# Database Migration: Dev to Production

This document describes how to migrate **questions and question sets** from the development environment to production. Tests are NOT migrated - they will be created manually by the admin using the question sets.

## Overview

When you create questions in the development environment using the digitization scripts, you'll need to migrate them to production. This guide covers the recommended approach using PostgreSQL's native tools.

**Important:** Only questions and question sets are migrated. Tests will be created manually by the admin in production using the question sets. This ensures:
- Each test is in its own question set for easy recreation
- Tests can be customized per environment
- Student data (attempts, results) stays environment-specific

## Tables to Migrate

The following tables contain question data (in dependency order):

| Table | Description | Dependencies |
|-------|-------------|--------------|
| `reading_passages` | Test images and reading passages | `users` (created_by) |
| `questions` | Individual questions | `users`, `reading_passages` |
| `answer_options` | MCQ options for questions | `questions` |
| `question_sets` | Groups of questions (one per test) | `users` |
| `question_set_items` | Questions within sets | `question_sets`, `questions` |

**Tables NOT migrated:**
- `tests` - Created manually by admin in production
- `test_questions` - Created when admin creates test
- `test_question_sets` - Created when admin assigns question set to test
- `test_assignments`, `test_attempts`, `test_results` - Environment-specific

---

## Prerequisites

1. **PostgreSQL client** (`psql`, `pg_dump`) installed locally
2. **Access credentials** for both dev and production databases
3. **Same admin user email** exists in both environments (e.g., `support@ae-tuition.com`)

### Connection Details

| Environment | Host | Port | Database | User |
|-------------|------|------|----------|------|
| Development | localhost | 5440 | ae_tuition | ae |
| Production | (your-prod-host) | 5432 | ae_tuition | (your-user) |

---

## Migration Steps

### Step 1: Export Data from Development

```bash
# Navigate to the migration directory
cd ae-tuition-backend/scripts
mkdir -p migration_dumps
cd migration_dumps

# Export questions and question sets only (NOT tests)
PGPASSWORD='Passw0rd' pg_dump -h localhost -p 5440 -U ae -d ae_tuition \
  -t reading_passages \
  -t questions \
  -t answer_options \
  -t question_sets \
  -t question_set_items \
  --data-only \
  --inserts \
  > questions_export.sql
```

**Flags explained:**
- `--data-only`: Export only data, not schema (schema should already exist in production)
- `--inserts`: Use INSERT statements instead of COPY (more portable)
- `-t table_name`: Specify which tables to export
- **Note:** `tests`, `test_questions`, and `test_question_sets` are NOT included

### Step 2: Get Admin User IDs

The `created_by` field references the admin user, which has different UUIDs in dev vs production.

```bash
# Get dev admin user ID
PGPASSWORD='Passw0rd' psql -h localhost -p 5440 -U ae -d ae_tuition -t -c \
  "SELECT id FROM users WHERE email = 'support@ae-tuition.com';"

# Example output: a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

```bash
# Get production admin user ID (replace connection details)
PGPASSWORD='<prod_password>' psql -h <prod_host> -p <prod_port> -U <prod_user> -d <prod_db> -t -c \
  "SELECT id FROM users WHERE email = 'support@ae-tuition.com';"

# Example output: f9e8d7c6-b5a4-3210-fedc-ba0987654321
```

### Step 3: Replace Admin User ID in Export

Replace the dev admin ID with the production admin ID in the exported SQL file:

```bash
# Using sed (macOS)
sed -i '' 's/DEV_ADMIN_UUID/PROD_ADMIN_UUID/g' questions_export.sql

# Using sed (Linux)
sed -i 's/DEV_ADMIN_UUID/PROD_ADMIN_UUID/g' questions_export.sql
```

**Example:**
```bash
sed -i '' 's/a1b2c3d4-e5f6-7890-abcd-ef1234567890/f9e8d7c6-b5a4-3210-fedc-ba0987654321/g' questions_export.sql
```

### Step 4: Review the Export File (Optional but Recommended)

```bash
# Check the file size and line count
wc -l questions_export.sql

# Preview the first few INSERT statements
head -50 questions_export.sql

# Verify the admin ID was replaced
grep -c "PROD_ADMIN_UUID" questions_export.sql
```

### Step 5: Import to Production

**Option A: Direct import (if you have direct access)**
```bash
PGPASSWORD='<prod_password>' psql -h <prod_host> -p <prod_port> -U <prod_user> -d <prod_db> -f questions_export.sql
```

**Option B: Copy file to production server first**
```bash
# Copy to production server
scp questions_export.sql user@prod-server:/tmp/

# SSH to production and run import
ssh user@prod-server
cd /tmp
PGPASSWORD='<password>' psql -h localhost -U <user> -d ae_tuition -f questions_export.sql
```

### Step 6: Verify Migration

```bash
# Connect to production and verify counts
PGPASSWORD='<prod_password>' psql -h <prod_host> -p <prod_port> -U <prod_user> -d <prod_db> -c "
SELECT 'reading_passages' as table_name, COUNT(*) as count FROM reading_passages
UNION ALL SELECT 'questions', COUNT(*) FROM questions
UNION ALL SELECT 'answer_options', COUNT(*) FROM answer_options
UNION ALL SELECT 'question_sets', COUNT(*) FROM question_sets
UNION ALL SELECT 'question_set_items', COUNT(*) FROM question_set_items
ORDER BY table_name;
"
```

### Step 7: Create Tests in Production (Manual)

After migration, the admin should create tests in production:

1. Log in to the admin dashboard in production
2. Navigate to **Tests > Create Test**
3. Fill in test details (title, type, duration, etc.)
4. In the **Question Sets** tab, assign the appropriate question set
5. Publish the test when ready

**Question Set Naming Convention:**
- VR tests: `VR CEM Test 1 V2`, `VR CEM Test 2 V2`, etc.
- Maths tests: `11+ Maths Test 1 Questions`, `11+ Maths Test 2 Questions`, etc.

---

## Handling Conflicts

### If Data Already Exists in Production

**Option 1: Skip duplicates (safe)**

Wrap the import in a transaction and handle conflicts:

```sql
-- Create a wrapper script: import_safe.sql
BEGIN;

-- Disable triggers temporarily
SET session_replication_role = 'replica';

-- Your INSERT statements here (from questions_export.sql)
-- Add ON CONFLICT DO NOTHING to each INSERT if needed

-- Re-enable triggers
SET session_replication_role = 'origin';

COMMIT;
```

**Option 2: Clear and replace (destructive)**

```sql
-- WARNING: This deletes ALL existing question data!
BEGIN;

-- Delete in reverse dependency order (questions only, not tests)
TRUNCATE question_set_items, question_sets,
         answer_options, questions, reading_passages CASCADE;

-- Then run the import
\i questions_export.sql

COMMIT;
```

**Option 3: Migrate by subject**

Export only specific subjects:

```bash
# Export only Mathematics questions
PGPASSWORD='Passw0rd' psql -h localhost -p 5440 -U ae -d ae_tuition -c "
\COPY (SELECT * FROM questions WHERE subject = 'Mathematics') TO 'questions_maths.csv' WITH CSV HEADER;
"
```

---

## S3 Images

**Good news:** S3 images do NOT need to be migrated separately!

The images are stored in AWS S3 (shared bucket) and referenced by URL in the database. As long as:
- Both environments use the same S3 bucket
- CloudFront URLs are the same

The images will work automatically in production.

If you're using different S3 buckets, you'll need to:
1. Copy images between buckets using `aws s3 sync`
2. Update `image_url` and `s3_key` columns in the exported SQL

---

## Rollback

If something goes wrong, you can rollback by:

1. **If you used a transaction:** It will automatically rollback on error
2. **If already committed:** Restore from a backup or delete the imported data:

```sql
-- Delete only the data imported (by created_at timestamp)
DELETE FROM question_set_items WHERE created_at > '2024-01-06 00:00:00';
DELETE FROM question_sets WHERE created_at > '2024-01-06 00:00:00';
DELETE FROM answer_options WHERE created_at > '2024-01-06 00:00:00';
DELETE FROM questions WHERE created_at > '2024-01-06 00:00:00';
DELETE FROM reading_passages WHERE created_at > '2024-01-06 00:00:00';
```

---

## Quick Reference

### Export Command (Questions Only)
```bash
PGPASSWORD='Passw0rd' pg_dump -h localhost -p 5440 -U ae -d ae_tuition \
  -t reading_passages -t questions -t answer_options \
  -t question_sets -t question_set_items \
  --data-only --inserts > questions_export.sql
```

### Replace Admin ID
```bash
sed -i '' 's/DEV_UUID/PROD_UUID/g' questions_export.sql
```

### Import Command (File → Production)
```bash
PGPASSWORD='<password>' psql -h <host> -p <port> -U <user> -d <db> -f questions_export.sql
```

---

## Test Creation After Migration

After importing questions to production, create tests using the admin UI:

| Question Set | Test to Create |
|--------------|----------------|
| `VR CEM Test 1 V2` | `11+ Verbal Reasoning CEM Style - Test 1` |
| `VR CEM Test 2 V2` | `11+ Verbal Reasoning CEM Style - Test 2` |
| `11+ Maths Test 1 Questions` | `11+ Maths CEM Style - Test 1` |
| ... | ... |

Each question set contains all 25 (VR) or 15 (Maths) questions for one test.

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| `permission denied` | Check database user has INSERT privileges |
| `duplicate key` | Data already exists; use ON CONFLICT or clear first |
| `foreign key violation` | Import tables in correct dependency order |
| `relation does not exist` | Run migrations first (`alembic upgrade head`) |
| `invalid UUID` | Check the sed replacement worked correctly |
| `images not loading` | Verify S3 bucket access and CloudFront URLs |
| `question set not showing` | Refresh admin dashboard or check `is_active` flag |

---

## See Also

- [DIGITIZATION_SCRIPTS.md](./DIGITIZATION_SCRIPTS.md) - How to create questions/question sets
- [../CLAUDE.md](../CLAUDE.md) - Project overview
