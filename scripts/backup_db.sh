#!/bin/bash
set -euo pipefail
# Ensure we are in the project root to load .env
cd "$(dirname "$0")/.."

if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
fi

BACKUP_DIR="/var/backups/chatbot"
LOG_FILE="/var/log/chatbot_backup.log"
DAYS_TO_KEEP=30

mkdir -p "$BACKUP_DIR"

TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_FILE="$BACKUP_DIR/backup_${TIMESTAMP}.dump"

echo "[$(date)] Starting backup..." >> "$LOG_FILE"

if [ -z "$DATABASE_URL" ]; then
    echo "[$(date)] Error: DATABASE_URL not found in .env" >> "$LOG_FILE"
    exit 1
fi

# Remove '+psycopg' adapter from URL so pg_dump understands it
CLEAN_URL=$(echo "$DATABASE_URL" | sed 's/+psycopg//')

pg_dump -Fc "$CLEAN_URL" > "$BACKUP_FILE" 2>> "$LOG_FILE"

if [ $? -eq 0 ]; then
    echo "[$(date)] Backup completed successfully: $BACKUP_FILE" >> "$LOG_FILE"
    echo "[$(date)] Removing backups older than $DAYS_TO_KEEP days..." >> "$LOG_FILE"
    find "$BACKUP_DIR" -type f -name "backup_*.dump" -mtime +$DAYS_TO_KEEP -exec rm {} \; 2>> "$LOG_FILE"
else
    echo "[$(date)] Backup failed!" >> "$LOG_FILE"
    rm -f "$BACKUP_FILE"
fi

echo "----------------------------------------" >> "$LOG_FILE"
