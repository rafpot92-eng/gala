-- ============================================================
-- GALA / MECZYKI EDITORIAL PLATFORM
-- 002_indexes.sql
-- ============================================================


-- ============================================================
-- SOURCE ARTICLES
-- ============================================================

CREATE INDEX IF NOT EXISTS idx_source_articles_published
ON source_articles(published_at DESC);

CREATE INDEX IF NOT EXISTS idx_source_articles_ingested
ON source_articles(ingested_at DESC);

CREATE INDEX IF NOT EXISTS idx_source_articles_source
ON source_articles(source_name);

CREATE INDEX IF NOT EXISTS idx_source_articles_embedding_pending
ON source_articles(id)
WHERE embedding IS NULL;


-- Vector similarity search.
--
-- For now we use pgvector's HNSW index.
-- We can later switch to Lakebase Search's lakebase_ann
-- if we enable Lakebase Search.
-- ============================================================

CREATE INDEX IF NOT EXISTS idx_source_articles_embedding
ON source_articles
USING hnsw (embedding vector_cosine_ops);


-- ============================================================
-- GENERATED ARTICLES
-- ============================================================

CREATE INDEX IF NOT EXISTS idx_generated_articles_status
ON generated_articles(status);

CREATE INDEX IF NOT EXISTS idx_generated_articles_created
ON generated_articles(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_generated_articles_category
ON generated_articles(category);


-- ============================================================
-- GENERATED ARTICLE SOURCES
-- ============================================================

CREATE INDEX IF NOT EXISTS idx_generated_article_sources_source
ON generated_article_sources(source_article_id);


-- ============================================================
-- ARTICLE REVISIONS
-- ============================================================

CREATE INDEX IF NOT EXISTS idx_article_revisions_article
ON article_revisions(article_id);

CREATE INDEX IF NOT EXISTS idx_article_revisions_created
ON article_revisions(created_at DESC);


-- ============================================================
-- AUDIT LOG
-- ============================================================

CREATE INDEX IF NOT EXISTS idx_audit_article
ON editorial_audit_log(article_id);

CREATE INDEX IF NOT EXISTS idx_audit_created
ON editorial_audit_log(created_at DESC);