# Databricks notebook source

# MAGIC %md
# MAGIC # 03 — Editorial Agent
# MAGIC
# MAGIC Generates an original sports article from source material.
# MAGIC
# MAGIC Parameters:
# MAGIC
# MAGIC     topic
# MAGIC     category
# MAGIC     desired_length
# MAGIC
# MAGIC IMPORTANT:
# MAGIC
# MAGIC The AI agent can only create:
# MAGIC
# MAGIC     draft
# MAGIC
# MAGIC It can never create:
# MAGIC
# MAGIC     ready_for_review
# MAGIC     approved
# MAGIC     published
# MAGIC
# MAGIC Human editorial workflow is handled by FastAPI.

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
    "topic",
    "",
    "Topic",
)

dbutils.widgets.text(
    "category",
    "Piłka nożna",
    "Category",
)

dbutils.widgets.text(
    "desired_length",
    "700",
    "Desired article length",
)

dbutils.widgets.text(
    "source_limit",
    "8",
    "Number of source articles",
)

dbutils.widgets.text(
    "generation_model",
    "databricks-meta-llama-3-3-70b-instruct",
    "Generation model",
)

topic = dbutils.widgets.get(
    "topic"
).strip()

category = dbutils.widgets.get(
    "category"
).strip()

desired_length = int(
    dbutils.widgets.get(
        "desired_length"
    )
)

source_limit = int(
    dbutils.widgets.get(
        "source_limit"
    )
)

generation_model = dbutils.widgets.get(
    "generation_model"
).strip()

if not topic:
    raise ValueError(
        "topic is required"
    )

# COMMAND ----------

import json
import os
from datetime import datetime, timezone
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
# MAGIC ## Retrieval
# MAGIC
# MAGIC We use vector similarity to find relevant source articles.
# MAGIC
# MAGIC The actual embedding implementation should be shared with
# MAGIC `02_embed.py`.

# COMMAND ----------

import os

import requests


def _workspace_url():

    url = os.environ.get(
        "DATABRICKS_HOST"
    ) or os.environ.get(
        "DATABRICKS_WORKSPACE_URL"
    )

    if url:

        return url

    if "dbutils" in globals():

        ctx = (
            dbutils.notebook
            .entry_point
            .getDbutils()
            .notebook()
            .getContext()
        )

        host = ctx.workspaceUrl().get()

        if host:

            return f"https://{host}"

    return (
        "https://"
        + spark.conf.get(
            "spark.databricks.workspaceUrl"
        )
    )


def _embedding_token():

    if "dbutils" in globals():

        return (
            dbutils.notebook
            .entry_point
            .getDbutils()
            .notebook()
            .getContext()
            .apiToken()
            .get()
        )

    return os.environ.get(
        "DATABRICKS_TOKEN"
    )


# COMMAND ----------

# MAGIC %md
# MAGIC ## Query embedding
# MAGIC
# MAGIC Same `sentence-transformers` model as `02_embed.py` — they must
# MAGIC match for vector similarity to work.

# COMMAND ----------

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

# COMMAND ----------

query_vector = embed_query(
    f"{topic}\n{category}"
)

# COMMAND ----------

with get_conn() as conn:

    with conn.cursor() as cur:

        cur.execute(
            """
            SELECT
                id,
                title,
                description,
                content,
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
                source_limit,
            ),
        )

        sources = cur.fetchall()


if not sources:

    raise RuntimeError(
        "No source articles with embeddings "
        "were found."
    )

print(
    f"Retrieved {len(sources)} "
    f"source articles."
)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Build source packet

# COMMAND ----------

source_packet_parts = []

for index, source in enumerate(
    sources,
    start=1,
):

    (
        source_id,
        title,
        description,
        content,
        canonical_url,
        published_at,
        similarity,
    ) = source

    source_packet_parts.append(
        f"""
SOURCE {index}

ID: {source_id}
TITLE: {title}
URL: {canonical_url}
PUBLISHED: {published_at}
RELEVANCE: {similarity:.4f}

CONTENT:
{content}
"""
    )


source_packet = "\n\n".join(
    source_packet_parts
)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Editorial prompt
# MAGIC
# MAGIC The prompt explicitly prevents invented facts and treats sources
# MAGIC as evidence rather than text to copy.

# COMMAND ----------

SYSTEM_PROMPT = """
You are an experienced Polish sports journalist.

Your job is to create an original sports article
using the supplied source material.

Rules:

1. Write in Polish.
2. Do not copy source articles verbatim.
3. Do not invent facts.
4. Do not invent quotations.
5. Do not present rumors as confirmed facts.
6. Clearly attribute uncertain information.
7. Pay attention to publication dates.
8. If sources conflict, acknowledge the uncertainty.
9. Do not fabricate statistics, transfers, injuries,
   lineups, dates or statements.
10. The article must be independently written.
11. Do not mention that you are an AI.
12. Do not claim that a source confirms something
    unless the source actually supports it.

Return JSON with:

{
  "title": "...",
  "subtitle": "...",
  "content": "...",
  "category": "...",
  "editorial_notes": "..."
}

The editorial_notes field is internal metadata for
the human editor and must mention important uncertainty,
rumors or conflicting source information.
"""

USER_PROMPT = f"""
TOPIC:
{topic}

CATEGORY:
{category}

TARGET LENGTH:
approximately {desired_length} words

SOURCE MATERIAL:
{source_packet}

Write the article now.
"""

# COMMAND ----------

# MAGIC %md
# MAGIC ## LLM generation
# MAGIC
# MAGIC Uses Databricks Foundation Models Serving, model from the
# MAGIC `generation_model` widget (OpenAI-compatible chat API).

# COMMAND ----------

def generate_article(
    system_prompt: str,
    user_prompt: str,
):

    response = requests.post(
        (
            f"{_workspace_url().rstrip('/')}"
            f"/serving-endpoints/{generation_model}/invocations"
        ),
        headers={
            "Authorization": (
                f"Bearer {_embedding_token()}"
            ),
            "Databricks-Context": "cache-control",
        },
        json={
            "messages": [
                {
                    "role": "system",
                    "content": system_prompt,
                },
                {
                    "role": "user",
                    "content": user_prompt,
                },
            ],
            "temperature": 0.7,
            "max_tokens": 2000,
        },
        timeout=600,
    )

    response.raise_for_status()

    content = (
        response.json()["choices"][0]
        ["message"]["content"]
    )

    content = content.strip()

    if content.startswith("```"):

        content = content.split(
            "\n",
            1,
        )[-1].rsplit(
            "```",
            1,
        )[0].strip()

    return json.loads(content)

# COMMAND ----------

article = generate_article(
    SYSTEM_PROMPT,
    USER_PROMPT,
)

required_fields = [
    "title",
    "subtitle",
    "content",
    "category",
    "editorial_notes",
]

for field in required_fields:

    if not article.get(field):

        raise ValueError(
            f"Generated article missing "
            f"field: {field}"
        )

# COMMAND ----------

# MAGIC %md
# MAGIC ## Persist generated article
# MAGIC
# MAGIC IMPORTANT:
# MAGIC
# MAGIC The status is hard-coded to `draft`.
# MAGIC
# MAGIC There is intentionally no parameter that can change this.

# COMMAND ----------

source_ids = [
    source[0]
    for source in sources
]

with get_conn() as conn:

    with conn.cursor() as cur:

        cur.execute(
            """
            INSERT INTO generated_articles (
                title,
                subtitle,
                content,
                category,
                status,
                generated_by,
                generation_topic,
                desired_length,
                editorial_notes,
                created_at,
                updated_at
            )
            VALUES (
                %s,
                %s,
                %s,
                %s,
                'draft',
                'editorial_agent',
                %s,
                %s,
                %s,
                NOW(),
                NOW()
            )
            RETURNING id
            """,
            (
                article["title"],
                article["subtitle"],
                article["content"],
                article["category"],
                topic,
                desired_length,
                article["editorial_notes"],
            ),
        )

        generated_article_id = (
            cur.fetchone()[0]
        )

        #
        # Store exactly which source articles
        # were used by the model.
        #

        for source_id in source_ids:

            cur.execute(
                """
                INSERT INTO generated_article_sources (
                    generated_article_id,
                    source_article_id,
                    similarity_score
                )
                VALUES (
                    %s,
                    %s,
                    (
                        SELECT
                            1 - (
                                embedding <=> %s::vector
                            )
                        FROM source_articles
                        WHERE id = %s
                    )
                )
                ON CONFLICT DO NOTHING
                """,
                (
                    generated_article_id,
                    source_id,
                    pg_vector(query_vector),
                    source_id,
                ),
            )

    conn.commit()


print(
    f"Created generated article "
    f"{generated_article_id}"
)

print(
    "Status: draft"
)

# COMMAND ----------

dbutils.notebook.exit(
    json.dumps(
        {
            "generated_article_id":
                generated_article_id,
            "status": "draft",
            "source_count":
                len(source_ids),
        }
    )
)