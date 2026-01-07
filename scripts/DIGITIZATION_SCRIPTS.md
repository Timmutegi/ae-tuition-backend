# Test Digitization Scripts

This document describes the scripts used to digitize 11+ test materials into the AE-Tuition platform.

## Supported Testbooks

| Testbook | Subject | Tests | Questions/Test | Format | Status |
|----------|---------|-------|----------------|--------|--------|
| Year 5-7 Verbal Reasoning CEM Style Testbook 1 | Verbal Reasoning | 20 | 25 | MCQ | ✅ Complete (Verified) |
| Year 5-7 Maths Testbook 1 | Mathematics | 40 | 15 | MCQ | ✅ Complete |
| Year 5-7 Non-Verbal Reasoning Testbook 1 | Non-Verbal Reasoning | - | - | - | 🔜 Planned |
| Year 5-7 English Testbook 1 | English | - | - | - | 🔜 Planned |

**Note:** Both VR and Maths tests use **Multiple Choice Question (MCQ)** format with AI-generated distractors:
- **Maths**: Test image on left, MCQ options on right
- **VR Q1-10**: Reading passage MCQs
- **VR Q11-20**: Various formats (cloze, odd-one-out, synonym/antonym MCQs)
- **VR Q21-25**: Synonym/antonym MCQs with AI-generated distractors

---

## Verification Status

### Verbal Reasoning Tests (All 20 Verified)

All 20 VR CEM Tests have been comprehensively verified:

| Check | Result |
|-------|--------|
| **Question Counts** | All 20 tests have exactly 25 questions |
| **Letter Templates** | All 55 templates have matching lengths |
| **Given Word Fields** | Correctly populated for synonym/antonym questions |
| **Answer Options** | All MCQ questions have 4 options with correct answer marked |
| **Correct Answers** | Cross-checked against answer_keys.py - all 500 questions match |

```
VR CEM Test 1 V2  │ 25/25 │ ✓ VERIFIED
VR CEM Test 2 V2  │ 25/25 │ ✓ VERIFIED
...
VR CEM Test 20 V2 │ 25/25 │ ✓ VERIFIED
```

### Maths Tests

40 Maths tests created with MCQ format.

## Workflow: Questions/Question Sets vs Tests

**Important:** The digitization scripts create **questions and question sets only**, NOT tests. Tests are created manually by the admin in the UI.

| Entity | Created By | Migrated |
|--------|------------|----------|
| Questions | Digitization scripts | ✅ Yes |
| Question Sets | Digitization scripts | ✅ Yes |
| Tests | Admin (manual in UI) | ❌ No |

This approach ensures:
- Each test is in its own question set for easy recreation
- Tests can be customized per environment
- Student data (attempts, results) stays environment-specific

---

## Folder Structure

```
scripts/
├── DIGITIZATION_SCRIPTS.md           # This documentation
├── MIGRATION.md                      # Production migration guide
├── migrate_questions_to_production.sh # Migration helper script
├── migration_dumps/                  # Exported SQL files (gitignored)
├── digitization/                     # Organized digitization scripts
│   ├── __init__.py
│   ├── common/                       # Shared utilities
│   │   ├── __init__.py
│   │   ├── answer_keys.py           # VR answer keys (legacy location)
│   │   └── question_types.py        # Question type mappings
│   ├── verbal_reasoning/            # Verbal Reasoning scripts
│   │   ├── __init__.py
│   │   ├── answer_keys.py           # VR answer keys
│   │   ├── test_content.py          # Manually extracted content
│   │   ├── question_types.py        # Question type mappings for VR
│   │   ├── vr_distractor_generator.py # AI distractor generator for Q21-25
│   │   ├── vr_distractor_cache.json   # Cached distractors
│   │   ├── create_test_from_content.py  # Content-based creation
│   │   ├── create_verbal_reasoning_test.py
│   │   ├── create_verbal_reasoning_test_ai.py
│   │   ├── create_verbal_reasoning_test_ai_v2.py  # Main VR script (recommended)
│   │   ├── ai_extractor.py
│   │   └── ai_extractor_v2.py
│   └── maths/                       # Maths scripts
│       ├── __init__.py
│       ├── answer_keys.py           # Maths answer keys (20 tests x 15 questions)
│       ├── create_maths_test.py     # Main creation script
│       └── create_maths_test_standalone.py  # Standalone version
├── answer_keys.py                    # Legacy - VR answer keys
├── question_types.py                 # Legacy - Question type mappings
├── test_content.py                   # Legacy - Manual content
├── create_test_from_content.py       # Legacy - VR content-based creation
├── create_verbal_reasoning_test.py   # Legacy - Template-based
├── create_verbal_reasoning_test_ai.py    # Legacy - AI V1
├── create_verbal_reasoning_test_ai_v2.py # Legacy - AI V2
├── ai_extractor.py                   # Legacy - AI extractor V1
├── ai_extractor_v2.py               # Legacy - AI extractor V2
└── setup_intervention_test_data.py   # Intervention system test data
```

---

## Quick Start

### Verbal Reasoning Tests

```bash
cd ae-tuition-backend/scripts/digitization/verbal_reasoning

# RECOMMENDED: Create questions and question sets only (admin creates tests in UI)
python3 create_verbal_reasoning_test_ai_v2.py --questions-only

# Create a single test's questions/question set
python3 create_verbal_reasoning_test_ai_v2.py --test 1 --questions-only

# Create all 20 tests' questions/question sets
python3 create_verbal_reasoning_test_ai_v2.py --questions-only

# Legacy: Create questions AND test (not recommended)
python3 create_verbal_reasoning_test_ai_v2.py --test 1 --publish
```

### Maths Tests

```bash
cd ae-tuition-backend/scripts/digitization/maths

# RECOMMENDED: Create questions and question sets only (admin creates tests in UI)
python3 create_maths_test_mcq.py --questions-only

# Create a single test's questions/question set
python3 create_maths_test_mcq.py --test 1 --questions-only

# Create all 40 tests' questions/question sets
python3 create_maths_test_mcq.py --all --questions-only

# Pre-generate and cache distractors (saves API costs on re-runs)
python3 create_maths_test_mcq.py --generate-distractors

# Legacy: Create questions AND test (not recommended)
python3 create_maths_test_mcq.py --test 1 --publish
```

---

## Verbal Reasoning Digitization

### Test Structure

Each Verbal Reasoning test has 25 questions across 4 pages:

| Questions | Type | Answer Format | Description |
|-----------|------|---------------|-------------|
| Q1-10 | Multiple Choice | Letter (a-d) | Reading comprehension (4 options) |
| Q11-20 | Cloze/Various | Word | Fill blanks, odd-one-out, etc. |
| Q21-25 | **MCQ** | Word (4 options) | Synonym/antonym with AI-generated distractors |

**Q21-25 MCQ Format:**
- Students see the word pair (e.g., "smart → in_______")
- 4 options are provided: correct answer + 3 AI-generated distractors
- Uses GPT-4 to generate plausible wrong answers

### Scripts Overview

| Script | Description | Recommended For |
|--------|-------------|-----------------|
| `create_verbal_reasoning_test_ai_v2.py` | AI-powered extraction with MCQ Q21-25 | **All tests (1-20)** |
| `create_test_from_content.py` | Uses manually extracted content | Legacy - Test 1 only |
| `create_verbal_reasoning_test_ai.py` | AI V1 (deprecated) | - |
| `create_verbal_reasoning_test.py` | Template-based (deprecated) | - |

### AI-Powered Creation (Recommended)

The main script `create_verbal_reasoning_test_ai_v2.py` handles all 20 tests:

```bash
cd ae-tuition-backend/scripts/digitization/verbal_reasoning

# Create questions and question sets for ALL tests (recommended)
python3 create_verbal_reasoning_test_ai_v2.py --questions-only

# Create for a single test
python3 create_verbal_reasoning_test_ai_v2.py --test 1 --questions-only

# Force regeneration (ignores cache)
python3 create_verbal_reasoning_test_ai_v2.py --test 1 --questions-only --reset
```

#### Command-Line Options

| Option | Description |
|--------|-------------|
| `--test N` | Test number to create (1-20). Omit for all tests |
| `--questions-only` | **Recommended**: Create questions and question sets only, skip test creation |
| `--publish` | Legacy: Publish test after creation (default: DRAFT) |
| `--assign-classes CLASSES` | Legacy: Comma-separated class names |
| `--list-classes` | List available classes and exit |
| `--reset` | Recreate existing question set (clears cache) |

This creates:
- Reading passage with full text and image
- Q1-10: Multiple choice with 4 options (a-d)
- Q11-20: Various formats (cloze, odd-one-out, etc.)
- Q21-25: **MCQ with AI-generated distractors** (4 options)

### How It Works

1. **AI Extraction**: Uses GPT-4 Vision to extract content from test images
2. **Caching**: Caches extraction results in `extraction_cache_ai_v2.json` to avoid repeated API calls
3. **Distractor Generation**: Uses `vr_distractor_generator.py` to generate Q21-25 MCQ options
4. **Question Creation**: Creates all questions via the admin API
5. **Question Set**: Groups all 25 questions into a question set named `VR CEM Test N V2`

### Q11-20 Question Types

| Type | Description | Tests |
|------|-------------|-------|
| CLOZE_PASSAGE | Fill blanks with word options | 1 |
| ODD_ONE_OUT | Find word that doesn't belong | 2, 6, 8, 14 |
| LETTER_COMPLETION_CLOZE | Fill missing letters | 3, 7, 9, 13, 15, 19 |
| ANTONYM_LETTER | Complete antonym | 4, 10, 12, 16, 18, 20 |
| LETTER_WORD_MATCH | Match letters to words | 5, 11, 17 |

### Q21-25 Distractor Generator

The `vr_distractor_generator.py` module generates plausible wrong answers for synonym/antonym questions:

```python
from vr_distractor_generator import VRDistractorGenerator

generator = VRDistractorGenerator()
distractors = generator.generate_distractors(
    given_word="smart",
    correct_answer="intelligent",
    question_type="synonym",  # or "antonym"
    test_num=1,
    question_num=21
)
# Returns: ["clever", "brilliant", "wise"]
```

Features:
- Uses GPT-4 for intelligent distractor generation
- Generates 3 plausible wrong answers for each question
- Caches results in `vr_distractor_cache.json` to minimize API costs
- Considers question context (Year 5-7 vocabulary level)

### Frontend Display for VR Tests

The test-taking component (`test-taking.component.ts/html`) handles VR synonym/antonym questions specially:

#### Question Data Fields

| Field | Description | Example |
|-------|-------------|---------|
| `given_word` | The word to find synonym/antonym for | "smart" |
| `question_text` | Full instruction with word | "Find a word meaning the same as: smart" |
| `letter_template` | Partial answer hint (optional) | `{"template": "in_______", "answer": "intelligent"}` |
| `answer_options` | MCQ options (4 choices) | Array of option objects |

#### Display Logic

For questions with `given_word` set:

1. **Instruction Text** (`instruction_text`): Hidden to avoid redundancy
2. **Question Text** (`question_text`): Hidden for MCQ questions
3. **Clean Instruction**: Extracted and displayed (e.g., "Find a word meaning the SAME as:")
4. **Given Word**: Displayed prominently with styling
5. **MCQ Options**: Displayed as radio buttons

```typescript
// Helper method in test-taking.component.ts
getSynonymAntonymInstruction(questionText: string): string {
  if (questionText.toLowerCase().includes('same as')) {
    return 'Find a word meaning the SAME as:';
  } else if (questionText.toLowerCase().includes('opposite')) {
    return 'Find a word meaning the OPPOSITE of:';
  }
  // Fallback: extract before colon
  const colonIndex = questionText.indexOf(':');
  return colonIndex > 0 ? questionText.substring(0, colonIndex + 1).trim() : questionText;
}
```

#### Key Files

- `src/app/student/components/test-taking/test-taking.component.html` - Template with conditional display
- `src/app/student/components/test-taking/test-taking.component.ts` - Component logic with helper method

---

## Maths Digitization (MCQ Format)

### Test Structure

Each Maths test has 15 Multiple Choice questions with the test image displayed as a passage:

| Questions | Type | Answer Format | Display |
|-----------|------|---------------|---------|
| Q1-15 | Multiple Choice | 4 options (a-d) | Test image on left, MCQ options on right |

**Important:** Uses **GPT-4** to generate plausible wrong answers (distractors) for each question.

### Answer Types Supported

The AI generates appropriate distractors for:
- **Integers**: `120`, `81`, `37`
- **Decimals**: `0.3`, `1.76`, `0.45`
- **Fractions**: `1/100`, `5/6`, `3/4`
- **Mixed fractions**: `1 3/4`, `4 1/2`
- **Multiple values**: `13, 17`, `25 and 49`
- **Letters** (a-d): Returns other 3 letters (no AI needed)
- **Yes/No**: Returns opposite (no AI needed)
- **Text words**: `Thursday`, `vertical`, `reflex`
- **Ratios**: `4:3`, `3:1`
- **Time**: `8.29am`, `10:30pm`
- **Money**: `£9.50`, `£7.00`
- **Percentages**: `45%`, `60%`
- **Degrees**: `90°`, `180°`
- **Measurements**: `7.5cm`, `18cm²`
- **Compass**: `south-east`, `north`
- **Shapes**: `trapezium`, `hexagon`
- **Equations**: `A = 10, B = 12`
- **Compound**: `20 days and 6 hours`

### Running MCQ Maths Digitization

```bash
cd ae-tuition-backend/scripts/digitization/maths

# RECOMMENDED: Generate and cache distractors for all tests first
python3 create_maths_test_mcq.py --generate-distractors

# Create a single MCQ test (DRAFT status)
python3 create_maths_test_mcq.py --test 1

# Create and publish
python3 create_maths_test_mcq.py --test 1 --publish

# Full workflow: create, assign to classes, and publish
python3 create_maths_test_mcq.py --test 1 --publish --assign-classes 6A,7A

# Recreate existing test
python3 create_maths_test_mcq.py --test 1 --reset --publish

# Create ALL 40 tests at once
python3 create_maths_test_mcq.py --all --publish

# Create tests starting from a specific number
python3 create_maths_test_mcq.py --all --start-from 21 --publish

# List available classes
python3 create_maths_test_mcq.py --list-classes
```

#### Command-Line Options

| Option | Description |
|--------|-------------|
| `--test N` | Test number to create (1-40) |
| `--all` | Create all 40 tests |
| `--start-from N` | Start from test number (use with --all) |
| `--publish` | Publish test after creation (default: DRAFT) |
| `--assign-classes CLASSES` | Comma-separated class names (e.g., `6A,7A`) |
| `--list-classes` | List available classes and exit |
| `--reset` | Recreate existing test (archives the old one) |
| `--generate-distractors` | Pre-generate and cache distractors for all tests |
| `--force-regenerate` | Force regeneration of cached distractors |

### How MCQ Test Creation Works

1. **Authentication**: Logs in as admin
2. **Image Upload**: Uploads test page image to S3
3. **Passage Creation**: Creates a ReadingPassage with the test image
4. **Distractor Generation**: Uses GPT-4 to generate 3 wrong answers for each question
5. **Question Creation**: Creates 15 MULTIPLE_CHOICE questions linked to the passage
6. **Test Creation**: Creates test via `/admin/tests`
7. **Question Assignment**: Assigns questions to test via `/admin/tests/{id}/questions`
8. **Class Assignment** (optional): Assigns test to classes via `/admin/tests/{id}/assign`
9. **Publication** (optional): Updates test status to `published`

### Test Image Mapping

Test images are on odd-numbered pages:
- Test 1 → Page 03
- Test 2 → Page 05
- Test 3 → Page 07
- ...
- Test 40 → Page 81

Answer keys are on pages 85-86.

### Legacy Script (TEXT_ENTRY format)

The old script `create_maths_test_standalone.py` creates TEXT_ENTRY questions (short answer).
Use `create_maths_test_mcq.py` for the new MCQ format with AI-generated distractors.

### Cost Considerations (GPT-4)

- 600 questions × ~150 tokens/request ≈ 90,000 tokens
- **Estimated cost: ~$8-10** for all 40 tests
- Distractors are cached in `distractor_cache.json` to avoid repeated API calls

---

## Class Assignment

When using the `--assign-classes` option, tests are assigned to specified classes with a default 7-day availability window.

### How Class Assignment Works

1. **Fetch Classes**: Script retrieves all available classes from `/admin/classes`
2. **Match Names**: Class names are matched case-insensitively (e.g., `6a` matches `6A`)
3. **Create Assignment**: For each class, creates an assignment with:
   - `scheduled_start`: Current time (UTC)
   - `scheduled_end`: 7 days from now (UTC)
   - `buffer_time_minutes`: 5 minutes
   - `allow_late_submission`: False
   - `auto_submit`: True

### Example Output

```bash
$ python3 create_maths_test_standalone.py --list-classes

Available Classes:
----------------------------------------
  5A         (Year 5) - ID: abc123...
  6A         (Year 6) - ID: def456...
  7A         (Year 7) - ID: ghi789...
----------------------------------------
```

### Notes

- Tests must be published to be accessible by students
- Class assignments can only be created for existing classes
- If a class name is not found, a warning is logged but the script continues
- Students in assigned classes will see the test in their dashboard

---

## Test Statuses

Tests have three possible statuses:

| Status | Description | Student Visible |
|--------|-------------|-----------------|
| `draft` | Test created but not published | No |
| `published` | Test available for assigned students | Yes |
| `archived` | Test removed from active use | No |

### Workflow

```
[Create] → DRAFT → [Publish] → PUBLISHED → [Archive] → ARCHIVED
                       ↑                        ↓
                       └── [Unpublish] ←────────┘
```

- **Default**: Scripts create tests in DRAFT status
- **With `--publish`**: Tests are set to PUBLISHED after creation
- **With `--reset`**: Existing test is unpublished (if needed) then archived before recreating

---

## Configuration

### Environment Variables

```bash
# Backend API
API_BASE_URL=http://localhost:9000/api/v1

# Admin credentials
ADMIN_EMAIL=support@ae-tuition.com
ADMIN_PASSWORD=admin123

# OpenAI (for AI extraction)
OPENAI_API_KEY=sk-your-key
```

### Testbook Locations

Place testbook images in these directories:
- **Verbal Reasoning**: `Year_5-7_VR_CEM_Testbook_1/`
- **Maths**: `Year_5-7_Maths_Testbook_1/`

---

## Answer Keys

### Verbal Reasoning (`digitization/verbal_reasoning/answer_keys.py`)

```python
ANSWER_KEYS = {
    1: {
        1: "b", 2: "a", ..., 10: "c",  # Multiple choice
        11: "roughly", ..., 20: "determine",  # Cloze
        21: "intelligent", ..., 25: "balanced"  # Synonyms
    },
    # Tests 2-20...
}
```

### Maths (`digitization/maths/answer_keys.py`)

```python
ANSWER_KEYS = {
    1: {
        1: "120", 2: "13, 17", 3: "d", 4: "6", 5: "16",
        6: "6", 7: "0.3", 8: "no", 9: "100", 10: "1/100",
        11: "140", 12: "180", 13: "6", 14: "c", 15: "168"
    },
    # Tests 2-20...
}
```

---

## Troubleshooting

### Common Issues

| Issue | Solution |
|-------|----------|
| Authentication failed | Check admin credentials in `.env` |
| Image upload failed | Check AWS S3 credentials and permissions |
| AI extraction failed | Check OPENAI_API_KEY is set |
| Test already exists | Use `--reset` flag to recreate |
| Class not found | Use `--list-classes` to see available classes |
| Cannot archive published test | Script automatically unpublishes first |
| Test created but not visible | Check if test was published (`--publish` flag) |
| Assignment not created | Ensure class names match exactly (case-insensitive) |

### Logs

```bash
# View digitization logs
tail -f scripts/digitization.log
tail -f scripts/digitization_ai.log
tail -f scripts/digitization_ai_v2.log
```

### Reset Data

To completely reset:

```bash
# Remove progress files
rm scripts/progress*.json scripts/extraction_cache*.json

# Run with --reset flag
python3 scripts/create_verbal_reasoning_test_ai_v2.py --reset
```

---

## API Endpoints Used

| Endpoint | Purpose |
|----------|---------|
| `POST /auth/login` | Authentication |
| `POST /admin/questions/upload-image` | Upload question images |
| `POST /admin/questions/passages` | Create passages |
| `POST /admin/questions` | Create questions |
| `POST /admin/question-sets` | Create question sets |
| `POST /admin/tests` | Create tests |
| `POST /admin/tests/{id}/questions` | Assign questions to test |
| `GET /admin/classes` | List available classes |
| `POST /admin/tests/{id}/assign` | Assign test to classes |
| `PUT /admin/tests/{id}` | Update test status (publish) |
| `POST /admin/tests/{id}/unpublish` | Unpublish test |
| `POST /admin/tests/{id}/archive` | Archive test |

---

## Adding New Testbooks

To add support for a new testbook:

1. **Create folder**: `scripts/digitization/{subject}/`
2. **Add answer keys**: Create `answer_keys.py` with all answers
3. **Create script**: Adapt existing scripts for the question format
4. **Test**: Run for a single test first, verify in UI
5. **Document**: Update this file with new testbook info

---

## Cost Considerations

### AI Extraction (GPT-4 Vision)

- ~6 API calls per test (4 pages)
- Cost: ~$0.10-0.20 per test
- Full VR digitization (20 tests): ~$2-4

Extraction results are cached to avoid repeated API calls.

---

## Migrating to Production

After creating questions and question sets in development, migrate them to production. **Tests are created manually by the admin in production.**

### Quick Migration

```bash
cd ae-tuition-backend/scripts/migration_dumps

# 1. Export questions and question sets from dev (NOT tests)
PGPASSWORD='Passw0rd' pg_dump -h localhost -p 5440 -U ae -d ae_tuition \
  -t reading_passages -t questions -t answer_options \
  -t question_sets -t question_set_items \
  --data-only --inserts > questions_export.sql

# 2. Get admin IDs and replace dev ID with prod ID
sed -i '' 's/DEV_ADMIN_UUID/PROD_ADMIN_UUID/g' questions_export.sql

# 3. Import to production
PGPASSWORD='<password>' psql -h <host> -p <port> -U <user> -d <db> -f questions_export.sql
```

### Tables Migrated

| Table | Description |
|-------|-------------|
| `reading_passages` | Test images and reading passages |
| `questions` | Individual questions |
| `answer_options` | MCQ options |
| `question_sets` | Groups of questions |
| `question_set_items` | Questions within sets |

### Tables NOT Migrated

| Table | Reason |
|-------|--------|
| `tests` | Created manually by admin in production |
| `test_questions` | Created when admin creates test |
| `test_question_sets` | Created when admin assigns question set to test |
| `test_assignments`, `test_attempts`, `test_results` | Environment-specific student data |

**Note:** S3 images don't need separate migration if both environments share the same bucket.

### Creating Tests After Migration

After importing questions and question sets to production, the admin creates tests manually:

1. Log in to the admin dashboard
2. Navigate to **Tests > Create Test**
3. Fill in test details (title, type, duration, etc.)
4. In the **Question Sets** tab, assign the appropriate question set
5. Publish the test when ready

**Question Set Naming Convention:**
| Subject | Pattern | Example |
|---------|---------|---------|
| Verbal Reasoning | `VR CEM Test N V2` | `VR CEM Test 1 V2` |
| Mathematics | `11+ Maths Test N Questions` | `11+ Maths Test 1 Questions` |

For detailed instructions, see **[MIGRATION.md](./MIGRATION.md)**.
