# scripts/backup.sh
# Резервное копирование: PostgreSQL + Qdrant + Neo4j

set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-/data/backups}"
DATE=$(date +%Y%m%d_%H%M)
mkdir -p "$BACKUP_DIR"

echo "🔄 Starting backup: $DATE"

# PostgreSQL
echo "📦 Dumping PostgreSQL..."
docker-compose exec -T postgres pg_dump -U agent devops_memory \
  | gzip > "$BACKUP_DIR/pg_devops_$DATE.sql.gz"

# Qdrant snapshot
echo "📦 Snapshotting Qdrant..."
curl -X POST "http://localhost:6333/collections/devops_errors/snapshots" \
  -H "Content-Type: application/json" \
  -d '{"wait": true}' | jq -r '.result.name' | \
  xargs -I {} cp "/var/lib/qdrant/snapshots/devops_errors/{}" "$BACKUP_DIR/qdrant_$DATE.snapshot"

# Neo4j backup (через neo4j-admin)
echo "📦 Backing up Neo4j..."
docker-compose exec -T neo4j neo4j-admin database backup devops_memory \
  --to-path=/backups --verbose || true  # Community edition ограничивает

# Очистка старых бэкапов (>7 дней)
find "$BACKUP_DIR" -name "*.gz" -mtime +7 -delete
find "$BACKUP_DIR" -name "*.snapshot" -mtime +7 -delete

echo "✓ Backup complete: $BACKUP_DIR"
ls -lh "$BACKUP_DIR" | tail -5

