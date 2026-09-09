# Databricks notebook source

# MAGIC %md
# MAGIC # 02 — Generate Article Embeddings
# MAGIC
# MAGIC Finds source articles that do not have a current embedding,
# MAGIC generates vectors, and stores them in Lakebase.
# MAGIC
# MAGIC This notebook is incremental and safe to rerun.

# COMMAND ----------

# MAGIC %pip install \
# MAGIC   psycopg[binary] \
# MAGIC   requests

# COMMAND ----------

dbutils.widgets.text(
    "batch_size",
    "50",
    "Batch size",
)

dbutils.widgets.text(
    "embedding_model",
    "databricks-gte-large-en",
    "Embedding model",
)

batch_size = int(
    dbutils.widgets.get(
        "batch_size"
    )
)

embedding_model = dbutils.widgets.get(
    "embedding_model"
)

# COMMAND ----------

import json
import os
import time
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
# MAGIC ## Load articles needing embeddings

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
# MAGIC Keep provider-specific implementation here only temporarily.
# MAGIC In the final project this should import:
# MAGIC
# MAGIC     from editorial.embeddings import embed_text
# MAGIC
# MAGIC so the notebook does not know which model/provider is used.

# COMMAND ----------

def embed_text(
    text: str,
    model: str,
):

    """
    Replace this implementation with the project's
    Databricks Model Serving / embedding implementation.

    The function must return:

        list[float]
    """

    # Example contract only.
    #
    # Do not fake vectors in production.
    #
    # The actual implementation should call the
    # configured Databricks embedding endpoint/model.

    raise NotImplementedError(
        "Configure the production embedding provider "
        "in databricks/src/editorial/embeddings.py"
    )

# COMMAND ----------

# MAGIC %md
# MAGIC ## Generate and persist vectors

# COMMAND ----------

processed = 0
failed = 0

with psycopg.connect(
    DATABASE_URL
) as conn:

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
                    text,
                    embedding_model,
                )

                if not vector:

                    raise ValueError(
                        "Embedding returned empty vector"
                    )

                cur.execute(
                    """
                    UPDATE source_articles
                    SET
                        embedding = %s,
                        embedding_model = %s,
                        embedding_content_hash = %s,
                        embedding_created_at = NOW(),
                        updated_at = NOW()
                    WHERE id = %s
                    """,
                    (
                        vector,
                        embedding_model,
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