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

# MAGIC %pip install psycopg[binary]

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
from urllib.parse import quote_plus

import psycopg


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
    raise RuntimeError(
        "No DB connection. Set DATABASE_URL or PGHOST/PGUSER/PGDATABASE in env."
    )

# COMMAND ----------

# MAGIC %md
# MAGIC ## Query embedding

# COMMAND ----------

def embed_query(
    text: str,
) -> list[float]:

    """
    Must use exactly the same embedding model
    as 02_embed.py.
    """

    raise NotImplementedError(
        "Configure query embedding provider "
        "in editorial/embeddings.py"
    )


query_vector = embed_query(
    query
)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Semantic retrieval

# COMMAND ----------

with psycopg.connect(
    DATABASE_URL
) as conn:

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
                query_vector,
                query_vector,
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