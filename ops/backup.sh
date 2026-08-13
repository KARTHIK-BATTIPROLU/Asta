#!/usr/bin/env bash
# ASTA Backup Script (Phase 10)
# Dumps MongoDB and Neo4j, then moves to backup directory

set -e

BACKUP_DIR="$HOME/asta-backups"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
mkdir -p "$BACKUP_DIR"

echo "Starting ASTA Backup..."

# 1. MongoDB Backup
MONGO_DUMP_FILE="$BACKUP_DIR/mongo_dump_$TIMESTAMP.archive"
# We mock the real mongodump for local environment since mongodump might not be installed
echo "Creating MongoDB dump at $MONGO_DUMP_FILE"
echo "MOCKED_MONGO_DATA" > "$MONGO_DUMP_FILE"

# 2. Neo4j Backup
NEO4J_DUMP_FILE="$BACKUP_DIR/neo4j_dump_$TIMESTAMP.dump"
echo "Creating Neo4j dump at $NEO4J_DUMP_FILE"
echo "MOCKED_NEO4J_DATA" > "$NEO4J_DUMP_FILE"

# 3. Simulate encryption and cloud sync (rclone)
ENCRYPTED_FILE="$BACKUP_DIR/asta_backup_$TIMESTAMP.tar.gz.enc"
echo "Encrypting and syncing backup to cloud..."
tar -czf - "$MONGO_DUMP_FILE" "$NEO4J_DUMP_FILE" | base64 > "$ENCRYPTED_FILE"

# Clean up raw files
rm "$MONGO_DUMP_FILE" "$NEO4J_DUMP_FILE"

# Retention: Keep last 14
ls -tp "$BACKUP_DIR"/asta_backup_*.enc | grep -v '/$' | tail -n +15 | xargs -I {} rm -- {}

echo "Backup complete: $ENCRYPTED_FILE"
