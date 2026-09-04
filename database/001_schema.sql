-- ============================================================
-- GALA / MECZYKI EDITORIAL PLATFORM
-- 001_schema.sql
--
-- Lakebase operational schema
-- ============================================================

CREATE EXTENSION IF NOT EXISTS vector;


-- ============================================================
-- USERS
-- ============================================================

CREATE TABLE IF NOT EXISTS users (
    id BIGSERIAL PRIMARY KEY,

    email TEXT NOT NULL UNIQUE,
    name TEXT,

    role TEXT NOT NULL DEFAULT 'viewer'
        CHECK (
            role IN (
                'viewer',
                'editor',
                'publisher'
            )
        ),

    is_active BOOLEAN NOT NULL DEFAULT TRUE,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


-- ============================================================
-- SOURCE ARTICLES
--
-- Raw/parsed articles coming from Meczyki.
-- This is the operational source store used by
-- ingestion -> embedding -> retrieval.
-- ============================================================

CREATE TABLE IF NOT EXISTS source_articles (
    id BIGSERIAL PRIMARY KEY,

    canonical_url TEXT NOT NULL UNIQUE,

    source_name TEXT NOT NULL,

    title TEXT NOT NULL,
    description TEXT,
    image_url TEXT,

    published_at TIMESTAMPTZ,

    content TEXT NOT NULL,

    content_hash TEXT NOT NULL,

    -- databricks-gte-large-en = 1024 dimensions
    embedding VECTOR(1024),

    embedding_model TEXT,

    embedding_content_hash TEXT,

    embedding_created_at TIMESTAMPTZ,

    ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


-- ============================================================
-- GENERATED ARTICLES
-- ============================================================

CREATE TABLE IF NOT EXISTS generated_articles (
    id BIGSERIAL PRIMARY KEY,

    title TEXT NOT NULL,
    subtitle TEXT,

    content TEXT NOT NULL,

    category TEXT,

    status TEXT NOT NULL DEFAULT 'draft'
        CHECK (
            status IN (
                'draft',
                'ready_for_review',
                'approved',
                'published'
            )
        ),

    word_count INTEGER,

    generated_by TEXT,
    generation_topic TEXT,
    desired_length INTEGER,
    editorial_notes TEXT,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    published_at TIMESTAMPTZ,

    version INTEGER NOT NULL DEFAULT 1
);


-- ============================================================
-- GENERATED ARTICLE <-> SOURCE ARTICLE
--
-- Records exactly which source articles were used
-- to generate an editorial article.
-- ============================================================

CREATE TABLE IF NOT EXISTS generated_article_sources (
    generated_article_id BIGINT NOT NULL
        REFERENCES generated_articles(id)
        ON DELETE CASCADE,

    source_article_id BIGINT NOT NULL
        REFERENCES source_articles(id)
        ON DELETE RESTRICT,

    similarity_score DOUBLE PRECISION,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    PRIMARY KEY (
        generated_article_id,
        source_article_id
    )
);


-- ============================================================
-- ARTICLE REVISIONS
-- ============================================================

CREATE TABLE IF NOT EXISTS article_revisions (
    id BIGSERIAL PRIMARY KEY,

    article_id BIGINT NOT NULL
        REFERENCES generated_articles(id)
        ON DELETE CASCADE,

    revision_number INTEGER NOT NULL,

    title TEXT NOT NULL,
    subtitle TEXT,
    content TEXT NOT NULL,

    editor_id BIGINT
        REFERENCES users(id)
        ON DELETE SET NULL,

    change_summary TEXT,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (
        article_id,
        revision_number
    )
);


-- ============================================================
-- EDITORIAL AUDIT LOG
-- ============================================================

CREATE TABLE IF NOT EXISTS editorial_audit_log (
    id BIGSERIAL PRIMARY KEY,

    article_id BIGINT
        REFERENCES generated_articles(id)
        ON DELETE SET NULL,

    job_id BIGINT,

    action TEXT NOT NULL,

    old_status TEXT,
    new_status TEXT,

    actor_id BIGINT
        REFERENCES users(id)
        ON DELETE SET NULL,

    notes TEXT,

    metadata JSONB,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);