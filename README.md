# Meczyki Editorial Platform

AI-assisted sports editorial platform built around Databricks, Lakebase/PostgreSQL, FastAPI and Next.js.

The system:

1. Collects new articles from Meczyki.
2. Stores article metadata and content.
3. Prevents duplicate ingestion.
4. Generates embeddings.
5. Stores vectors in Lakebase/PostgreSQL with `pgvector`.
6. Retrieves relevant source material.
7. Generates original editorial drafts.
8. Stores generated articles in the database.
9. Sends generated articles through human review.
10. Records every human revision.
11. Requires approval before publication.
12. Restricts publishing to authorized users.
13. Maintains an audit trail.

## Editorial workflow

```text
draft
   │
   │ editor submits
   ▼
ready_for_review
   │
   ├──────── reject ────────► draft
   │
   │ approve
   ▼
approved
   │
   │ publisher
   ▼
published
```

AI-generated articles stop at:

```text
ready_for_review
```

The AI agent must never approve or publish its own article.

---

# Architecture

```text
                         ┌──────────────────┐
                         │     Meczyki      │
                         │      /newsy      │
                         └────────┬─────────┘
                                  │
                                  ▼
                         ┌──────────────────┐
                         │ Databricks Job    │
                         │ 01_ingest         │
                         └────────┬─────────┘
                                  │
                                  ▼
                         ┌──────────────────┐
                         │ Bronze / Silver   │
                         │ source_articles   │
                         └────────┬─────────┘
                                  │
                                  ▼
                         ┌──────────────────┐
                         │ 02_embed          │
                         └────────┬─────────┘
                                  │
                                  ▼
                         ┌──────────────────┐
                         │ Lakebase          │
                         │ PostgreSQL        │
                         │ + pgvector        │
                         └────────┬─────────┘
                                  │
                                  ▼
                         ┌──────────────────┐
                         │ 03_editorial      │
                         │ agent             │
                         └────────┬─────────┘
                                  │
                                  ▼
                         generated_articles
                              status=draft
                                  │
                                  ▼
                         ┌──────────────────┐
                         │ FastAPI           │
                         └────────┬─────────┘
                                  │
                                  ▼
                         ┌──────────────────┐
                         │ Next.js           │
                         │ Editorial UI      │
                         └────────┬─────────┘
                                  │
                            Human editor
                                  │
                         ┌────────┴─────────┐
                         │                  │
                       reject             approve
                         │                  │
                         ▼                  ▼
                       draft             approved
                                            │
                                            │ publisher
                                            ▼
                                         published
```

---

# Components

## Databricks

Databricks performs:

* article discovery
* HTML parsing
* metadata extraction
* deduplication
* text normalization
* embedding generation
* semantic retrieval
* AI article generation
* scheduled execution

## Lakebase

Lakebase/PostgreSQL stores:

* source articles
* article metadata
* embeddings
* generated articles
* revisions
* users
* audit events

## FastAPI

FastAPI provides:

* authentication
* authorization
* article API
* editorial workflow
* revision persistence
* search
* audit logging

## Next.js

Next.js provides:

* dashboard
* article list
* article editor
* review screen
* source panel
* search
* authentication UI

---

# Development

See:

`docs/development.md`

# Databricks

See:

`docs/databricks.md`

# Database

See:

`docs/database.md`

# Editorial agent

See:

`docs/editorial-agent.md`

# Deployment

See:

`docs/deployment.md`
