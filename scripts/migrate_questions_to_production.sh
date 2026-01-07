#!/bin/bash
# Migration Script: Copy questions, tests, and related data from dev to production
#
# Usage:
#   1. Set environment variables (or modify defaults below)
#   2. Run: ./migrate_questions_to_production.sh
#
# This script exports question-related tables from dev and imports to production,
# automatically updating the created_by field to the production admin user.

set -e

# ============================================================================
# CONFIGURATION - Modify these values for your environments
# ============================================================================

# Dev Database (source)
DEV_HOST="${DEV_HOST:-localhost}"
DEV_PORT="${DEV_PORT:-5440}"
DEV_DB="${DEV_DB:-ae_tuition}"
DEV_USER="${DEV_USER:-ae}"
DEV_PASSWORD="${DEV_PASSWORD:-Passw0rd}"

# Production Database (destination)
PROD_HOST="${PROD_HOST:-your-prod-host}"
PROD_PORT="${PROD_PORT:-5432}"
PROD_DB="${PROD_DB:-ae_tuition}"
PROD_USER="${PROD_USER:-ae}"
PROD_PASSWORD="${PROD_PASSWORD:-your-prod-password}"

# Admin email (same in both environments)
ADMIN_EMAIL="${ADMIN_EMAIL:-support@ae-tuition.com}"

# Output directory for dump files
DUMP_DIR="./migration_dumps"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# ============================================================================
# FUNCTIONS
# ============================================================================

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

error() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ERROR: $1" >&2
    exit 1
}

# ============================================================================
# MAIN SCRIPT
# ============================================================================

log "Starting migration from dev to production..."

# Create dump directory
mkdir -p "$DUMP_DIR"

# Export PGPASSWORD for dev database
export PGPASSWORD="$DEV_PASSWORD"

log "Step 1: Getting admin user ID from dev database..."
DEV_ADMIN_ID=$(psql -h "$DEV_HOST" -p "$DEV_PORT" -U "$DEV_USER" -d "$DEV_DB" -t -c \
    "SELECT id FROM users WHERE email = '$ADMIN_EMAIL' LIMIT 1;" | tr -d ' \n')

if [ -z "$DEV_ADMIN_ID" ]; then
    error "Could not find admin user with email $ADMIN_EMAIL in dev database"
fi
log "Dev admin user ID: $DEV_ADMIN_ID"

# Export PGPASSWORD for prod database
export PGPASSWORD="$PROD_PASSWORD"

log "Step 2: Getting admin user ID from production database..."
PROD_ADMIN_ID=$(psql -h "$PROD_HOST" -p "$PROD_PORT" -U "$PROD_USER" -d "$PROD_DB" -t -c \
    "SELECT id FROM users WHERE email = '$ADMIN_EMAIL' LIMIT 1;" | tr -d ' \n')

if [ -z "$PROD_ADMIN_ID" ]; then
    error "Could not find admin user with email $ADMIN_EMAIL in production database"
fi
log "Production admin user ID: $PROD_ADMIN_ID"

# Switch back to dev for export
export PGPASSWORD="$DEV_PASSWORD"

log "Step 3: Exporting tables from dev database..."

# Tables to export (in order of dependencies)
TABLES=(
    "reading_passages"
    "questions"
    "answer_options"
    "question_sets"
    "question_set_items"
    "tests"
    "test_questions"
    "test_question_sets"
)

# Export each table to CSV
for table in "${TABLES[@]}"; do
    log "  Exporting $table..."
    psql -h "$DEV_HOST" -p "$DEV_PORT" -U "$DEV_USER" -d "$DEV_DB" -c \
        "\COPY $table TO '$DUMP_DIR/${table}_${TIMESTAMP}.csv' WITH CSV HEADER;"
done

log "Step 4: Creating SQL import script..."

# Create SQL script for import
SQL_SCRIPT="$DUMP_DIR/import_${TIMESTAMP}.sql"

cat > "$SQL_SCRIPT" << 'SQLEOF'
-- Migration Script: Import questions, tests, and related data
-- Generated automatically - review before running!

BEGIN;

-- Disable triggers temporarily for faster import
SET session_replication_role = 'replica';

-- Clear existing data (optional - uncomment if you want to replace)
-- TRUNCATE test_question_sets, test_questions, question_set_items, question_sets, tests, answer_options, questions, reading_passages CASCADE;

SQLEOF

# Add COPY commands for each table
for table in "${TABLES[@]}"; do
    cat >> "$SQL_SCRIPT" << EOF

-- Import $table
\COPY $table FROM '$DUMP_DIR/${table}_${TIMESTAMP}.csv' WITH CSV HEADER;
EOF
done

# Add the admin ID replacement commands
cat >> "$SQL_SCRIPT" << EOF

-- Update created_by to production admin user
UPDATE reading_passages SET created_by = '$PROD_ADMIN_ID' WHERE created_by = '$DEV_ADMIN_ID';
UPDATE questions SET created_by = '$PROD_ADMIN_ID' WHERE created_by = '$DEV_ADMIN_ID';
UPDATE question_sets SET created_by = '$PROD_ADMIN_ID' WHERE created_by = '$DEV_ADMIN_ID';
UPDATE tests SET created_by = '$PROD_ADMIN_ID' WHERE created_by = '$DEV_ADMIN_ID';

-- Re-enable triggers
SET session_replication_role = 'origin';

COMMIT;

-- Verify counts
SELECT 'reading_passages' as table_name, COUNT(*) as count FROM reading_passages
UNION ALL SELECT 'questions', COUNT(*) FROM questions
UNION ALL SELECT 'answer_options', COUNT(*) FROM answer_options
UNION ALL SELECT 'question_sets', COUNT(*) FROM question_sets
UNION ALL SELECT 'question_set_items', COUNT(*) FROM question_set_items
UNION ALL SELECT 'tests', COUNT(*) FROM tests
UNION ALL SELECT 'test_questions', COUNT(*) FROM test_questions
UNION ALL SELECT 'test_question_sets', COUNT(*) FROM test_question_sets;
EOF

log "Step 5: SQL script created at $SQL_SCRIPT"
log ""
log "============================================================================"
log "NEXT STEPS:"
log "============================================================================"
log ""
log "1. Review the exported CSV files in $DUMP_DIR/"
log ""
log "2. Copy the dump directory to a location accessible from production:"
log "   scp -r $DUMP_DIR user@prod-server:/tmp/"
log ""
log "3. On the production server, run the import script:"
log "   PGPASSWORD='$PROD_PASSWORD' psql -h $PROD_HOST -p $PROD_PORT -U $PROD_USER -d $PROD_DB -f /tmp/migration_dumps/import_${TIMESTAMP}.sql"
log ""
log "4. Verify the data was imported correctly"
log ""
log "============================================================================"
log ""
log "Alternatively, if you have direct access to production from this machine:"
log ""
log "   export PGPASSWORD='$PROD_PASSWORD'"
log "   psql -h $PROD_HOST -p $PROD_PORT -U $PROD_USER -d $PROD_DB -f $SQL_SCRIPT"
log ""
