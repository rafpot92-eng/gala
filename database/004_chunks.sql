-- ============================================================
-- GALA / MECZYKI EDITORIAL PLATFORM
-- 004_chunks.sql
--
-- Chunk-level retrieval unit. Articles are chunked (~1,000 chars,
-- paragraph-aware) and each chunk is embedded with
-- intfloat/multilingual-e5-large (1024 dims). Retrieval in
-- 03/04 queries this table -> reranks -> the top chunks become
-- the labeled source material for generation.
-- ============================================================

CREATE TABLE IF NOT EXISTS source_article_chunks (
    id BIGSERIAL PRIMARY KEY,

    source_article_id BIGINT NOT NULL
        REFERENCES source_articles(id)
        ON DELETE CASCADE,

    chunk_index INTEGER NOT NULL,

    content TEXT NOT NULL,

    content_hash TEXT NOT NULL,

    -- intfloat/multilingual-e5-large = 1024
    embedding VECTOR(1024),

    embedding_model TEXT,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (source_article_id, chunk_index)
);


-- Vector similarity search over chunks.
CREATE INDEX IF NOT EXISTS
idx_source_article_chunks_embedding
ON source_article_chunks
USING hnsw (embedding vector_cosine_ops);

CREATE INDEX IF NOT EXISTS
idx_source_article_chunks_source
ON source_article_chunks(source_article_id);


-- ============================================================
-- PER-ARTICLE SOURCE OVERLAP (for 05_eval)
-- ============================================================

CREATE TABLE IF NOT EXISTS eval_runs (
    id BIGSERIAL PRIMARY KEY,

    run_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    sample_size INTEGER,

    avg_word_count NUMERIC,

    avg_source_overlap NUMERIC,

    avg_quality_score NUMERIC,

    rejection_rate NUMERIC,

    notes TEXT
);