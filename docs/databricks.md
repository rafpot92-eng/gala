# Databricks

Databricks is responsible for the data and AI pipeline.

The project contains four primary notebooks.

```text
01_ingest
02_embed
03_editorial_agent
04_search
```

---

# Notebook 01 — Ingestion

Location:

```text
databricks/notebooks/01_ingest.py
```

Purpose:

```text
Meczyki
   ↓
discover new article URLs
   ↓
download HTML
   ↓
parse article
   ↓
extract metadata
   ↓
deduplicate
   ↓
Lakebase / Delta
```

The ingestion job is incremental.

It must not repeatedly ingest the same article.

The canonical external identifier should be the Meczyki article URL.

Example:

```text
https://www.meczyki.pl/newsy/...
```

The ingestion process should:

1. discover current article URLs
2. normalize URLs
3. check whether URL already exists
4. download only new articles
5. parse article content
6. calculate content hash
7. store article
8. record ingestion timestamp

---

# Notebook 02 — Embeddings

Location:

```text
databricks/notebooks/02_embed.py
```

Purpose:

```text
source articles
      ↓
clean text
      ↓
embedding model
      ↓
vector
      ↓
Lakebase pgvector
```

Only articles that don't have a current embedding need to be processed.

This makes the notebook incremental.

Pseudo-flow:

```python
articles = load_articles_without_embeddings()

for article in articles:
    vector = embed(article.text)
    save_embedding(article.id, vector)
```

---

# Notebook 03 — Editorial Agent

Location:

```text
databricks/notebooks/03_editorial_agent.py
```

The notebook accepts parameters:

```text
topic
category
desired_length
```

Example:

```text
topic = "Legia Warszawa transfery"
category = "Piłka nożna"
desired_length = 700
```

The agent performs:

```text
topic
  ↓
semantic retrieval
  ↓
source articles
  ↓
source verification
  ↓
LLM
  ↓
article draft
  ↓
generated_articles
```

The generated article is always inserted with:

```text
status = draft
```

Never:

```text
approved
```

Never:

```text
published
```

---

# Notebook 04 — Search

Location:

```text
databricks/notebooks/04_search.py
```

This notebook is used for:

* testing vector search
* evaluating retrieval quality
* debugging embeddings
* manually testing queries
* evaluating source relevance

Production application search should eventually call the same retrieval implementation through an API/service rather than duplicating retrieval logic.

---

# Jobs

The notebooks are executed through Databricks Jobs.

The repository contains:

```text
databricks/jobs/
```

with:

```text
hourly_ingestion.yml
embedding.yml
editorial_agent.yml
```

---

# Hourly ingestion job

The ingestion job should run approximately once per hour.

```text
every hour
     ↓
01_ingest
     ↓
discover articles
     ↓
only new articles
```

It does not regenerate existing articles.

---

# Embedding job

The embedding job can run after ingestion.

Recommended flow:

```text
01_ingest
    ↓
02_embed
```

The embedding job processes only records missing embeddings.

---

# Editorial agent job

The editorial agent should not automatically publish.

It can be triggered:

* manually
* from an orchestration job
* by an API
* from a future editorial scheduling interface

Parameters:

```text
topic
category
desired_length
```

Example:

```text
topic=Robert Lewandowski
category=Piłka nożna
desired_length=800
```

Result:

```text
generated_articles.status = draft
```

---

# Recommended production orchestration

```text
Hourly
   │
   ▼
01_ingest
   │
   ▼
02_embed
```

Editorial generation should be separate:

```text
Manual/API trigger
        │
        ▼
03_editorial_agent
        │
        ▼
generated_articles
        │
        ▼
draft
```

This separation prevents an ingestion failure from automatically creating editorial content.

---

# Databricks source code

Business logic should not live exclusively inside notebooks.

Notebooks should be thin orchestration layers.

For example:

```text
databricks/src/meczyki/discovery.py
databricks/src/meczyki/parser.py
databricks/src/editorial/agent.py
```

The notebook imports these modules.

This makes the code:

* testable
* reusable
* easier to deploy
* easier to maintain
* easier to review
