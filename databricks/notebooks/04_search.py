# Databricks notebook source

# MAGIC %md
# MAGIC # 04 — Semantic Search
# MAGIC
# MAGIC Interactive semantic search over Meczyki source articles.
# MAGIC
# MAGIC Parameters:
# MAGIC
# MAGIC     query
# MAGIC     limit
# MAGIC
# MAGIC This notebook is read-only.

# COMMAND ----------

# MAGIC %pip uninstall -y psycopg2 psycopg2-binary
# MAGIC %pip install \
# MAGIC   sentence-transformers

# COMMAND ----------

# Databricks bundles a compatible psycopg2; never pip-install psycopg or
# psycopg2 here (their bundled libpq aborts this kernel). Restart Python
# so pip-installed deps load against a clean runtime.
dbutils.library.restartPython()

# COMMAND ----------

dbutils.widgets.text(
    "query",
    "transfery piłkarskie",
    "Search query",
)

dbutils.widgets.text(
    "limit",
    "10",
    "Results",
)

query = dbutils.widgets.get(
    "query"
).strip()

limit = int(
    dbutils.widgets.get(
        "limit"
    )
)

if not query:

    raise ValueError(
        "query is required"
    )

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


def pg_vector(values):

    return (
        "["
        + ",".join(
            repr(float(v))
            for v in values
        )
        + "]"
    )

# COMMAND ----------

# MAGIC %md
# MAGIC ## Query embedding

# COMMAND ----------

# MAGIC %md
# MAGIC ## Query embedding
# MAGIC
# MAGIC Same `sentence-transformers` model as `02_embed.py` — they must
# MAGIC match for vector similarity to work.

# COMMAND ----------

import os


HF_CACHE_VOLUME = os.environ.get(
    "HF_CACHE_VOLUME",
    "/Volumes/meczyki/models/ml-cache",
)

try:

    os.makedirs(HF_CACHE_VOLUME, exist_ok=True)

    os.environ["HF_HOME"] = (
        f"{HF_CACHE_VOLUME}/hf"
    )

    os.environ["SENTENCE_TRANSFORMERS_HOME"] = (
        f"{HF_CACHE_VOLUME}/st"
    )

except OSError:

    print(
        "Cache volume not writable; "
        "using ephemeral cluster cache."
    )

from sentence_transformers import SentenceTransformer


EMBEDDING_MODEL_NAME = (
    "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
)

QUERY_EMBEDDER = SentenceTransformer(
    EMBEDDING_MODEL_NAME
)


def embed_query(
    text: str,
) -> list[float]:

    return [
        float(v)
        for v in QUERY_EMBEDDER.encode(text)
    ]


query_vector = embed_query(
    query
)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Semantic retrieval

# COMMAND ----------

with get_conn() as conn:

    with conn.cursor() as cur:

        cur.execute(
            """
            SELECT
                id,
                title,
                description,
                canonical_url,
                published_at,
                1 - (
                    embedding <=> %s::vector
                ) AS similarity
            FROM source_articles
            WHERE embedding IS NOT NULL
            ORDER BY
                embedding <=> %s::vector
            LIMIT %s
            """,
            (
                pg_vector(query_vector),
                pg_vector(query_vector),
                limit,
            ),
        )

        rows = cur.fetchall()

# COMMAND ----------

# MAGIC %md
# MAGIC ## Results

# COMMAND ----------

results = []

for row in rows:

    (
        article_id,
        title,
        description,
        url,
        published_at,
        similarity,
    ) = row

    results.append(
        {
            "id": article_id,
            "title": title,
            "description": description,
            "url": url,
            "published_at": published_at,
            "similarity": float(
                similarity
            ),
        }
    )


display(
    spark.createDataFrame(
        results
    )
    if results
    else spark.createDataFrame(
        [],
        """
        id long,
        title string,
        description string,
        url string,
        published_at timestamp,
        similarity double
        """
    )
)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Debugging information

# COMMAND ----------

print(
    f"Query: {query}"
)

print(
    f"Returned: {len(results)}"
)

for result in results:

    print(
        f"{result['similarity']:.4f} "
        f"{result['title']}"
    )