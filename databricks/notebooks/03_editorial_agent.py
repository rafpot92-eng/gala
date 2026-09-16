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
    "Topic (blank = derive from last batch)",
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

dbutils.widgets.text(
    "batch_lookback_hours",
    "24",
    "Batch lookback hours",
)

dbutils.widgets.text(
    "max_topics",
    "3",
    "Max topics to derive",
)

dbutils.widgets.text(
    "max_articles",
    "3",
    "Approx articles per run",
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

batch_lookback_hours = int(
    dbutils.widgets.get(
        "batch_lookback_hours"
    )
)

max_topics = int(
    dbutils.widgets.get(
        "max_topics"
    )
)

max_articles = int(
    dbutils.widgets.get(
        "max_articles"
    )
)

# COMMAND ----------

import json
import os
from datetime import datetime, timezone
from urllib.parse import quote_plus, urlparse

import numpy as np

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

        # ponytail: workspaceUrl() was removed from the runtime
        # context API; browserHostName tag is the fallback.
        try:

            host = (
                dbutils.notebook
                .entry_point
                .getDbutils()
                .notebook()
                .getContext()
                .tags()
                .apply("browserHostName")
            )

            if host:

                return f"https://{host}"

        except Exception:

            pass

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

# COMMAND ----------

def parse_vector(
    value: str,
) -> np.ndarray:

    return np.array(
        value.strip("[]").split(","),
        dtype=np.float64,
    )


def kmeans(
    X: np.ndarray,
    k: int,
    seed: int = 42,
    iters: int = 50,
):

    rng = np.random.default_rng(seed)

    centroids = np.zeros(
        (k, X.shape[1])
    )

    centroids[0] = X[
        rng.integers(0, X.shape[0])
    ]

    for i in range(1, k):

        distances = (
            (X[:, None, :] - centroids[:i][None, :, :])
            ** 2
        ).sum(axis=-1).min(axis=-1)

        probabilities = (
            distances / distances.sum()
        )

        centroids[i] = X[
            rng.choice(
                X.shape[0],
                p=probabilities,
            )
        ]

    labels = np.zeros(
        X.shape[0],
        dtype=int,
    )

    for _ in range(iters):

        labels = (
            (X[:, None, :] - centroids[None, :, :])
            ** 2
        ).sum(axis=-1).argmin(axis=1)

        new_centroids = np.array([
            (
                X[labels == c].mean(axis=0)
                if (labels == c).any()
                else centroids[c]
            )
            for c in range(k)
        ])

        if np.allclose(
            new_centroids,
            centroids,
        ):

            break

        centroids = new_centroids

    return labels, centroids

# COMMAND ----------

# MAGIC %md
# MAGIC ## Topic selection
# MAGIC
# MAGIC If the `topic` widget is blank, derive topics from the last
# MAGIC batch of ingested articles with k-means on their embeddings.
# MAGIC Each cluster becomes one topic, seeded by the title of the
# MAGIC article nearest its centroid.
# MAGIC
# MAGIC Temperature of a topic = 0.5 * (cluster share of the batch)
# MAGIC + 0.5 * (mean recency of the cluster's articles). Hotter
# MAGIC topics get a larger share of the run's article budget.

# COMMAND ----------

topics = []

if topic:

    topics.append(
        (topic, 1)
    )

else:

    with get_conn() as conn:

        with conn.cursor() as cur:

            cur.execute(
                """
                SELECT
                    id,
                    title,
                    published_at,
                    embedding
                FROM source_articles
                WHERE embedding IS NOT NULL
                  AND ingested_at >= (
                      NOW() - (%s || ' hours')::interval
                  )
                """,
                (batch_lookback_hours,),
            )

            batch_rows = cur.fetchall()

    if not batch_rows:

        raise RuntimeError(
            "No embedded articles in the "
            "last batch."
        )

    matrix = np.vstack([
        parse_vector(row[3])
        for row in batch_rows
    ])

    k = min(
        max_topics,
        len(batch_rows),
    )

    labels, _ = kmeans(
        matrix,
        k,
    )

    now = datetime.now(
        timezone.utc
    )

    for cluster in range(k):

        indexes = np.where(
            labels == cluster
        )[0]

        if len(indexes) == 0:

            continue

        cluster_matrix = matrix[indexes]

        centroid = cluster_matrix.mean(
            axis=0
        )

        distances = (
            (cluster_matrix - centroid)
            ** 2
        ).sum(axis=1)

        representative = batch_rows[
            int(indexes[distances.argmin()])
        ]

        topic_label = representative[1]

        share = (
            len(indexes) / len(batch_rows)
        )

        hours_since_published = []

        for row_index in indexes:

            published = batch_rows[
                int(row_index)
            ][2]

            if published:

                hours_since_published.append(
                    max(
                        0.0,
                        (
                            now - published
                        ).total_seconds() / 3600.0,
                    )
                )

        if hours_since_published:

            average_hours = (
                sum(hours_since_published)
                / len(hours_since_published)
            )

            recency = 1.0 / (
                1.0 + average_hours
            )

        else:

            recency = 0.0

        temperature = (
            0.5 * share
            + 0.5 * recency
        )

        article_count = max(
            1,
            round(max_articles * temperature),
        )

        topics.append(
            (topic_label, article_count)
        )

    print(
        f"Derived {len(topics)} topics "
        f"from the last batch:"
    )

    for topic_label, article_count in topics:

        print(
            f"- {article_count}x "
            f"{topic_label!r}"
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

TODAY = datetime.now(
    timezone.utc
).date().isoformat()

SYSTEM_PROMPT += (
    f"\nToday's date is {TODAY}. "
    "Use it to judge how current the "
    "publication dates of the sources are.\n"
)

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

    last_error = None

    for _ in range(2):

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
                "temperature": 0.2,
                "max_tokens": 4000,
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

        try:

            return json.loads(content)

        except (
            json.JSONDecodeError,
            TypeError,
        ) as exc:

            last_error = exc

            print(
                "Model returned invalid JSON; "
                "retrying once."
            )

    raise RuntimeError(
        f"Model returned invalid JSON twice: "
        f"{last_error}"
    )

# COMMAND ----------

generated_article_ids = []

for topic_label, article_count in topics:

    print(
        f"Generating {article_count} article(s) "
        f"for topic: {topic_label!r}"
    )

    for _ in range(article_count):

        query_vector = embed_query(
            f"{topic_label}\n{category}"
        )

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

            print(
                "No source articles found for "
                "this topic; skipping."
            )

            continue

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

        user_prompt = f"""
TOPIC:
{topic_label}

CATEGORY:
{category}

TARGET LENGTH:
approximately {desired_length} words

SOURCE MATERIAL:
{source_packet}

Write the article now.
"""

        article = generate_article(
            SYSTEM_PROMPT,
            user_prompt,
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

        #
        # Persist as `draft` only. There is
        # intentionally no parameter that can
        # change this — humans approve/publish.
        #

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
                        topic_label,
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

                for source in sources:

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
                            %s
                        )
                        ON CONFLICT DO NOTHING
                        """,
                        (
                            generated_article_id,
                            source[0],
                            source[6],
                        ),
                    )

            conn.commit()

        generated_article_ids.append(
            generated_article_id
        )

        print(
            f"Created generated article "
            f"{generated_article_id} (draft)"
        )

if not generated_article_ids:

    raise RuntimeError(
        "No articles were generated."
    )

dbutils.notebook.exit(
    json.dumps(
        {
            "generated_article_ids":
                generated_article_ids,
            "status": "draft",
            "total": len(
                generated_article_ids
            ),
        }
    )
)