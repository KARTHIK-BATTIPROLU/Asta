#!/usr/bin/env bash
# Backs up MongoDB + Neo4j/Graphiti into a timestamped tarball under backups/,
# then proves the backup actually restores: loads it into scratch targets and
# asserts a known canary record survives the round trip. Exits nonzero on any
# failure. See scripts/backup_restore.py for the logical dump/restore -- this
# machine has no mongodump/neo4j-admin, and Neo4j is Aura-managed (no
# filesystem to run neo4j-admin against), so a driver-based JSON export/import
# is the form of backup that's actually runnable here.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

PYTHON=${PYTHON:-python}
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="backups/asta_backup_${TIMESTAMP}"
ARCHIVE="backups/asta_backup_${TIMESTAMP}.tar.gz"

mkdir -p "$BACKUP_DIR"

echo "--- Writing canary record (Mongo + Neo4j) ---"
CANARY_TAG=$("$PYTHON" scripts/backup_restore.py insert-canary | tail -1)
echo "canary tag: $CANARY_TAG"

echo "--- Dumping MongoDB ($BACKUP_DIR/mongo) ---"
"$PYTHON" scripts/backup_restore.py dump-mongo --out "$BACKUP_DIR/mongo"

echo "--- Dumping Neo4j/Graphiti ($BACKUP_DIR/neo4j) ---"
"$PYTHON" scripts/backup_restore.py dump-neo4j --out "$BACKUP_DIR/neo4j"

echo "--- Archiving ---"
tar -czf "$ARCHIVE" -C backups "asta_backup_${TIMESTAMP}"
rm -rf "$BACKUP_DIR"
echo "Backup written: $ARCHIVE ($(du -h "$ARCHIVE" | cut -f1))"

echo "--- Testing restore (scratch Mongo db + scratch Neo4j label) ---"
if "$PYTHON" scripts/backup_restore.py test-restore --archive "$ARCHIVE" --canary-tag "$CANARY_TAG"; then
  echo "[OK] backup restores: canary record survived the round trip"
  RESULT=0
else
  echo "[FAIL] backup restore did not reproduce the canary record"
  RESULT=1
fi

echo "--- Cleaning up canary record from the live stores ---"
"$PYTHON" scripts/backup_restore.py cleanup-canary --canary-tag "$CANARY_TAG"

exit $RESULT
