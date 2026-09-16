# Databricks notebook source

# MAGIC %md
# MAGIC # 05 — Quality Evaluation
# MAGIC
# MAGIC Lightweight eval over generated articles. Computes:
# MAGIC
# MAGIC     - article word count
# MAGIC     - vocabulary overlap between the article and its
# MAGIC       linked source chunks (grounding proxy)
# MAGIC     - average human quality_score (stored by the API on
# MAGIC       reject/approve/publish)
# MAGIC     - rejection rate
# MAGIC
# MAGIC Writes a summary row into `eval_runs`. Read-only for
# MAGIC articles; append-only for `eval_runs`.
# MAGIC
# MAGIC This is intentionally not a full RAG eval framework. It exists
# MAGIC to detect regressions when prompts/models change.

# COMMAND ----------

# MAGIC %pip uninstall -y psycopg2 psycopg2-binary
# MAGIC %pip install \
# MAGIC   requests

# COMMAND ----------

dbutils.library.restartPython()

# COMMAND ----------

dbutils.widgets.text(
    "sample_size",
    "20",
    "Articles to evaluate",
)

sample_size = int(
    dbutils.widgets.get(
        "sample_size"
    )
)

# COMMAND ----------

import json
import os
import re
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

# COMMAND ----------

def article_tokens(text):
    return set(
        re.findall(
            r"[a-ząęćłńóśźż0-9]+",
            text.lower(),
        )
    )

# COMMAND ----------

# MAGIC %md
# MAGIC ## Human feedback stats

# COMMAND ----------

with get_conn() as conn:

    with conn.cursor() as cur:

        cur.execute(
            """
            SELECT
                a.id,
                (al.metadata
                    ->> 'quality_score')::int
                    AS quality_score,
                a.created_at
            FROM generated_articles a
            JOIN editorial_audit_log al
                ON al.article_id = a.id
            WHERE al.metadata ? 'quality_score'
            ORDER BY a.id
            """
        )

        feedback_rows = cur.fetchall()

        cur.execute(
            """
            SELECT
                COUNT(*) FILTER (
                    WHERE action =
                        'status_change:ready_for_review'
                ) AS reviews,
                COUNT(*) FILTER (
                    WHERE action =
                        'status_change:draft'
                ) AS rejections
            FROM editorial_audit_log
            """
        )

        reviews, rejections = cur.fetchone()


quality_scores = [
    row[1]
    for row in feedback_rows
    if row[1] is not None
]

avg_quality = (
    sum(quality_scores) / len(quality_scores)
    if quality_scores
    else None
)

rejection_rate = (
    rejections / reviews
    if reviews
    else None
)

print(
    f"Reviews={reviews}, "
    f"rejections={rejections}, "
    f"avg quality={avg_quality}"
)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Source-overlap on a sample of articles

# COMMAND ----------

with get_conn() as conn:

    with conn.cursor() as cur:

        cur.execute(
            """
            SELECT
                a.id,
                a.content,
                COALESCE(
                    string_agg(c.content, ' '),
                    ''
                ) AS source_text
            FROM generated_articles a
            LEFT JOIN generated_article_sources g
                ON g.generated_article_id = a.id
            LEFT JOIN source_article_chunks c
                ON c.source_article_id =
                   g.source_article_id
            GROUP BY a.id, a.content
            ORDER BY a.id DESC
            LIMIT %s
            """,
            (sample_size,),
        )

        sample = cur.fetchall()


overlaps = []
word_counts = []

for article_id, content, source_text in sample:

    article = article_tokens(content)
    sources = article_tokens(source_text)

    if not article:

        continue

    word_counts.append(
        len(content.split())
    )

    overlaps.append(
        len(article & sources)
        / len(article)
    )

avg_word_count = (
    sum(word_counts) / len(word_counts)
    if word_counts
    else None
)

avg_overlap = (
    sum(overlaps) / len(overlaps)
    if overlaps
    else None
)

print(
    f"Sample={len(sample)}, "
    f"avg words={avg_word_count}, "
    f"avg source overlap={avg_overlap:.3f}"
)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Store run summary

# COMMAND ----------

with get_conn() as conn:

    with conn.cursor() as cur:

        cur.execute(
            """
            INSERT INTO eval_runs (
                sample_size,
                avg_word_count,
                avg_source_overlap,
                avg_quality_score,
                rejection_rate
            )
            VALUES (%s, %s, %s, %s, %s)
            """,
            (
                len(sample),
                avg_word_count,
                avg_overlap,
                avg_quality,
                rejection_rate,
            ),
        )

    conn.commit()

print("Stored eval_runs row.")

# COMMAND ----------

dbutils.notebook.exit(
    json.dumps(
        {
            "sample_size": len(sample),
            "avg_word_count": avg_word_count,
            "avg_source_overlap": avg_overlap,
            "avg_quality_score": avg_quality,
            "rejection_rate": rejection_rate,
        }
    )
)