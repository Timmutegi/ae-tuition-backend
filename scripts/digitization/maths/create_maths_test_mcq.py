#!/usr/bin/env python3
"""
MCQ Maths Test Digitization Script

Creates Maths tests with Multiple Choice Questions (MCQ) from Year 5-7 Maths Testbook 1.
Each test displays the question paper image on the left and MCQ options on the right.

Uses OpenAI GPT-4 to generate plausible wrong answers (distractors) for each question.

Usage:
    cd ae-tuition-backend/scripts/digitization/maths

    # Generate and cache distractors for all tests (recommended first step)
    python create_maths_test_mcq.py --generate-distractors

    # Create a single test (draft mode)
    python create_maths_test_mcq.py --test 1

    # Create and publish a test
    python create_maths_test_mcq.py --test 1 --publish

    # Create, publish, and assign to classes
    python create_maths_test_mcq.py --test 1 --publish --assign-classes 6A,7A

    # Recreate existing test
    python create_maths_test_mcq.py --test 1 --reset --publish

    # Create all 40 tests
    python create_maths_test_mcq.py --all --publish

    # List available classes
    python create_maths_test_mcq.py --list-classes
"""

import os
import sys
import argparse
import logging
import random
import requests
from pathlib import Path
from typing import Optional, List, Dict, Tuple
from datetime import datetime, timedelta

# Configuration
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:9000/api/v1")
ADMIN_EMAIL = os.getenv("DEFAULT_ADMIN_EMAIL", "support@ae-tuition.com")
ADMIN_PASSWORD = os.getenv("DEFAULT_ADMIN_PASSWORD", "Admin123!!")

# Testbook location (relative to this script's location)
SCRIPT_DIR = Path(__file__).parent
TESTBOOK_PATH = SCRIPT_DIR.parent.parent.parent.parent / "Year_5-7_Maths_Testbook_1"

# Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Import answer keys and distractor generator
from answer_keys import ANSWER_KEYS, get_answer, get_all_answers, TEST_METADATA
from distractor_generator import DistractorGenerator


class MathsMCQTestCreator:
    """Creates Maths MCQ tests via the API."""

    def __init__(self):
        self.session = requests.Session()
        self.token = None
        self.classes_cache = None
        self.distractor_generator = None

    def authenticate(self) -> bool:
        """Authenticate as admin."""
        try:
            response = self.session.post(
                f"{API_BASE_URL}/auth/login",
                json={"identifier": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
            )
            response.raise_for_status()
            data = response.json()
            self.token = data["access_token"]
            self.session.headers["Authorization"] = f"Bearer {self.token}"
            logger.info(f"Authenticated as {ADMIN_EMAIL}")
            return True
        except Exception as e:
            logger.error(f"Authentication failed: {e}")
            return False

    def init_distractor_generator(self) -> bool:
        """Initialize the distractor generator."""
        try:
            self.distractor_generator = DistractorGenerator()
            logger.info("Distractor generator initialized")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize distractor generator: {e}")
            return False

    def get_classes(self) -> List[Dict]:
        """Get all available classes."""
        if self.classes_cache is not None:
            return self.classes_cache

        try:
            response = self.session.get(f"{API_BASE_URL}/admin/classes")
            response.raise_for_status()
            data = response.json()
            self.classes_cache = data.get("classes", data) if isinstance(data, dict) else data
            return self.classes_cache
        except Exception as e:
            logger.error(f"Failed to get classes: {e}")
            return []

    def get_class_ids_by_names(self, class_names: List[str]) -> List[str]:
        """Convert class names to class IDs."""
        classes = self.get_classes()
        class_ids = []

        for name in class_names:
            name = name.strip()
            for cls in classes:
                if cls.get("name", "").lower() == name.lower():
                    class_ids.append(cls["id"])
                    break
            else:
                logger.warning(f"Class not found: {name}")

        return class_ids

    def list_classes(self) -> None:
        """List all available classes."""
        classes = self.get_classes()
        if not classes:
            logger.info("No classes found")
            return

        logger.info("\nAvailable Classes:")
        logger.info("-" * 40)
        for cls in classes:
            logger.info(f"  {cls.get('name', 'N/A'):10} (Year {cls.get('year_group', 'N/A')}) - ID: {cls.get('id', 'N/A')}")
        logger.info("-" * 40)

    def get_test_image_path(self, test_num: int) -> Path:
        """Get the image path for a test page."""
        # Test 1 is on page 03, Test 2 on page 05, etc.
        page_num = (test_num * 2) + 1
        image_name = f"Year 5-7 Maths Testbook 1 26.06.20-{page_num:02d}.png"
        return TESTBOOK_PATH / image_name

    def upload_image(self, image_path: Path) -> Tuple[Optional[str], Optional[str]]:
        """
        Upload an image and return the URL and S3 key.

        Returns:
            Tuple of (public_url, s3_key) or (None, None) on failure
        """
        try:
            with open(image_path, 'rb') as f:
                response = self.session.post(
                    f"{API_BASE_URL}/admin/questions/upload-image",
                    files={"file": (image_path.name, f, "image/png")}
                )
                response.raise_for_status()
                data = response.json()
                return data.get("public_url", ""), data.get("s3_key", "")
        except Exception as e:
            logger.error(f"Failed to upload image: {e}")
            return None, None

    def create_passage(self, test_num: int, image_url: str, s3_key: str) -> Optional[str]:
        """
        Create a ReadingPassage for the test image.

        Returns:
            Passage ID or None on failure
        """
        metadata = TEST_METADATA.get(test_num, {})
        topics = metadata.get("topics", ["arithmetic", "fractions", "geometry"])

        passage_data = {
            "title": f"11+ Maths Test {test_num} - Question Paper",
            "content": "",  # No text content, just image
            "image_url": image_url,
            "s3_key": s3_key,
            "subject": "Mathematics",
            "genre": "Test Paper",
            "reading_level": "Year 5-7"
        }

        try:
            response = self.session.post(
                f"{API_BASE_URL}/admin/questions/passages",
                json=passage_data
            )
            response.raise_for_status()
            passage_id = response.json().get("id")
            logger.info(f"Created passage: {passage_id[:8]}...")
            return passage_id
        except Exception as e:
            logger.error(f"Failed to create passage: {e}")
            if hasattr(e, 'response') and e.response:
                logger.error(f"Response: {e.response.text}")
            return None

    def create_mcq_question(self, test_num: int, q_num: int, passage_id: str) -> Optional[str]:
        """
        Create a single MCQ question with distractors.

        Returns:
            Question ID or None on failure
        """
        # Get correct answer
        correct_answer = get_answer(test_num, q_num)

        # Generate distractors
        distractors = self.distractor_generator.generate_distractors(
            correct_answer=correct_answer,
            test_num=test_num,
            question_num=q_num
        )

        # Shuffle options
        options, correct_index = self.distractor_generator.get_shuffled_options(
            correct_answer, distractors
        )

        # Build answer options
        answer_options = []
        for i, option_text in enumerate(options):
            answer_options.append({
                "option_text": str(option_text),
                "is_correct": i == correct_index,
                "order_number": i + 1
            })

        # Create question
        question_data = {
            "question_text": f"Question {q_num}",
            "question_type": "multiple_choice",
            "question_format": "passage_based",
            "passage_id": passage_id,
            "instruction_text": "Look at the test paper image on the left and select the correct answer.",
            "correct_answer": str(correct_answer),
            "points": 1,
            "subject": "Mathematics",
            "answer_options": answer_options
        }

        try:
            response = self.session.post(
                f"{API_BASE_URL}/admin/questions",
                json=question_data
            )
            response.raise_for_status()
            question_id = response.json().get("id")
            correct_letter = chr(97 + correct_index)  # a, b, c, d
            logger.info(f"  Q{q_num}: '{correct_answer}' -> [{', '.join(options)}] (correct: {correct_letter})")
            return question_id
        except Exception as e:
            logger.error(f"Failed to create question {q_num}: {e}")
            if hasattr(e, 'response') and e.response:
                logger.error(f"Response: {e.response.text}")
            return None

    def assign_questions_to_test(self, test_id: str, question_ids: List[str]) -> bool:
        """Assign questions to a test."""
        questions = [
            {
                "question_id": qid,
                "order_number": idx + 1,
                "points": 1
            }
            for idx, qid in enumerate(question_ids)
        ]

        try:
            response = self.session.post(
                f"{API_BASE_URL}/admin/tests/{test_id}/questions",
                json=questions
            )
            response.raise_for_status()
            logger.info(f"Assigned {len(question_ids)} questions to test")
            return True
        except Exception as e:
            logger.error(f"Failed to assign questions: {e}")
            if hasattr(e, 'response') and e.response:
                logger.error(f"Response: {e.response.text}")
            return False

    def publish_test(self, test_id: str) -> bool:
        """Publish a test."""
        try:
            response = self.session.put(
                f"{API_BASE_URL}/admin/tests/{test_id}",
                json={"status": "published"}
            )
            if response.status_code == 200:
                logger.info("Test published successfully!")
                return True
            else:
                logger.error(f"Failed to publish test: {response.status_code}")
                logger.error(f"Response: {response.text}")
                return False
        except Exception as e:
            logger.error(f"Failed to publish test: {e}")
            return False

    def assign_test_to_classes(self, test_id: str, class_ids: List[str],
                                days_available: int = 7) -> bool:
        """Assign test to classes."""
        if not class_ids:
            logger.warning("No class IDs provided for assignment")
            return False

        # Set assignment window: start now, end in X days
        now = datetime.utcnow()
        scheduled_start = now.isoformat() + "Z"
        scheduled_end = (now + timedelta(days=days_available)).isoformat() + "Z"

        assignment_data = {
            "class_ids": class_ids,
            "assignment_data": {
                "scheduled_start": scheduled_start,
                "scheduled_end": scheduled_end,
                "buffer_time_minutes": 5,
                "allow_late_submission": False,
                "auto_submit": True
            }
        }

        try:
            response = self.session.post(
                f"{API_BASE_URL}/admin/tests/{test_id}/assign",
                json=assignment_data
            )
            if response.status_code == 200:
                assignments = response.json()
                logger.info(f"Test assigned to {len(assignments)} class(es)")
                return True
            else:
                logger.error(f"Failed to assign test: {response.status_code}")
                logger.error(f"Response: {response.text}")
                return False
        except Exception as e:
            logger.error(f"Failed to assign test: {e}")
            return False

    def find_existing_test(self, title: str):
        """Find an existing test by title."""
        try:
            response = self.session.get(f"{API_BASE_URL}/admin/tests")
            response.raise_for_status()
            data = response.json()
            tests = data.get("tests", data) if isinstance(data, dict) else data
            for test in tests:
                if test.get("title") == title and test.get("status") != "archived":
                    return test
        except Exception as e:
            logger.debug(f"Error finding test: {e}")
        return None

    def archive_test(self, test_id: str):
        """Archive a test (unpublish first if needed)."""
        try:
            # First try to unpublish if published
            unpublish_response = self.session.post(
                f"{API_BASE_URL}/admin/tests/{test_id}/unpublish"
            )
            if unpublish_response.status_code == 200:
                logger.info(f"Test unpublished: {test_id}")

            # Then archive
            response = self.session.post(
                f"{API_BASE_URL}/admin/tests/{test_id}/archive"
            )
            if response.status_code == 200:
                logger.info(f"Test archived: {test_id}")
            else:
                logger.error(f"Failed to archive: {response.status_code} - {response.text}")
        except Exception as e:
            logger.error(f"Failed to archive: {e}")

    def create_test(self, test_num: int, reset: bool = False,
                    publish: bool = False, class_names: List[str] = None) -> bool:
        """Create a single Maths MCQ test."""
        logger.info(f"\n{'='*60}")
        logger.info(f"Creating MCQ Maths Test {test_num}")
        logger.info(f"{'='*60}")

        test_title = f"11+ Maths CEM Style - Test {test_num}"

        # Check for existing test
        existing = self.find_existing_test(test_title)
        if existing:
            if reset:
                logger.info(f"Archiving existing test...")
                self.archive_test(existing['id'])
            else:
                logger.info("Test already exists. Use --reset to recreate.")
                return True

        # Validate test number
        if test_num not in ANSWER_KEYS:
            logger.error(f"Test {test_num} not found in answer keys")
            return False

        # Step 1: Upload test image
        image_path = self.get_test_image_path(test_num)
        if not image_path.exists():
            logger.error(f"Test image not found: {image_path}")
            return False

        logger.info(f"Uploading test image: {image_path.name}")
        image_url, s3_key = self.upload_image(image_path)
        if not image_url:
            logger.error("Failed to upload test image")
            return False
        logger.info(f"Image uploaded: {image_url[:60]}...")

        # Step 2: Create passage for the test image
        logger.info("Creating passage for test image...")
        passage_id = self.create_passage(test_num, image_url, s3_key)
        if not passage_id:
            logger.error("Failed to create passage")
            return False

        # Step 3: Create MCQ questions
        logger.info("Creating MCQ questions...")
        question_ids = []
        for q_num in range(1, 16):
            question_id = self.create_mcq_question(test_num, q_num, passage_id)
            if question_id:
                question_ids.append(question_id)
            else:
                logger.error(f"Failed to create question {q_num}, aborting")
                return False

        # Step 4: Create the test
        logger.info("Creating test...")
        metadata = TEST_METADATA.get(test_num, {})
        topics = metadata.get("topics", ["arithmetic", "fractions", "geometry"])
        topics_str = ", ".join(topics)

        test_data = {
            "title": test_title,
            "type": "Mathematics",
            "description": f"Year 5-7 Maths Testbook 1 - Test {test_num}. Topics: {topics_str}. Look at the question paper image and select the correct answer for each question.",
            "instructions": "Read each question carefully from the test paper image. Select the correct answer from the four options provided. You may use rough paper for working out.",
            "duration_minutes": 20,
            "pass_mark": 60,
            "warning_intervals": [5, 2]
        }

        try:
            response = self.session.post(
                f"{API_BASE_URL}/admin/tests",
                json=test_data
            )
            response.raise_for_status()
            test_id = response.json().get("id")
            logger.info(f"Test created: {test_id}")
        except Exception as e:
            logger.error(f"Failed to create test: {e}")
            if hasattr(e, 'response') and e.response:
                logger.error(f"Response: {e.response.text}")
            return False

        # Step 5: Assign questions to test
        if not self.assign_questions_to_test(test_id, question_ids):
            return False

        # Step 6: Assign to classes (if requested)
        if class_names:
            class_ids = self.get_class_ids_by_names(class_names)
            if class_ids:
                logger.info(f"Assigning test to classes: {', '.join(class_names)}")
                self.assign_test_to_classes(test_id, class_ids)
            else:
                logger.warning("No valid class IDs found for assignment")

        # Step 7: Publish the test (if requested)
        if publish:
            self.publish_test(test_id)
        else:
            logger.info("Test created in DRAFT status (use --publish to publish)")

        logger.info(f"\n{'='*60}")
        logger.info(f"TEST {test_num} CREATED SUCCESSFULLY (MCQ FORMAT)")
        logger.info(f"{'='*60}")

        return True

    def generate_all_distractors(self, force_regenerate: bool = False) -> bool:
        """
        Pre-generate and cache distractors for all tests.

        This is useful to run once before creating all tests, to:
        1. Review the generated distractors for quality
        2. Cache them to avoid repeated API calls
        """
        logger.info("\n" + "="*60)
        logger.info("GENERATING DISTRACTORS FOR ALL 40 TESTS")
        logger.info("="*60)

        if not self.distractor_generator:
            if not self.init_distractor_generator():
                return False

        total_questions = 0
        for test_num in range(1, 41):
            logger.info(f"\nTest {test_num}:")
            answers = get_all_answers(test_num)
            for q_num, correct_answer in answers.items():
                distractors = self.distractor_generator.generate_distractors(
                    correct_answer=correct_answer,
                    test_num=test_num,
                    question_num=q_num,
                    force_regenerate=force_regenerate
                )
                logger.info(f"  Q{q_num}: {correct_answer} -> {distractors}")
                total_questions += 1

        logger.info(f"\n{'='*60}")
        logger.info(f"GENERATED DISTRACTORS FOR {total_questions} QUESTIONS")
        logger.info(f"Cache saved to: {SCRIPT_DIR / 'distractor_cache.json'}")
        logger.info(f"{'='*60}")

        return True

    def create_all_tests(self, reset: bool = False, publish: bool = False,
                         class_names: List[str] = None, start_from: int = 1) -> bool:
        """Create all 40 MCQ maths tests."""
        logger.info("\n" + "="*60)
        logger.info("CREATING ALL 40 MCQ MATHS TESTS")
        logger.info("="*60)

        success_count = 0
        fail_count = 0

        for test_num in range(start_from, 41):
            success = self.create_test(
                test_num=test_num,
                reset=reset,
                publish=publish,
                class_names=class_names
            )
            if success:
                success_count += 1
            else:
                fail_count += 1

        logger.info(f"\n{'='*60}")
        logger.info(f"COMPLETED: {success_count} tests created, {fail_count} failed")
        logger.info(f"{'='*60}")

        return fail_count == 0


def main():
    parser = argparse.ArgumentParser(
        description="Create MCQ Maths tests from Year 5-7 Testbook 1",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate and cache distractors for all tests first (recommended)
  python create_maths_test_mcq.py --generate-distractors

  # Create a single test (draft)
  python create_maths_test_mcq.py --test 1

  # Create and publish
  python create_maths_test_mcq.py --test 1 --publish

  # Create, publish, and assign to classes
  python create_maths_test_mcq.py --test 1 --publish --assign-classes 6A,7A

  # Recreate existing test
  python create_maths_test_mcq.py --test 1 --reset --publish

  # Create all 40 tests
  python create_maths_test_mcq.py --all --publish

  # List available classes
  python create_maths_test_mcq.py --list-classes
        """
    )
    parser.add_argument("--test", type=int, help="Test number to create (1-40)")
    parser.add_argument("--all", action="store_true", help="Create all 40 tests")
    parser.add_argument("--start-from", type=int, default=1,
                        help="Start from test number (use with --all)")
    parser.add_argument("--reset", action="store_true", help="Recreate existing test")
    parser.add_argument("--publish", action="store_true", help="Publish the test after creation")
    parser.add_argument("--assign-classes", type=str,
                        help="Comma-separated list of class names to assign (e.g., '6A,7A')")
    parser.add_argument("--list-classes", action="store_true", help="List available classes")
    parser.add_argument("--generate-distractors", action="store_true",
                        help="Generate and cache distractors for all tests")
    parser.add_argument("--force-regenerate", action="store_true",
                        help="Force regeneration of cached distractors")
    args = parser.parse_args()

    # Validate arguments
    if not any([args.test, args.all, args.list_classes, args.generate_distractors]):
        parser.print_help()
        sys.exit(1)

    if args.test and (args.test < 1 or args.test > 40):
        logger.error("Test number must be 1-40")
        sys.exit(1)

    creator = MathsMCQTestCreator()

    # Handle --generate-distractors (doesn't need authentication)
    if args.generate_distractors:
        if not creator.init_distractor_generator():
            sys.exit(1)
        success = creator.generate_all_distractors(force_regenerate=args.force_regenerate)
        sys.exit(0 if success else 1)

    # Authenticate for other operations
    if not creator.authenticate():
        sys.exit(1)

    # Handle --list-classes
    if args.list_classes:
        creator.list_classes()
        sys.exit(0)

    # Initialize distractor generator
    if not creator.init_distractor_generator():
        sys.exit(1)

    # Parse class names
    class_names = None
    if args.assign_classes:
        class_names = [c.strip() for c in args.assign_classes.split(",")]

    # Create tests
    if args.all:
        success = creator.create_all_tests(
            reset=args.reset,
            publish=args.publish,
            class_names=class_names,
            start_from=args.start_from
        )
    else:
        success = creator.create_test(
            args.test,
            reset=args.reset,
            publish=args.publish,
            class_names=class_names
        )

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
