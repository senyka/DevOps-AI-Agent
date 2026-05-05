### `init/02_indexes.sql`
```sql
-- init/02_indexes.sql
-- Дополнительные индексы для производительности

-- Быстрый поиск по проекту + статусу
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_error_project_status 
ON error_cases (project, status) WHERE status = 'success';

-- Частые запросы по дате
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_error_created 
ON error_cases (created_at DESC) WHERE consolidated = false;

-- Аудит: поиск по метаданным
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_audit_metadata 
ON audit_log USING GIN ((metadata->'project'));

-- Оптимизация для pgvector (если используется для эмбеддингов в PG)
-- CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_error_embedding 
-- ON error_cases USING hnsw (embedding vector_cosine_ops) 
-- WITH (m=16, ef_construction=64);

-- Statistics update
ANALYZE error_cases;
ANALYZE audit_log;
ANALYZE lora_versions;
```

---
