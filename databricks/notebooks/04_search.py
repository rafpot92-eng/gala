# Databricks notebook source

# MAGIC %md
# MAGIC # 04 — Semantic Search
# MAGIC
# MAGIC Interactive semantic search over Meczyki source articles.
# MAGIC
# MAGIC Uses chunk-level retrieval with a cross-encoder reranker.
# MAGIC Returns the best matching chunk per article.
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
# MAGIC
# MAGIC Same `intfloat/multilingual-e5-large` model as `02_embed.py`
# MAGIC — they must match. E5 requires a `query:` prefix for
# MAGIC query-side embeddings.

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

from sentence_transformers import (
    CrossEncoder,
    SentenceTransformer,
)


EMBEDDING_MODEL_NAME = (
    "intfloat/multilingual-e5-large"
)

QUERY_EMBEDDER = SentenceTransformer(
    EMBEDDING_MODEL_NAME
)


def embed_query(
    text: str,
) -> list[float]:

    return [
        float(v)
        for v in QUERY_EMBEDDER.encode(
            f"query: {text}"
        )
    ]


RERANKER = CrossEncoder(
    "BAAI/bge-reranker-v2-m3"
)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Chunk retrieval + rerank

# COMMAND ----------

query_vector = embed_query(query)

with get_conn() as conn:

    with conn.cursor() as cur:

        cur.execute(
            """
            SELECT
                c.id,
                c.source_article_id,
                c.chunk_index,
                c.content,
                s.title,
                s.canonical_url,
                s.published_at,
                1 - (
                    c.embedding <=> %s::vector
                ) AS similarity
            FROM source_article_chunks c
            JOIN source_articles s
                ON s.id = c.source_article_id
            WHERE c.embedding IS NOT NULL
            ORDER BY
                c.embedding <=> %s::vector
            LIMIT 50
            """,
            (
                pg_vector(query_vector),
                pg_vector(query_vector),
            ),
        )

        candidates = cur.fetchall()


# Rerank candidates with cross-encoder.

if candidates:

    pairs = [
        (query, row[3])
        for row in candidates
    ]

    scores = RERANKER.score(pairs)

    reranked = [
        (row, float(score))
        for row, score in zip(
            candidates, scores
        )
    ]

    reranked.sort(
        key=lambda x: x[1],
        reverse=True,
    )

else:

    reranked = []

# Dedupe: keep best chunk per article.

seen_articles = set()
results = []

for row, rerank_score in reranked:

    article_id = row[1]

    if article_id in seen_articles:

        continue

    seen_articles.add(article_id)

    results.append(
        {
            "id": row[0],
            "article_id": article_id,
            "title": row[4],
            "url": row[5],
            "published_at": row[6],
            "snippet": row[3][:300] + (
                "..." if len(row[3]) > 300 else ""
            ),
            "similarity": float(row[7]),
            "rerank_score": rerank_score,
        }
    )

    if len(results) >= limit:

        break

# COMMAND ----------

# MAGIC %md
# MAGIC ## Results

# COMMAND ----------

display(
    spark.createDataFrame(results)
    if results
    else spark.createDataFrame(
        [],
        """
        id long,
        article_id long,
        title string,
        url string,
        published_at timestamp,
        snippet string,
        similarity double,
        rerank_score double
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
        f"{result['rerank_score']:.4f} "
        f"{result['title']}"
    )