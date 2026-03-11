CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TABLE IF NOT EXISTS documents (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  building_id TEXT NOT NULL DEFAULT 'palace_of_fine_arts',
  source_id TEXT NOT NULL UNIQUE,
  title TEXT NOT NULL,
  url TEXT NOT NULL,
  license TEXT,
  fetched_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW(),
  raw_text TEXT
);

CREATE TABLE IF NOT EXISTS chunks (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  chunk_index INT NOT NULL,
  content TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  metadata JSONB DEFAULT '{}'::jsonb,
  UNIQUE(document_id, chunk_index)
);

CREATE TABLE IF NOT EXISTS embeddings (
  chunk_id UUID PRIMARY KEY REFERENCES chunks(id) ON DELETE CASCADE,
  embedding vector(3072) NOT NULL,
  model TEXT NOT NULL,
  created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS hotspots (
  building_id TEXT NOT NULL DEFAULT 'palace_of_fine_arts',
  id TEXT NOT NULL,
  name TEXT NOT NULL,
  description TEXT,
  tags TEXT[] DEFAULT ARRAY[]::TEXT[],
  bbox JSONB,
  camera JSONB,
  priority INT DEFAULT 0,
  mesh_names TEXT[] DEFAULT ARRAY[]::TEXT[],
  PRIMARY KEY (building_id, id)
);

CREATE TABLE IF NOT EXISTS buildings (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  location TEXT NOT NULL,
  description TEXT NOT NULL,
  model_url TEXT NOT NULL,
  hotspots_file TEXT NOT NULL,
  suggested_prompts JSONB DEFAULT '[]'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_chunks_document_id ON chunks(document_id);
CREATE INDEX IF NOT EXISTS idx_chunks_metadata_gin ON chunks USING GIN(metadata);
CREATE INDEX IF NOT EXISTS idx_embeddings_vector_hnsw ON embeddings USING hnsw (embedding vector_l2_ops);
CREATE INDEX IF NOT EXISTS idx_documents_building_id ON documents(building_id);
