#!/usr/bin/env python3
"""
Maths Test Digitization Script

This script creates Maths tests from the Year 5-7 Maths Testbook 1.
Each test has 15 short-answer questions covering topics like:
- Arithmetic (addition, subtraction, multiplication, division)
- Fractions and decimals
- Geometry (angles, shapes)
- Number sequences and patterns
- Word problems
- Time and measurement

Usage:
    python create_maths_test.py --test 1
    python create_maths_test.py --test 1 --reset  # Delete and recreate
    python create_maths_test.py --all             # Create all tests
"""

import os
import sys
import argparse
import logging
import requests
from typing import Dict, List, Optional
from pathlib import Path

# Add parent directories to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from .answer_keys import ANSWER_KEYS, get_answer, TEST_METADATA

# Configuration
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:9000/api/v1")
ADMIN_EMAIL = os.getenv("DEFAULT_ADMIN_EMAIL", "support@ae-tuition.com")
ADMIN_PASSWORD = os.getenv("DEFAULT_ADMIN_PASSWORD", "Admin123!!")

# Image paths
TESTBOOK_PATH = Path(__file__).parent.parent.parent.parent.parent / "Year_5-7_Maths_Testbook_1"

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class MathsTestCreator:
    """Creates Maths tests via the API."""

    def __init__(self):
        self.session = requests.Session()
        self.token = None
        self.admin_id = None

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
            self.admin_id = data.get("user", {}).get("id")
            self.session.headers["Authorization"] = f"Bearer {self.token}"
            logger.info(f"Authenticated as {ADMIN_EMAIL}")
            return True
        except Exception as e:
            logger.error(f"Authentication failed: {e}")
            return False

    def get_test_image_path(self, test_num: int) -> Optional[Path]:
        """Get the image path for a test page."""
        # Test pages are on odd pages starting from page 3
        # Test 1 = page 3, Test 2 = page 5, etc.
        page_num = (test_num * 2) + 1
        image_name = f"Year 5-7 Maths Testbook 1 26.06.20-{page_num:02d}.png"
        image_path = TESTBOOK_PATH / image_name

        if image_path.exists():
            return image_path
        return None

    def upload_image(self, image_path: Path) -> Optional[str]:
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
            logger.error(f"Failed to upload image {image_path}: {e}")
            return None

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

    def create_test(self, test_num: int, reset: bool = False) -> bool:
        """Create a single Maths test."""
        logger.info(f"\n{'='*50}")
        logger.info(f"Creating Maths Test {test_num}")
        logger.info(f"{'='*50}")

        test_title = f"11+ Maths CEM Style - Test {test_num}"

        # Check if test already exists
        existing_test = self.find_existing_test(test_title)
        if existing_test:
            if reset:
                logger.info(f"Archiving existing test: {existing_test['id']}")
                self.archive_test(existing_test['id'])
            else:
                logger.info(f"Test {test_num} already exists. Use --reset to recreate.")
                return True

        # Get test image
        image_path = self.get_test_image_path(test_num)
        image_url = None

        if image_path:
            logger.info(f"Uploading test image: {image_path.name}")
            image_url = self.upload_image(image_path)
            if image_url:
                logger.info(f"Image uploaded: {image_url[:60]}...")

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
            "description": f"Year 5-7 Maths Testbook 1 - Test {test_num}. This test covers arithmetic, fractions, decimals, geometry, and problem-solving.",
            "instructions": "Answer all 15 questions. Write your answers clearly in the spaces provided. You may use rough paper for working out. Check your answers carefully before submitting.",
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
            result = response.json()
            test_id = result.get("id")
            logger.info(f"Test created successfully: {test_id}")
        except Exception as e:
            logger.error(f"Failed to create test: {e}")
            if hasattr(e, 'response') and e.response is not None:
                logger.error(f"Response: {e.response.text}")
            return False

        # Step 3: Assign questions to test
        if not self.assign_questions_to_test(test_id, question_ids):
            return False

        # Step 4: Publish the test
        self.publish_test(test_id)

        return True

    def find_existing_test(self, title: str) -> Optional[Dict]:
        """Find an existing test by title."""
        try:
            response = self.session.get(f"{API_BASE_URL}/admin/tests")
            response.raise_for_status()
            data = response.json()
            # Handle paginated response
            tests = data.get("tests", data) if isinstance(data, dict) else data

            for test in tests:
                if test.get("title") == title and test.get("status") != "archived":
                    return test
            return None
        except Exception as e:
            logger.error(f"Failed to search tests: {e}")
            return None

    def archive_test(self, test_id: str) -> bool:
        """Archive an existing test (unpublish first if needed)."""
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
                return True
            else:
                logger.error(f"Failed to archive: {response.status_code} - {response.text}")
                return False
        except Exception as e:
            logger.error(f"Failed to archive test: {e}")
            return False

    def publish_test(self, test_id: str) -> bool:
        """Publish a test."""
        try:
            response = self.session.put(
                f"{API_BASE_URL}/admin/tests/{test_id}",
                json={"status": "published"}
            )
            if response.status_code == 200:
                logger.info(f"Test published: {test_id}")
                return True
            else:
                logger.error(f"Failed to publish: {response.status_code} - {response.text}")
                return False
        except Exception as e:
            logger.error(f"Failed to publish test: {e}")
            return False

    def create_all_tests(self, reset: bool = False) -> None:
        """Create all 20 Maths tests."""
        success_count = 0
        for test_num in range(1, 21):
            if self.create_test(test_num, reset):
                success_count += 1

        logger.info(f"\n{'='*50}")
        logger.info(f"Created {success_count}/20 tests successfully")
        logger.info(f"{'='*50}")


def main():
    parser = argparse.ArgumentParser(
        description="Create Maths tests from Year 5-7 Testbook 1"
    )
    parser.add_argument(
        "--test",
        type=int,
        help="Test number to create (1-20)"
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Create all 20 tests"
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Delete existing test and recreate"
    )

    args = parser.parse_args()

    if not args.test and not args.all:
        parser.print_help()
        sys.exit(1)

    creator = MathsTestCreator()

    if not creator.authenticate():
        logger.error("Authentication failed. Exiting.")
        sys.exit(1)

    if args.all:
        creator.create_all_tests(args.reset)
    else:
        if args.test < 1 or args.test > 20:
            logger.error("Test number must be between 1 and 20")
            sys.exit(1)
        creator.create_test(args.test, args.reset)


if __name__ == "__main__":
    main()
