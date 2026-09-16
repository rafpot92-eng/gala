# Databricks notebook source

# MAGIC %md
# MAGIC # 03 — Editorial Agent
# MAGIC
# MAGIC Generates editorial draft articles from Meczyki source material.
# MAGIC
# MAGIC Flow:
# MAGIC
# MAGIC     topic selection (widget or cluster-derived)
# MAGIC         ↓
# MAGIC     chunk retrieval → cross-encoder rerank → dedupe
# MAGIC         ↓
# MAGIC     extract facts from labeled chunks
# MAGIC         ↓
# MAGIC     write article from fact sheet
# MAGIC         ↓
# MAGIC     critique: check grounding vs facts, revise if critical
# MAGIC         ↓
# MAGIC     persist as draft
# MAGIC
# MAGIC The status is hard-coded to `draft`. Humans approve/publish.

# COMMAND ----------

# MAGIC %pip uninstall -y psycopg2 psycopg2-binary
# MAGIC %pip install \
# MAGIC   sentence-transformers

# COMMAND ----------

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
    "Desired article length (words)",
)

dbutils.widgets.text(
    "source_limit",
    "8",
    "Chunks to send to the writer",
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


def parse_vector(value):

    return np.array(
        value.strip("[]").split(","),
        dtype=np.float64,
    )

# COMMAND ----------

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
# MAGIC ## Embedding + reranking
# MAGIC
# MAGIC E5-large for retrieval embeddings (1024 dims, multilingual).
# MAGIC Cross-encoder `bge-reranker-v2-m3` for reranking top candidates.

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

RERANKER = CrossEncoder(
    "BAAI/bge-reranker-v2-m3"
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

# COMMAND ----------

# MAGIC %md
# MAGIC ## Topic selection
# MAGIC
# MAGIC If the `topic` widget is blank, cluster articles from the last
# MAGIC batch by their mean chunk embeddings and derive topics + a
# MAGIC temperature-weighted article count per topic.

# COMMAND ----------


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
                    a.id,
                    a.title,
                    a.published_at,
                    AVG(c.embedding) AS mean_emb
                FROM source_articles a
                JOIN source_article_chunks c
                    ON c.source_article_id = a.id
                WHERE c.embedding IS NOT NULL
                  AND a.ingested_at >= (
                      NOW() - (%s || ' hours')::interval
                  )
                GROUP BY
                    a.id, a.title, a.published_at
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

    labels, _ = kmeans(matrix, k)

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
            (cluster_matrix - centroid) ** 2
        ).sum(axis=1)

        rep = batch_rows[
            int(indexes[distances.argmin()])
        ]

        topic_label = rep[1]

        share = (
            len(indexes) / len(batch_rows)
        )

        hours_since = []

        for ri in indexes:

            published = batch_rows[int(ri)][2]

            if published:

                hours_since.append(
                    max(
                        0.0,
                        (
                            now - published
                        ).total_seconds() / 3600.0,
                    )
                )

        avg_hours = (
            sum(hours_since) / len(hours_since)
            if hours_since
            else 0.0
        )

        recency = 1.0 / (1.0 + avg_hours)

        temperature = (
            0.5 * share + 0.5 * recency
        )

        count = max(
            1,
            round(max_articles * temperature),
        )

        topics.append(
            (topic_label, count)
        )

    print(
        f"Derived {len(topics)} topics "
        f"from the last batch:"
    )

    for tl, cnt in topics:

        print(f"- {cnt}x {tl!r}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Retrieval

# COMMAND ----------

RERANK_CANDIDATES = 50


def retrieve_chunks(
    query_text,
    query_vector,
    limit=source_limit,
):

    with get_conn() as conn:

        with conn.cursor() as cur:

            cur.execute(
                """
                SELECT
                    c.id,
                    c.source_article_id,
                    c.chunk_index,
                    c.content,
                    c.embedding,
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
                LIMIT %s
                """,
                (
                    pg_vector(query_vector),
                    pg_vector(query_vector),
                    RERANK_CANDIDATES,
                ),
            )

            candidates = cur.fetchall()

    if not candidates:

        return []

    pairs = [
        (query_text, row[3])
        for row in candidates
    ]

    scores = RERANKER.predict(pairs)

    ranked = sorted(
        zip(candidates, scores),
        key=lambda x: x[1],
        reverse=True,
    )

    selected = []
    seen = []

    for row, score in ranked:

        is_dup = False

        for prev in seen:

            vec_a = parse_vector(row[4])
            vec_b = parse_vector(prev)

            cos = (
                float(np.dot(vec_a, vec_b))
                / (
                    float(np.linalg.norm(vec_a))
                    * float(np.linalg.norm(vec_b))
                    + 1e-10
                )
            )

            if cos > 0.95:

                is_dup = True
                break

        if is_dup:

            continue

        selected.append(
            (row, float(score))
        )

        seen.append(row[4])

        if len(selected) >= limit:

            break

    return selected


def build_packet(
    reranked_chunks,
) -> str:

    parts = []

    for i, (row, score) in enumerate(
        reranked_chunks, start=1
    ):

        parts.append(
            f"SOURCE S{i}\n"
            f"ARTICLE: {row[5]}\n"
            f"URL: {row[6]}\n"
            f"PUBLISHED: {row[7]}\n"
            f"RELEVANCE: {float(row[8]):.4f}\n\n"
            f"{row[3]}"
        )

    return "\n\n".join(parts)

# COMMAND ----------

# MAGIC %md
# MAGIC ## LLM generation
# MAGIC
# MAGIC Single `generate()` function used for extract / write / critique.
# MAGIC Retries once on JSON parse failure, returning a clear error on
# MAGIC second failure.

# COMMAND ----------

import requests


def _extract_content(response_json):
    try:

        return (
            response_json["choices"][0]
            ["message"]["content"]
        )

    except (KeyError, IndexError, TypeError):

        try:

            return response_json[
                "predictions"
            ][0]

        except (KeyError, IndexError, TypeError):

            return str(response_json)


def generate(
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.2,
    max_tokens: int = 4000,
):

    last_error = None

    for attempt in range(2):

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
                "temperature": temperature,
                "max_tokens": max_tokens,
            },
            timeout=600,
        )

        response.raise_for_status()

        payload = response.json()

        content = _extract_content(payload)

        if content is None:

            last_error = ValueError(
                "Model returned null content"
            )

            print(
                f"ATTEMPT {attempt + 1}: model "
                "returned null content.\n"
                f"Full response headers: "
                f"{response.headers}\n"
                f"Full response body: "
                f"{json.dumps(payload)[:2000]}\n"
                "Retrying once."
            )

            continue

        content = content.strip()

        if "```" in content:

            parts = content.split("```")

            if len(parts) >= 3:

                content = parts[1].strip()

                if content.startswith(
                    ("json", "JSON")
                ):

                    content = content.split(
                        "\n", 1
                    )[-1].strip()

        if not content:

            last_error = ValueError(
                "Empty response from model"
            )

            print(
                f"ATTEMPT {attempt + 1}: model "
                "returned empty response.\n"
                f"Full response body: "
                f"{json.dumps(payload)[:2000]}\n"
                "Retrying once."
            )

            continue

        try:

            return json.loads(content)

        except (
            json.JSONDecodeError,
            TypeError,
        ) as exc:

            last_error = exc

            print(
                f"ATTEMPT {attempt + 1}: model "
                "returned invalid JSON; "
                "retrying once.\n"
                f"Raw response (first 500 chars): "
                f"{content[:500]}"
            )

    raise RuntimeError(
        f"Model returned invalid JSON twice: "
        f"{last_error}"
    )

# COMMAND ----------

TODAY = datetime.now(
    timezone.utc
).date().isoformat()

# COMMAND ----------

EXTRACT_SYSTEM = (
    "You are a factual extraction assistant.\n"
    "\n"
    "Given labeled source chunks, extract the key\n"
    "facts relevant to the topic. Each fact must\n"
    "reference its source label (S1, S2, ...).\n"
    "\n"
    "Output JSON:\n"
    '{"facts": [{"fact": "...", "source": "S1"}]}\n'
    "\n"
    "Rules:\n"
    "- Extract only facts, not opinions.\n"
    "- Use the exact source label.\n"
    "- Include dates, names, scores, and specific\n"
    "  details when present.\n"
    "- Do not add facts not in the sources.\n"
)

WRITE_SYSTEM = (
    "You are an experienced Polish sports journalist.\n"
    "\n"
    "Write an original article from the supplied\n"
    "fact sheet and topic.\n"
    "\n"
    "Rules:\n"
    "\n"
    "1. Write in Polish.\n"
    "2. Every factual claim must be in the fact sheet.\n"
    "3. Do not invent facts, quotes, or statistics.\n"
    "4. Do not present rumors as confirmed.\n"
    "5. Clearly attribute uncertain information.\n"
    "6. If facts conflict, acknowledge the uncertainty.\n"
    "7. Structure: strong lede, 2-3 detail sections,\n"
    "   closing. Avoid generic AI filler phrases\n"
    '   ("W zaskakującym rozwoju sytuacji",\n'
    '    "Warto zauważyć").\n'
    "8. Do not mention you are an AI.\n"
    f"9. Target length: approximately {desired_length} words.\n"
    "\n"
    "Return JSON:\n"
    "{\n"
    '  "title": "...",\n'
    '  "subtitle": "...",\n'
    '  "content": "...",\n'
    '  "category": "...",\n'
    '  "editorial_notes": "Internal notes for the human editor. Mention uncertainty, conflicting facts, and gaps in the source material."\n'
    "}\n"
    "\n"
    f"Today's date is {TODAY}. Use it to judge\n"
    "how current the publication dates of the\n"
    "sources are.\n"
)

CRITIQUE_SYSTEM = (
    "You are a sports journalism fact-checker.\n"
    "\n"
    "Review the article against the source facts.\n"
    "For each issue, return an issue object.\n"
    "\n"
    "Output JSON:\n"
    '{"issues": [{"type": "hallucination",\n'
    '  "description": "...",\n'
    '  "severity": "critical"}]}\n'
    "\n"
    "Severity: critical = must fix (hallucination,\n"
    "contradiction), minor = polish (redundancy,\n"
    "fluff, style).\n"
    "\n"
    "Rules:\n"
    "- Check factual grounding: does every claim\n"
    "  trace to at least one source fact?\n"
    "- Check for invented details.\n"
    "- Check for redundancy and fluff.\n"
)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Validation

# COMMAND ----------

REQUIRED_FIELDS = [
    "title",
    "subtitle",
    "content",
    "category",
    "editorial_notes",
]


def validate_article(article):

    errors = []

    for field in REQUIRED_FIELDS:

        if not article.get(field):

            errors.append({
                "type": "missing_field",
                "description": (
                    f"Missing field: {field}"
                ),
                "severity": "critical",
            })

    content = article.get("content", "")

    if content and len(content.split()) < 150:

        errors.append({
            "type": "short_content",
            "description": (
                "Article under 150 words"
            ),
            "severity": "critical",
        })

    title = article.get("title", "")

    if title and len(title) > 150:

        errors.append({
            "type": "long_title",
            "description": (
                f"Title is {len(title)} chars"
            ),
            "severity": "minor",
        })

    return errors

# COMMAND ----------

# MAGIC %md
# MAGIC ## Generation loop

# COMMAND ----------

CRITIQUE_MAX_ROUNDS = 2

generated_article_ids = []

for topic_label, article_count in topics:

    print(
        f"Generating {article_count} article(s) "
        f"for: {topic_label!r}"
    )

    for _ in range(article_count):

        query_vector = embed_query(
            f"{topic_label}\n{category}"
        )

        query_text = (
            f"{topic_label}\n{category}"
        )

        reranked = retrieve_chunks(
            query_text,
            query_vector,
            limit=source_limit,
        )

        if not reranked:

            print(
                "No chunks found; skipping."
            )

            continue

        packet = build_packet(reranked)

        # ---- extract facts ----

        facts = generate(
            EXTRACT_SYSTEM,
            f"TOPIC: {topic_label}\n"
            f"CATEGORY: {category}\n\n"
            f"{packet}",
            temperature=0.1,
        )

        facts_list = (
            facts.get("facts", [])
            if isinstance(facts, dict)
            else []
        )

        # ---- write article ----

        article = generate(
            WRITE_SYSTEM,
            "FACTS:\n"
            + json.dumps(
                facts_list,
                ensure_ascii=False,
                indent=2,
            )
            + f"\n\nTOPIC: {topic_label}\n"
            f"CATEGORY: {category}\n"
            f"TARGET LENGTH: approximately "
            f"{desired_length} words\n",
            temperature=0.4,
        )

        # ---- critique + revise ----

        for _ in range(CRITIQUE_MAX_ROUNDS):

            issues = validate_article(article)

            issues_resp = generate(
                CRITIQUE_SYSTEM,
                f"TOPIC: {topic_label}\n\n"
                "ARTICLE:\n"
                + json.dumps(
                    article,
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n\nFACTS:\n"
                + json.dumps(
                    facts_list,
                    ensure_ascii=False,
                    indent=2,
                ),
            )

            critique_issues = (
                issues_resp.get("issues", [])
                if isinstance(issues_resp, dict)
                else []
            )

            issues.extend([
                i for i in critique_issues
                if i.get("severity") == "critical"
            ])

            if not issues:

                break

            print(
                f"  {len(issues)} issue(s) — "
                f"revising."
            )

            article = generate(
                WRITE_SYSTEM
                + "\n\nPrevious version had "
                "issues:\n"
                + json.dumps(
                    [
                        i["description"]
                        for i in issues
                    ],
                    ensure_ascii=False,
                )
                + "\nFix these. Do not introduce "
                "new hallucinations.\n",
                "FACTS:\n"
                + json.dumps(
                    facts_list,
                    ensure_ascii=False,
                    indent=2,
                )
                + f"\n\nTOPIC: {topic_label}\n"
                f"CATEGORY: {category}\n"
                f"TARGET LENGTH: approximately "
                f"{desired_length} words\n",
                temperature=0.4,
            )

        errors = validate_article(article)

        if errors:

            raise ValueError(
                "Article failed validation "
                f"after revision: {errors}"
            )

        # ---- persist (draft only) ----

        with get_conn() as conn:

            with conn.cursor() as cur:

                cur.execute(
                    """
                    INSERT INTO generated_articles (
                        title, subtitle, content,
                        category, status,
                        generated_by,
                        generation_topic,
                        desired_length,
                        editorial_notes,
                        created_at, updated_at
                    )
                    VALUES (
                        %s, %s, %s,
                        %s, 'draft',
                        'editorial_agent',
                        %s,
                        %s,
                        %s,
                        NOW(), NOW()
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

                new_id = cur.fetchone()[0]

                source_map = {}

                for row, _ in reranked:

                    sa_id = row[1]
                    sim = float(row[8])

                    source_map[sa_id] = max(
                        source_map.get(sa_id, 0),
                        sim,
                    )

                for sa_id, sim in (
                    source_map.items()
                ):

                    cur.execute(
                        """
                        INSERT INTO generated_article_sources (
                            generated_article_id,
                            source_article_id,
                            similarity_score
                        )
                        VALUES (%s, %s, %s)
                        ON CONFLICT DO NOTHING
                        """,
                        (new_id, sa_id, sim),
                    )

            conn.commit()

        generated_article_ids.append(new_id)

        print(
            f"  Created {new_id} (draft)"
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