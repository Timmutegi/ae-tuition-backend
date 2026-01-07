#!/usr/bin/env python3
"""
Standalone Maths Test Digitization Script

Creates Maths tests from Year 5-7 Maths Testbook 1.
Each test has 15 short-answer questions.

Usage:
    cd ae-tuition-backend/scripts/digitization/maths

    # Digitize only (creates test in DRAFT status)
    python create_maths_test_standalone.py --test 1

    # Digitize and publish
    python create_maths_test_standalone.py --test 1 --publish

    # Digitize, assign to classes, and publish
    python create_maths_test_standalone.py --test 1 --publish --assign-classes 6A,7A

    # Recreate existing test
    python create_maths_test_standalone.py --test 1 --reset --publish

    # List available classes
    python create_maths_test_standalone.py --list-classes
"""

import os
import sys
import argparse
import logging
import requests
from pathlib import Path
from typing import Optional, List, Dict
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

# Import answer keys
from answer_keys import ANSWER_KEYS, get_answer, TEST_METADATA


class MathsTestCreator:
    """Creates Maths tests via the API."""

    def __init__(self):
        self.session = requests.Session()
        self.token = None
        self.classes_cache = None

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

    def get_classes(self) -> List[Dict]:
        """Get all available classes."""
        if self.classes_cache is not None:
            return self.classes_cache

        try:
            response = self.session.get(f"{API_BASE_URL}/admin/classes")
            response.raise_for_status()
            data = response.json()
            # Handle paginated response
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
        page_num = (test_num * 2) + 1
        image_name = f"Year 5-7 Maths Testbook 1 26.06.20-{page_num:02d}.png"
        return TESTBOOK_PATH / image_name

    def upload_image(self, image_path: Path) -> str:
        """Upload an image and return the URL."""
        try:
            with open(image_path, 'rb') as f:
                response = self.session.post(
                    f"{API_BASE_URL}/admin/questions/upload-image",
                    files={"file": (image_path.name, f, "image/png")}
                )
                response.raise_for_status()
                return response.json().get("public_url", "")
        except Exception as e:
            logger.error(f"Failed to upload image: {e}")
            return ""

    def create_question(self, test_num: int, q_num: int, image_url: Optional[str] = None) -> Optional[str]:
        """Create a single question and return its ID."""
        answer = get_answer(test_num, q_num)

        question_data = {
            "question_text": f"Question {q_num}",
            "question_type": "text_entry",
            "instruction_text": "Refer to the test paper image and write your answer.",
            "correct_answer": str(answer),
            "points": 1,
            "subject": "Mathematics",
            "image_url": image_url
        }

        try:
            response = self.session.post(
                f"{API_BASE_URL}/admin/questions",
                json=question_data
            )
            response.raise_for_status()
            question_id = response.json().get("id")
            logger.info(f"  Q{q_num}: answer = {answer} (ID: {question_id[:8]}...)")
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

    def create_test(self, test_num: int, reset: bool = False,
                    publish: bool = False, class_names: List[str] = None) -> bool:
        """Create a single Maths test."""
        logger.info(f"\n{'='*50}")
        logger.info(f"Creating Maths Test {test_num}")
        logger.info(f"{'='*50}")

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

        # Upload test image
        image_path = self.get_test_image_path(test_num)
        image_url = None
        if image_path.exists():
            logger.info(f"Uploading test image: {image_path.name}")
            image_url = self.upload_image(image_path)
            if image_url:
                logger.info(f"Image uploaded: {image_url[:60]}...")
        else:
            logger.warning(f"Test image not found: {image_path}")

        # Step 1: Create questions
        logger.info("Creating questions...")
        question_ids = []
        for q_num in range(1, 16):
            question_id = self.create_question(test_num, q_num, image_url)
            if question_id:
                question_ids.append(question_id)
            else:
                logger.error(f"Failed to create question {q_num}, aborting")
                return False

        # Step 2: Create the test
        logger.info("Creating test...")
        test_data = {
            "title": test_title,
            "type": "Mathematics",
            "description": f"Year 5-7 Maths Testbook 1 - Test {test_num}. Covers arithmetic, fractions, decimals, geometry, and problem-solving.",
            "instructions": "Answer all 15 questions. Write your answers clearly. You may use rough paper for working out.",
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

        # Step 3: Assign questions to test
        if not self.assign_questions_to_test(test_id, question_ids):
            return False

        # Step 4: Assign to classes (if requested)
        if class_names:
            class_ids = self.get_class_ids_by_names(class_names)
            if class_ids:
                logger.info(f"Assigning test to classes: {', '.join(class_names)}")
                self.assign_test_to_classes(test_id, class_ids)
            else:
                logger.warning("No valid class IDs found for assignment")

        # Step 5: Publish the test (if requested)
        if publish:
            self.publish_test(test_id)
        else:
            logger.info("Test created in DRAFT status (use --publish to publish)")

        logger.info(f"\n{'='*50}")
        logger.info(f"TEST {test_num} CREATED SUCCESSFULLY")
        logger.info(f"{'='*50}")

        return True

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


def main():
    parser = argparse.ArgumentParser(
        description="Create Maths tests from Year 5-7 Testbook 1",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Digitize only (creates test in DRAFT status)
  python create_maths_test_standalone.py --test 1

  # Digitize and publish
  python create_maths_test_standalone.py --test 1 --publish

  # Digitize, assign to classes, and publish
  python create_maths_test_standalone.py --test 1 --publish --assign-classes 6A,7A

  # Recreate existing test and publish
  python create_maths_test_standalone.py --test 1 --reset --publish

  # List available classes
  python create_maths_test_standalone.py --list-classes
        """
    )
    parser.add_argument("--test", type=int, help="Test number (1-20)")
    parser.add_argument("--reset", action="store_true", help="Recreate existing test")
    parser.add_argument("--publish", action="store_true", help="Publish the test after creation")
    parser.add_argument("--assign-classes", type=str,
                        help="Comma-separated list of class names to assign (e.g., '6A,7A')")
    parser.add_argument("--list-classes", action="store_true", help="List available classes")
    args = parser.parse_args()

    # Validate arguments
    if not args.test and not args.list_classes:
        parser.print_help()
        sys.exit(1)

    if args.test and (args.test < 1 or args.test > 20):
        logger.error("Test number must be 1-20")
        sys.exit(1)

    creator = MathsTestCreator()
    if not creator.authenticate():
        sys.exit(1)

    # Handle --list-classes
    if args.list_classes:
        creator.list_classes()
        sys.exit(0)

    # Parse class names
    class_names = None
    if args.assign_classes:
        class_names = [c.strip() for c in args.assign_classes.split(",")]

    # Create the test
    success = creator.create_test(
        args.test,
        reset=args.reset,
        publish=args.publish,
        class_names=class_names
    )
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
