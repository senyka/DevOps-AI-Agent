### `init/01_schema.sql`
```sql
-- init/01_schema.sql
-- PostgreSQL schema для DevOps Agent

-- Таблица кейсов ошибок
CREATE TABLE IF NOT EXISTS error_cases (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    signature TEXT NOT NULL,
    stacktrace TEXT,
    context JSONB DEFAULT '{}'::jsonb,
    fix_steps TEXT[],
    validation_cmd TEXT,
    rollback_cmd TEXT,
    project TEXT,
    status TEXT CHECK (status IN ('pending', 'success', 'failed', 'deprecated')),
    confidence FLOAT CHECK (confidence >= 0 AND confidence <= 1),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    consolidated BOOLEAN DEFAULT FALSE
);

-- Полнотекстовый поиск
ALTER TABLE error_cases ADD COLUMN IF NOT EXISTS search_vector tsvector;
CREATE INDEX IF NOT EXISTS idx_error_search ON error_cases USING GIN(search_vector);
CREATE INDEX IF NOT EXISTS idx_error_signature ON error_cases USING GIN(signature gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_error_project ON error_cases (project);
CREATE INDEX IF NOT EXISTS idx_error_status ON error_cases (status, created_at DESC);

-- Триггер для обновления search_vector
CREATE OR REPLACE FUNCTION update_search_vector() RETURNS trigger AS $$
BEGIN
  NEW.search_vector := 
    setweight(to_tsvector('russian', COALESCE(NEW.signature, '')), 'A') ||
    setweight(to_tsvector('russian', COALESCE(NEW.stacktrace, '')), 'B') ||
    setweight(to_tsvector('russian', COALESCE(array_to_string(NEW.fix_steps, ' '), '')), 'C');
  RETURN NEW;
END $$ LANGUAGE plpgsql;

CREATE TRIGGER trg_update_search_vector
BEFORE INSERT OR UPDATE ON error_cases
FOR EACH ROW EXECUTE FUNCTION update_search_vector();

-- Триггер для updated_at
CREATE OR REPLACE FUNCTION update_updated_at() RETURNS trigger AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END $$ LANGUAGE plpgsql;

CREATE TRIGGER trg_update_timestamp
BEFORE UPDATE ON error_cases
FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- Таблица аудита
CREATE TABLE IF NOT EXISTS audit_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    audit_id TEXT UNIQUE NOT NULL,
    input_data JSONB NOT NULL,
    output_data JSONB NOT NULL,
    metadata JSONB DEFAULT '{}'::jsonb,
    confidence FLOAT,
    execution_time FLOAT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_audit_id ON audit_log (audit_id);
CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_log (created_at DESC);

-- Таблица версий LoRA
CREATE TABLE IF NOT EXISTS lora_versions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT UNIQUE NOT NULL,
    path TEXT NOT NULL,
    base_model TEXT NOT NULL,
    metrics JSONB,
    status TEXT CHECK (status IN ('training', 'validating', 'deployed', 'rolled_back')),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    deployed_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_lora_status ON lora_versions (status);

-- LangGraph чекпоинты (создаются автоматически через AsyncPostgresSaver.setup())
-- Но можно предсоздать для контроля:
CREATE TABLE IF NOT EXISTS checkpoints (
    thread_id TEXT NOT NULL,
    checkpoint_id TEXT NOT NULL,
    parent_id TEXT,
    checkpoint BYTEA NOT NULL,
    metadata JSONB,
    PRIMARY KEY (thread_id, checkpoint_id)
);
```

---
