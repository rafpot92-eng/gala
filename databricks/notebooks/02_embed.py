# Databricks notebook source

# MAGIC %md
# MAGIC # 02 — Generate Article Embeddings
# MAGIC
# MAGIC Chunks each source article into ~1,000-char paragraph-aware
# MAGIC pieces and embeds them with `intfloat/multilingual-e5-large`
# MAGIC (1024 dims). Chunks are the actual retrieval unit used by
# MAGIC `03_editorial_agent.py` and `04_search.py`.
# MAGIC
# MAGIC This notebook is incremental and safe to rerun. It picks up
# MAGIC any article that does not yet have chunks for the current
# MAGIC embedding model.

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

import hashlib
import json
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
# MAGIC ## Load articles needing chunks
# MAGIC
# MAGIC An article is picked up if it does not yet have chunks
# MAGIC with the current `embedding_model`.

# COMMAND ----------

EMBEDDING_MODEL_NAME = (
    "intfloat/multilingual-e5-large"
)


with get_conn() as conn:

    with conn.cursor() as cur:

        cur.execute(
            """
            SELECT a.id, a.title, a.content, a.content_hash
            FROM source_articles a
            WHERE NOT EXISTS (
                SELECT 1
                FROM source_article_chunks c
                WHERE c.source_article_id = a.id
                  AND c.embedding_model = %s
            )
            ORDER BY a.ingested_at
            LIMIT %s
            """,
            (
                EMBEDDING_MODEL_NAME,
                batch_size,
            ),
        )

        articles = cur.fetchall()


print(
    f"Articles requiring chunks: "
    f"{len(articles)}"
)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Chunking
# MAGIC
# MAGIC Paragraph-aware: split on `\n\n`, accumulate up to 1,000 chars
# MAGIC per chunk. Any paragraph longer than 1,000 chars is hard-split
# MAGIC with a 150-char overlap to preserve sentence boundaries.

# COMMAND ----------

MAX_CHARS = 1000
HARD_SPLIT_OVERLAP = 150


def chunk_article(
    text: str,
) -> list[str]:

    paragraphs = [
        p.strip()
        for p in text.split("\n\n")
        if p.strip()
    ]

    chunks = []
    current = ""

    for paragraph in paragraphs:

        if len(paragraph) > MAX_CHARS:

            if current:

                chunks.append(current)
                current = ""

            for start in range(
                0,
                len(paragraph),
                MAX_CHARS - HARD_SPLIT_OVERLAP,
            ):

                chunks.append(
                    paragraph[
                        start:
                        start + MAX_CHARS
                    ]
                )

        elif (
            len(current) + len(paragraph) + 2
            <= MAX_CHARS
        ):

            current = (
                f"{current}\n\n{paragraph}"
                if current
                else paragraph
            )

        else:

            chunks.append(current)
            current = paragraph

    if current:

        chunks.append(current)

    return chunks

# COMMAND ----------

# MAGIC %md
# MAGIC ## Embedding function
# MAGIC
# MAGIC Runs locally on the cluster with `sentence-transformers`.
# MAGIC E5 requires a `passage:` prefix for document embeddings and
# MAGIC a `query:` prefix for query embeddings — the query variant
# MAGIC lives in 03/04.

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


EMBEDDER = SentenceTransformer(
    EMBEDDING_MODEL_NAME
)


def embed_chunks(
    texts: list[str],
) -> list[list[float]]:

    return [
        [float(v) for v in vec]
        for vec in EMBEDDER.encode(
            texts,
            show_progress_bar=False,
        )
    ]

# COMMAND ----------

# MAGIC %md
# MAGIC ## Generate and persist chunks

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

            try:

                chunks = chunk_article(content)

                if not chunks:

                    raise ValueError(
                        "Chunking returned empty list"
                    )

                prefixed = [
                    f"passage: {c}"
                    for c in chunks
                ]

                vectors = embed_chunks(
                    prefixed
                )

                cur.execute(
                    """
                    DELETE FROM source_article_chunks
                    WHERE source_article_id = %s
                    """,
                    (article_id,),
                )

                for idx, (
                    vector,
                    chunk_text,
                ) in enumerate(
                    zip(vectors, chunks)
                ):

                    chunk_hash = hashlib.sha256(
                        chunk_text.encode("utf-8")
                    ).hexdigest()

                    cur.execute(
                        """
                        INSERT INTO source_article_chunks (
                            source_article_id,
                            chunk_index,
                            content,
                            content_hash,
                            embedding,
                            embedding_model
                        )
                        VALUES (%s, %s, %s, %s, %s::vector, %s)
                        """,
                        (
                            article_id,
                            idx,
                            chunk_text,
                            chunk_hash,
                            pg_vector(vector),
                            EMBEDDING_MODEL_NAME,
                        ),
                    )

                processed += 1

            except Exception as exc:

                failed += 1

                print(
                    f"Chunking failed "
                    f"for article {article_id}: "
                    f"{exc}"
                )

    conn.commit()


print(
    f"Chunked={processed}, "
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