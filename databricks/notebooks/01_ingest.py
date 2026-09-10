# Databricks notebook source

# MAGIC %md
# MAGIC # 01 — Meczyki Article Ingestion
# MAGIC
# MAGIC Discovers new Meczyki articles, parses metadata/content,
# MAGIC deduplicates them, and persists them to the source article store.
# MAGIC
# MAGIC This notebook is designed to run hourly.
# MAGIC
# MAGIC Workflow:
# MAGIC
# MAGIC     Meczyki /newsy
# MAGIC          ↓
# MAGIC     discover URLs
# MAGIC          ↓
# MAGIC     normalize URLs
# MAGIC          ↓
# MAGIC     parse article
# MAGIC          ↓
# MAGIC     content hash
# MAGIC          ↓
# MAGIC     Delta Bronze/Silver
# MAGIC          ↓
# MAGIC     Lakebase source_articles
# MAGIC
# MAGIC The operation is idempotent.

# COMMAND ----------

# MAGIC %pip uninstall -y psycopg2 psycopg2-binary
# MAGIC %pip install \
# MAGIC   requests \
# MAGIC   beautifulsoup4 \
# MAGIC   lxml \
# MAGIC   python-dateutil

# COMMAND ----------

# Databricks bundles a compatible psycopg2; never pip-install psycopg or
# psycopg2 here (their bundled libpq aborts this kernel). Restart Python
# so pip-installed deps load against a clean runtime.
dbutils.library.restartPython()

# COMMAND ----------

dbutils.widgets.text(
    "lookback_hours",
    "2",
    "Lookback hours",
)

dbutils.widgets.text(
    "max_articles",
    "200",
    "Maximum articles",
)

dbutils.widgets.text(
    "source_name",
    "meczyki",
    "Source",
)

lookback_hours = int(
    dbutils.widgets.get("lookback_hours")
)

max_articles = int(
    dbutils.widgets.get("max_articles")
)

source_name = dbutils.widgets.get(
    "source_name"
)

print(
    f"source={source_name}, "
    f"lookback_hours={lookback_hours}, "
    f"max_articles={max_articles}"
)

# COMMAND ----------

from datetime import datetime, timezone
import hashlib
import json
import os
import re
import time
from pathlib import Path
from urllib.parse import (
    urljoin,
    urlparse,
    urlunparse,
)

import pandas as pd
import requests
from bs4 import BeautifulSoup
from dateutil import parser as date_parser


ARCHIVE_DIR = Path(
    os.environ.get(
        "ARCHIVE_DIR",
        "data/archive",
    )
)

ARCHIVE_DIR.mkdir(
    parents=True,
    exist_ok=True,
)


BASE_URL = "https://www.meczyki.pl"

DISCOVERY_URLS = [
    f"{BASE_URL}/newsy",
    f"{BASE_URL}/transfery",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 "
        "(compatible; MeczykiEditorialBot/1.0; "
        "+https://example.com/bot)"
    )
}

session = requests.Session()
session.headers.update(HEADERS)


# COMMAND ----------

# MAGIC %md
# MAGIC ## URL normalization

# COMMAND ----------

TRACKING_PARAMETERS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "fbclid",
    "gclid",
}


def normalize_url(url: str) -> str:

    parsed = urlparse(url)

    clean_query = []

    for key, value in (
        [
            item.split("=", 1)
            if "=" in item
            else (item, "")
            for item in parsed.query.split("&")
            if item
        ]
    ):

        if key.lower() in TRACKING_PARAMETERS:
            continue

        clean_query.append(
            f"{key}={value}"
            if value
            else key
        )

    normalized = urlunparse(
        (
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            parsed.path.rstrip("/"),
            "",
            "&".join(clean_query),
            "",
        )
    )

    return normalized


def is_meczyki_url(url: str) -> bool:

    try:
        parsed = urlparse(url)

        return (
            parsed.netloc.endswith("meczyki.pl")
            and parsed.scheme in {"http", "https"}
        )

    except Exception:
        return False


# COMMAND ----------

# MAGIC %md
# MAGIC ## Discovery

# COMMAND ----------

ARTICLE_PATH_PATTERNS = [
    re.compile(r"^/newsy/"),
    re.compile(r"^/transfery/"),
]


def looks_like_article_url(url: str) -> bool:

    parsed = urlparse(url)

    if not is_meczyki_url(url):
        return False

    path = parsed.path

    return any(
        pattern.search(path)
        for pattern in ARTICLE_PATH_PATTERNS
    )


def discover_article_urls():

    discovered = set()

    for discovery_url in DISCOVERY_URLS:

        try:

            response = session.get(
                discovery_url,
                timeout=30,
            )

            response.raise_for_status()

        except Exception as exc:

            print(
                f"Discovery failed: "
                f"{discovery_url}: {exc}"
            )

            continue

        soup = BeautifulSoup(
            response.text,
            "lxml",
        )

        for anchor in soup.find_all(
            "a",
            href=True,
        ):

            href = anchor["href"]

            url = normalize_url(
                urljoin(
                    discovery_url,
                    href,
                )
            )

            if looks_like_article_url(url):
                discovered.add(url)

    return sorted(discovered)


article_urls = discover_article_urls()

print(
    f"Discovered {len(article_urls)} "
    f"candidate article URLs."
)

article_urls = article_urls[
    :max_articles
]

# COMMAND ----------

# MAGIC %md
# MAGIC ## Existing URL lookup
# MAGIC
# MAGIC The database is the final authority on whether an article has already
# MAGIC been ingested.

# COMMAND ----------

import os
from urllib.parse import quote_plus, urlparse

import psycopg2


DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    pg = {k: os.environ.get(k) for k in ("PGHOST", "PGDATABASE", "PGUSER", "PGPASSWORD", "PGPORT", "PGSSLMODE")}
    if pg["PGHOST"] and pg["PGUSER"] and pg["PGDATABASE"]:
        DATABASE_URL = (
            f"postgresql://{quote_plus(pg['PGUSER'])}:{quote_plus(pg['PGPASSWORD'] or '')}@{pg['PGHOST']}"
            f":{pg.get('PGPORT') or 5432}/{pg['PGDATABASE']}"
            f"?sslmode={pg.get('PGSSLMODE') or 'prefer'}"
        )
if not DATABASE_URL and "dbutils" in globals():
    DATABASE_URL = dbutils.secrets.get(
        scope="meczyki",
        key="lakebase_database_url",
    )
if not DATABASE_URL:
    raise RuntimeError(
        "No DB connection. Set DATABASE_URL, PGHOST/PGUSER/PGDATABASE, "
        "or the meczyki/lakebase_database_url secret."
    )


def get_conn():

    parsed = urlparse(DATABASE_URL)

    return psycopg2.connect(
        host=parsed.hostname,
        port=parsed.port or 5432,
        dbname=parsed.path.lstrip("/"),
        user=parsed.username,
        password=parsed.password,
        sslmode="require",
    )


def get_existing_urls(urls):

    if not urls:
        return set()

    with get_conn() as conn:

        with conn.cursor() as cur:

            cur.execute(
                """
                SELECT canonical_url
                FROM source_articles
                WHERE canonical_url = ANY(%s)
                """,
                (list(urls),),
            )

            return {
                row[0]
                for row in cur.fetchall()
            }


existing_urls = get_existing_urls(
    article_urls
)

new_urls = [
    url
    for url in article_urls
    if url not in existing_urls
]

print(
    f"Already ingested: "
    f"{len(existing_urls)}"
)

print(
    f"New articles: "
    f"{len(new_urls)}"
)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Article parser

# COMMAND ----------

def clean_text(value):

    if not value:
        return None

    return re.sub(
        r"\s+",
        " ",
        value,
    ).strip()


def parse_article(url: str):

    response = session.get(
        url,
        timeout=30,
    )

    response.raise_for_status()

    soup = BeautifulSoup(
        response.text,
        "lxml",
    )

    # Remove elements that should not be considered article text.
    for element in soup(
        [
            "script",
            "style",
            "noscript",
            "svg",
        ]
    ):
        element.decompose()

    title = None

    og_title = soup.find(
        "meta",
        property="og:title",
    )

    if og_title:
        title = og_title.get("content")

    if not title and soup.title:
        title = soup.title.get_text()

    description = None

    meta_description = soup.find(
        "meta",
        attrs={
            "name": "description"
        },
    )

    if meta_description:
        description = meta_description.get(
            "content"
        )

    image_url = None

    og_image = soup.find(
        "meta",
        property="og:image",
    )

    if og_image:
        image_url = og_image.get("content")

    # Published date — prefer JSON-LD datePublished,
    # fall back to <time>.
    published_at = None

    date_match = re.search(
        r'"datePublished"\s*:\s*"([^"]+)"',
        response.text,
    )

    if date_match:

        try:
            published_at = date_parser.parse(
                date_match.group(1)
            ).astimezone(timezone.utc)

        except Exception:
            published_at = None

    if not published_at:

        time_element = soup.find(
            "time"
        )

        if time_element:

            raw_date = (
                time_element.get(
                    "datetime"
                )
                or time_element.get_text(
                    strip=True
                )
            )

            try:
                published_at = (
                    date_parser.parse(
                        raw_date
                    )
                    .astimezone(timezone.utc)
                )

            except Exception:
                published_at = None

    # Meczyki renders the article body in .news-text-body
    # divs, not <p> tags. Prefer those, then fall back to
    # any <p> in the semantic container.
    paragraphs = []

    body = soup.find(
        "div",
        class_="news-text-body",
    )

    if body:

        for block in body.find_all(
            recursive=False
        ):

            text = clean_text(
                block.get_text(
                    " ",
                    strip=True,
                )
            )

            if not text or len(text) < 40:
                continue

            paragraphs.append(text)

    if not paragraphs:

        article = (
            soup.find("article")
            or soup.find("main")
            or soup.body
        )

        if article:

            for paragraph in article.find_all(
                "p"
            ):

                text = clean_text(
                    paragraph.get_text(
                        " ",
                        strip=True,
                    )
                )

                if not text or len(text) < 40:
                    continue

                paragraphs.append(text)

    content = "\n\n".join(
        paragraphs
    )

    if not content:
        raise ValueError(
            f"No article content found: {url}"
        )

    title = clean_text(title)

    description = clean_text(
        description
    )

    content_hash = hashlib.sha256(
        content.encode(
            "utf-8"
        )
    ).hexdigest()

    return {
        "canonical_url": normalize_url(url),
        "title": title,
        "description": description,
        "image_url": image_url,
        "published_at": published_at,
        "content": content,
        "content_hash": content_hash,
        "source_name": "meczyki",
    }


# COMMAND ----------

# MAGIC %md
# MAGIC ## Parse new articles

# COMMAND ----------

parsed_articles = []

for index, url in enumerate(
    new_urls,
    start=1,
):

    print(
        f"[{index}/{len(new_urls)}] "
        f"{url}"
    )

    try:

        article = parse_article(
            url
        )

        parsed_articles.append(
            article
        )

    except Exception as exc:

        print(
            f"FAILED: {url}: {exc}"
        )

    time.sleep(0.5)


print(
    f"Successfully parsed "
    f"{len(parsed_articles)} articles."
)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Lakebase upsert

# COMMAND ----------

with get_conn() as conn:

    with conn.cursor() as cur:

        for article in parsed_articles:

            cur.execute(
                """
                INSERT INTO source_articles (
                    canonical_url,
                    source_name,
                    title,
                    description,
                    image_url,
                    published_at,
                    content,
                    content_hash,
                    ingested_at,
                    updated_at
                )
                VALUES (
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, NOW(), NOW()
                )
                ON CONFLICT (
                    canonical_url
                )
                DO UPDATE SET
                    title = EXCLUDED.title,
                    description = EXCLUDED.description,
                    image_url = EXCLUDED.image_url,
                    published_at = EXCLUDED.published_at,
                    content = EXCLUDED.content,
                    content_hash = EXCLUDED.content_hash,
                    updated_at = NOW()
                WHERE
                    source_articles.content_hash
                    IS DISTINCT FROM
                    EXCLUDED.content_hash
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

print(
    f"Lakebase upserted "
    f"{len(parsed_articles)} articles."
)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Parquet archive
# MAGIC
# MAGIC Daily raw archive on disk for offline use.

# COMMAND ----------

def write_parquet(articles):

    if not articles:

        return

    today = datetime.now(
        timezone.utc
    ).strftime("%Y-%m-%d")

    source = articles[0][
        "source_name"
    ]

    out_dir = ARCHIVE_DIR / source

    out_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    out_path = out_dir / (
        f"{today}.parquet"
    )

    rows = [
        {
            "canonical_url": a["canonical_url"],
            "source_name": a["source_name"],
            "title": a["title"],
            "description": a["description"],
            "image_url": a["image_url"],
            "published_at": a["published_at"],
            "content": a["content"],
            "content_hash": a["content_hash"],
            "ingested_at": datetime.now(timezone.utc),
        }
        for a in articles
    ]

    df = pd.DataFrame(rows)

    if out_path.exists():

        existing = pd.read_parquet(
            out_path
        )

        df = pd.concat(
            [existing, df],
            ignore_index=True,
        )

        df.drop_duplicates(
            subset=["canonical_url"],
            keep="last",
            inplace=True,
        )

    df.to_parquet(
        out_path,
        index=False,
    )

    print(
        f"Parquet: wrote {len(df)} "
        f"rows to {out_path}"
    )


write_parquet(
    parsed_articles
)

# COMMAND ----------

dbutils.notebook.exit(
    json.dumps(
        {
            "discovered": len(article_urls),
            "already_exists": len(existing_urls),
            "parsed": len(parsed_articles),
        }
    )
)