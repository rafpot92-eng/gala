CREATE EXTENSION IF NOT EXISTS vector;


-- =========================================================
-- USERS
-- =========================================================

CREATE TABLE IF NOT EXISTS users (
    id BIGSERIAL PRIMARY KEY,

    email TEXT NOT NULL UNIQUE,

    name TEXT,

    role TEXT NOT NULL
        CHECK (
            role IN (
                'viewer',
                'editor',
                'publisher'
            )
        ),

    is_active BOOLEAN NOT NULL DEFAULT TRUE,

    created_at TIMESTAMPTZ
        NOT NULL DEFAULT NOW(),

    updated_at TIMESTAMPTZ
        NOT NULL DEFAULT NOW()
);


-- =========================================================
-- GENERATED ARTICLES
--
-- If you already have this table from the Databricks project,
-- DO NOT recreate it. Run the ALTER statements below instead.
-- =========================================================

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

    embedding VECTOR(1536),

    created_at TIMESTAMPTZ
        NOT NULL DEFAULT NOW(),

    updated_at TIMESTAMPTZ
        NOT NULL DEFAULT NOW(),

    published_at TIMESTAMPTZ,

    version INTEGER NOT NULL DEFAULT 1
);


-- =========================================================
-- ARTICLE REVISIONS
-- =========================================================

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
        REFERENCES users(id),

    change_summary TEXT,

    created_at TIMESTAMPTZ
        NOT NULL DEFAULT NOW(),

    UNIQUE (
        article_id,
        revision_number
    )
);


-- =========================================================
-- AUDIT LOG
-- =========================================================

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

    created_at TIMESTAMPTZ
        NOT NULL DEFAULT NOW()
);


-- =========================================================
-- INDEXES
-- =========================================================

CREATE INDEX IF NOT EXISTS
idx_generated_articles_status
ON generated_articles(status);

CREATE INDEX IF NOT EXISTS
idx_generated_articles_created
ON generated_articles(created_at DESC);

CREATE INDEX IF NOT EXISTS
idx_article_revisions_article
ON article_revisions(article_id);

CREATE INDEX IF NOT EXISTS
idx_article_revisions_created
ON article_revisions(created_at DESC);

CREATE INDEX IF NOT EXISTS
idx_audit_article
ON editorial_audit_log(article_id);

CREATE INDEX IF NOT EXISTS
idx_audit_created
ON editorial_audit_log(created_at DESC);


-- =========================================================
-- VECTOR SEARCH
-- =========================================================

CREATE INDEX IF NOT EXISTS
idx_generated_articles_embedding
ON generated_articles
USING hnsw (embedding vector_cosine_ops);


-- =========================================================
-- DEVELOPMENT USER
-- =========================================================

INSERT INTO users (
    email,
    name,
    role
)
VALUES (
    'editor@example.com',
    'Demo Editor',
    'editor'
)
ON CONFLICT (email)
DO NOTHING;


INSERT INTO users (
    email,
    name,
    role
)
VALUES (
    'publisher@example.com',
    'Demo Publisher',
    'publisher'
)
ON CONFLICT (email)
DO NOTHING;