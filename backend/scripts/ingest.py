"""
Meczyki article ingestion.

Discovers new articles, parses metadata/content, deduplicates
against PostgreSQL, and persists to both PostgreSQL and Parquet.

Usage:
    python backend/scripts/ingest.py
    make ingest
"""

import hashlib
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote_plus, urljoin, urlparse, urlunparse

from dotenv import load_dotenv
import pandas as pd
import psycopg
import requests
from bs4 import BeautifulSoup
from dateutil import parser as date_parser

# load_dotenv(Path(__file__).resolve().parents[2] / ".env")

load_dotenv("/home/user/proj/gala/.env")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    pg = {k: os.environ.get(k) for k in ("PGHOST", "PGDATABASE", "PGUSER", "PGPASSWORD", "PGPORT", "PGSSLMODE")}
    if pg["PGHOST"] and pg["PGUSER"] and pg["PGDATABASE"]:
        DATABASE_URL = (
            f"postgresql://{quote_plus(pg['PGUSER'])}:{quote_plus(pg['PGPASSWORD'] or '')}@{pg['PGHOST']}"
            f":{pg.get('PGPORT') or 5432}/{pg['PGDATABASE']}"
            f"?sslmode={pg.get('PGSSLMODE') or 'prefer'}"
        )
if not DATABASE_URL:
    print("ERROR: no DB connection. Set DATABASE_URL or PGHOST/PGUSER/PGDATABASE in env.")
    sys.exit(1)

ARCHIVE_DIR = Path(os.environ.get("ARCHIVE_DIR", "data/archive"))
ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)

BASE_URL = "https://www.meczyki.pl"
DISCOVERY_URLS = [
    f"{BASE_URL}/newsy",
    f"{BASE_URL}/transfery",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; MeczykiEditorialBot/1.0; +https://example.com/bot)"
    )
}

TRACKING_PARAMETERS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "fbclid", "gclid",
}

ARTICLE_PATH_PATTERNS = [
    re.compile(r"^/newsy/"),
    re.compile(r"^/transfery/"),
]

session = requests.Session()
session.headers.update(HEADERS)


# ---------------------------------------------------------------------------
# URL utilities
# ---------------------------------------------------------------------------

def normalize_url(url: str) -> str:
    parsed = urlparse(url)
    clean_query = []
    for item in parsed.query.split("&"):
        if not item:
            continue
        if "=" in item:
            key, value = item.split("=", 1)
        else:
            key, value = item, ""
        if key.lower() in TRACKING_PARAMETERS:
            continue
        clean_query.append(f"{key}={value}" if value else key)
    return urlunparse((
        parsed.scheme.lower(),
        parsed.netloc.lower(),
        parsed.path.rstrip("/"),
        "",
        "&".join(clean_query),
        "",
    ))


def is_meczyki_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
        return parsed.netloc.endswith("meczyki.pl") and parsed.scheme in {"http", "https"}
    except Exception:
        return False


def looks_like_article_url(url: str) -> bool:
    if not is_meczyki_url(url):
        return False
    parsed = urlparse(url)
    return any(p.search(parsed.path) for p in ARTICLE_PATH_PATTERNS)


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

def discover_article_urls() -> list[str]:
    discovered = set()
    for discovery_url in DISCOVERY_URLS:
        try:
            response = session.get(discovery_url, timeout=30)
            response.raise_for_status()
        except Exception as exc:
            print(f"Discovery failed: {discovery_url}: {exc}")
            continue
        soup = BeautifulSoup(response.text, "lxml")
        for anchor in soup.find_all("a", href=True):
            url = normalize_url(urljoin(discovery_url, anchor["href"]))
            if looks_like_article_url(url):
                discovered.add(url)
    return sorted(discovered)


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

def clean_text(value: str | None) -> str | None:
    if not value:
        return None
    return re.sub(r"\s+", " ", value).strip()


def parse_article(url: str) -> dict:
    response = session.get(url, timeout=30)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "lxml")

    for element in soup(["script", "style", "noscript", "svg"]):
        element.decompose()

    # Title
    title = None
    og_title = soup.find("meta", property="og:title")
    if og_title:
        title = og_title.get("content")
    if not title and soup.title:
        title = soup.title.get_text()

    # Description
    description = None
    meta_desc = soup.find("meta", attrs={"name": "description"})
    if meta_desc:
        description = meta_desc.get("content")

    # Image
    image_url = None
    og_image = soup.find("meta", property="og:image")
    if og_image:
        image_url = og_image.get("content")

    # Published date — prefer JSON-LD datePublished, fall back to <time>
    published_at = None
    date_match = re.search(r'"datePublished"\s*:\s*"([^"]+)"', response.text)
    if date_match:
        try:
            published_at = date_parser.parse(date_match.group(1)).astimezone(timezone.utc)
        except Exception:
            published_at = None
    if not published_at:
        time_el = soup.find("time")
        if time_el:
            raw_date = time_el.get("datetime") or time_el.get_text(strip=True)
            try:
                published_at = date_parser.parse(raw_date).astimezone(timezone.utc)
            except Exception:
                published_at = None

    # Content — Meczyki renders body in .news-text-body divs, not <p> tags.
    # Try semantic containers first, then fall back to any <p> in <main>/<body>.
    paragraphs = []
    body = soup.find("div", class_="news-text-body")
    if body:
        for block in body.find_all(recursive=False):
            text = clean_text(block.get_text(" ", strip=True))
            if not text or len(text) < 40:
                continue
            paragraphs.append(text)
    if not paragraphs:
        article = soup.find("article") or soup.find("main") or soup.body
        if article:
            for p in article.find_all("p"):
                text = clean_text(p.get_text(" ", strip=True))
                if not text or len(text) < 40:
                    continue
                paragraphs.append(text)

    content = "\n\n".join(paragraphs)
    if not content:
        raise ValueError(f"No article content found: {url}")

    content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()

    return {
        "canonical_url": normalize_url(url),
        "title": clean_text(title),
        "description": clean_text(description),
        "image_url": image_url,
        "published_at": published_at,
        "content": content,
        "content_hash": content_hash,
        "source_name": "meczyki",
    }


# ---------------------------------------------------------------------------
# PostgreSQL
# ---------------------------------------------------------------------------

def get_existing_urls(urls: list[str]) -> set[str]:
    if not urls:
        return set()
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT canonical_url FROM source_articles WHERE canonical_url = ANY(%s)",
                (list(urls),),
            )
            return {row[0] for row in cur.fetchall()}


def upsert_articles(articles: list[dict]) -> None:
    if not articles:
        return
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            for article in articles:
                cur.execute(
                    """
                    INSERT INTO source_articles (
                        canonical_url, source_name, title, description,
                        image_url, published_at, content, content_hash,
                        ingested_at, updated_at
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW()
                    )
                    ON CONFLICT (canonical_url)
                    DO UPDATE SET
                        title = EXCLUDED.title,
                        description = EXCLUDED.description,
                        image_url = EXCLUDED.image_url,
                        published_at = EXCLUDED.published_at,
                        content = EXCLUDED.content,
                        content_hash = EXCLUDED.content_hash,
                        updated_at = NOW()
                    WHERE source_articles.content_hash IS DISTINCT FROM EXCLUDED.content_hash
                    """,
                    (
                        article["canonical_url"],
                        article["source_name"],
                        article["title"],
                        article["description"],
                        article["image_url"],
                        article["published_at"],
                        article["content"],
                        article["content_hash"],
                    ),
                )
        conn.commit()
    print(f"PostgreSQL: upserted {len(articles)} articles.")


# ---------------------------------------------------------------------------
# Parquet archive
# ---------------------------------------------------------------------------

def write_parquet(articles: list[dict]) -> None:
    if not articles:
        return

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    source = articles[0]["source_name"]
    out_dir = ARCHIVE_DIR / source
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{today}.parquet"

    rows = []
    for a in articles:
        rows.append({
            "canonical_url": a["canonical_url"],
            "source_name": a["source_name"],
            "title": a["title"],
            "description": a["description"],
            "image_url": a["image_url"],
            "published_at": a["published_at"],
            "content": a["content"],
            "content_hash": a["content_hash"],
            "ingested_at": datetime.now(timezone.utc),
        })

    df = pd.DataFrame(rows)

    # Append if file exists, else create
    if out_path.exists():
        existing = pd.read_parquet(out_path)
        df = pd.concat([existing, df], ignore_index=True)
        df.drop_duplicates(subset=["canonical_url"], keep="last", inplace=True)

    df.to_parquet(out_path, index=False)
    print(f"Parquet: wrote {len(df)} rows to {out_path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    max_articles = int(os.environ.get("MAX_ARTICLES", "200"))
    lookback_hours = int(os.environ.get("LOOKBACK_HOURS", "2"))

    print(f"Config: max_articles={max_articles}, lookback_hours={lookback_hours}")

    # Discover
    article_urls = discover_article_urls()
    print(f"Discovered {len(article_urls)} candidate URLs.")
    article_urls = article_urls[:max_articles]

    # Dedupe
    existing_urls = get_existing_urls(article_urls)
    new_urls = [u for u in article_urls if u not in existing_urls]
    print(f"Already ingested: {len(existing_urls)}, New: {len(new_urls)}")

    if not new_urls:
        print("Nothing to do.")
        return

    # Parse
    parsed = []
    for i, url in enumerate(new_urls, 1):
        print(f"[{i}/{len(new_urls)}] {url}")
        try:
            parsed.append(parse_article(url))
        except Exception as exc:
            print(f"FAILED: {url}: {exc}")
        time.sleep(0.5)

    print(f"Parsed {len(parsed)} articles.")

    # Write
    upsert_articles(parsed)
    write_parquet(parsed)

    print("Done.")


if __name__ == "__main__":
    main()
