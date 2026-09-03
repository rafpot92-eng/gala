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

# MAGIC %pip install \
# MAGIC   requests \
# MAGIC   beautifulsoup4 \
# MAGIC   lxml \
# MAGIC   psycopg[binary] \
# MAGIC   python-dateutil

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
import re
import time
from urllib.parse import (
    urljoin,
    urlparse,
    urlunparse,
)

import requests
from bs4 import BeautifulSoup
from dateutil import parser as date_parser


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
import psycopg


DATABASE_URL = (
    dbutils.secrets.get(
        scope="meczyki",
        key="lakebase_database_url",
    )
)


def get_existing_urls(urls):

    if not urls:
        return set()

    with psycopg.connect(
        DATABASE_URL
    ) as conn:

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

    published_at = None

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

    # Prefer semantic article containers.
    article = soup.find(
        "article"
    )

    if not article:

        article = soup.find(
            "main"
        )

    if not article:

        article = soup.body

    paragraphs = []

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

            if not text:
                continue

            # Avoid tiny navigation fragments.
            if len(text) < 40:
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
# MAGIC ## Delta Bronze
# MAGIC
# MAGIC If you use Unity Catalog, replace these names with your configured
# MAGIC catalog/schema.

# COMMAND ----------

CATALOG = "meczyki"

BRONZE_TABLE = (
    f"{CATALOG}.bronze.raw_articles"
)

SILVER_TABLE = (
    f"{CATALOG}.silver.source_articles"
)

spark.sql(
    f"""
    CREATE SCHEMA IF NOT EXISTS
        {CATALOG}.bronze
    """
)

spark.sql(
    f"""
    CREATE SCHEMA IF NOT EXISTS
        {CATALOG}.silver
    """
)

# COMMAND ----------

if parsed_articles:

    bronze_rows = []

    now = datetime.now(
        timezone.utc
    )

    for article in parsed_articles:

        bronze_rows.append(
            (
                article["canonical_url"],
                article["title"],
                article["description"],
                article["image_url"],
                article["published_at"],
                article["content"],
                article["content_hash"],
                article["source_name"],
                now,
            )
        )

    bronze_df = spark.createDataFrame(
        bronze_rows,
        [
            "canonical_url",
            "title",
            "description",
            "image_url",
            "published_at",
            "content",
            "content_hash",
            "source_name",
            "ingested_at",
        ],
    )

    (
        bronze_df.write
        .format("delta")
        .mode("append")
        .saveAsTable(
            BRONZE_TABLE
        )
    )

# COMMAND ----------

# MAGIC %md
# MAGIC ## Lakebase upsert

# COMMAND ----------

with psycopg.connect(
    DATABASE_URL
) as conn:

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

dbutils.notebook.exit(
    json.dumps(
        {
            "discovered": len(article_urls),
            "already_exists": len(existing_urls),
            "parsed": len(parsed_articles),
        }
    )
)