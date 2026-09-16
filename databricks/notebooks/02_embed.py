# Databricks notebook source

# MAGIC %md
# MAGIC # 02 — Generate Article Embeddings
# MAGIC
# MAGIC Finds source articles that do not have a current embedding,
# MAGIC generates vectors, and stores them in Lakebase.
# MAGIC
# MAGIC This notebook is incremental and safe to rerun.

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
    "batch_size",
    "50",
    "Batch size",
)

batch_size = int(
    dbutils.widgets.get(
        "batch_size"
    )
)

# COMMAND ----------

import json
import os
import time
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
# MAGIC ## Load articles needing embeddings

# COMMAND ----------

with get_conn() as conn:

    with conn.cursor() as cur:

        cur.execute(
            """
            SELECT
                id,
                title,
                content,
                content_hash
            FROM source_articles
            WHERE embedding IS NULL
            ORDER BY ingested_at
            LIMIT %s
            """,
            (batch_size,),
        )

        articles = cur.fetchall()


print(
    f"Articles requiring embeddings: "
    f"{len(articles)}"
)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Embedding function
# MAGIC
# MAGIC Runs locally on the cluster with `sentence-transformers`
# MAGIC (multilingual model — articles are Polish). Keep this model in
# MAGIC sync with `EMBEDDING_MODEL_NAME` in 03/04 — they must match.

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

EMBEDDER = SentenceTransformer(
    EMBEDDING_MODEL_NAME
)


def embed_text(
    text: str,
):

    return [
        float(v)
        for v in EMBEDDER.encode(text)
    ]

# COMMAND ----------

# MAGIC %md
# MAGIC ## Generate and persist vectors

# COMMAND ----------

processed = 0
failed = 0

with get_conn() as conn:

    with conn.cursor() as cur:

        for (
            article_id,
            title,
            content,
            content_hash,
        ) in articles:

            text = (
                f"{title}\n\n"
                f"{content}"
            )

            try:

                vector = embed_text(
                    text
                )

                if not vector:

                    raise ValueError(
                        "Embedding returned empty vector"
                    )

                cur.execute(
                    """
                    UPDATE source_articles
                    SET
                        embedding = %s::vector,
                        embedding_model = %s,
                        embedding_content_hash = %s,
                        embedding_created_at = NOW(),
                        updated_at = NOW()
                    WHERE id = %s
                    """,
                    (
                        pg_vector(vector),
                        EMBEDDING_MODEL_NAME,
                        content_hash,
                        article_id,
                    ),
                )

                processed += 1

            except Exception as exc:

                failed += 1

                print(
                    f"Embedding failed "
                    f"for article {article_id}: "
                    f"{exc}"
                )

    conn.commit()


print(
    f"Embedded={processed}, "
    f"failed={failed}"
)

# COMMAND ----------

dbutils.notebook.exit(
    json.dumps(
        {
            "processed": processed,
            "failed": failed,
        }
    )
)