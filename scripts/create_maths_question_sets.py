#!/usr/bin/env python3
"""
Create question sets for existing Maths tests.

This script:
1. Finds all published Maths tests
2. Gets the questions assigned to each test
3. Creates a question set for each test
4. Associates the question set with the test

Usage:
    cd ae-tuition-backend
    python scripts/create_maths_question_sets.py
"""

import os
import sys
import requests
import logging

# Configuration
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:9000/api/v1")
ADMIN_EMAIL = os.getenv("DEFAULT_ADMIN_EMAIL", "support@ae-tuition.com")
ADMIN_PASSWORD = os.getenv("DEFAULT_ADMIN_PASSWORD", "Admin123!!")

# Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class QuestionSetCreator:
    def __init__(self):
        self.session = requests.Session()
        self.token = None

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

    def get_all_tests(self):
        """Get all tests."""
        try:
            # Get all tests with pagination
            all_tests = []
            page = 1
            while True:
                response = self.session.get(
                    f"{API_BASE_URL}/admin/tests",
                    params={"page": page, "limit": 100}
                )
                response.raise_for_status()
                data = response.json()
                tests = data.get("tests", data) if isinstance(data, dict) else data
                if not tests:
                    break
                all_tests.extend(tests)
                if len(tests) < 100:
                    break
                page += 1
            return all_tests
        except Exception as e:
            logger.error(f"Failed to get tests: {e}")
            return []

    def get_test_details(self, test_id: str):
        """Get detailed test info including questions."""
        try:
            response = self.session.get(f"{API_BASE_URL}/admin/tests/{test_id}")
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to get test {test_id}: {e}")
            return None

    def get_existing_question_sets(self):
        """Get all existing question sets."""
        try:
            all_sets = []
            page = 1
            while True:
                response = self.session.get(
                    f"{API_BASE_URL}/admin/question-sets",
                    params={"page": page, "limit": 100}
                )
                response.raise_for_status()
                data = response.json()
                sets = data.get("question_sets", [])
                if not sets:
                    break
                all_sets.extend(sets)
                if len(sets) < 100:
                    break
                page += 1
            return all_sets
        except Exception as e:
            logger.error(f"Failed to get question sets: {e}")
            return []

    def create_question_set(self, name: str, subject: str, question_ids: list, grade_level: str = "Year 5-7"):
        """Create a question set with the given questions."""
        question_items = [
            {
                "question_id": qid,
                "order_number": idx + 1
            }
            for idx, qid in enumerate(question_ids)
        ]

        data = {
            "name": name,
            "subject": subject,
            "grade_level": grade_level,
            "question_items": question_items
        }

        try:
            response = self.session.post(
                f"{API_BASE_URL}/admin/question-sets",
                json=data
            )
            response.raise_for_status()
            result = response.json()
            logger.info(f"  Created question set: {name} ({len(question_ids)} questions)")
            return result.get("id")
        except Exception as e:
            logger.error(f"Failed to create question set: {e}")
            if hasattr(e, 'response') and e.response:
                logger.error(f"Response: {e.response.text}")
            return None

    def assign_question_set_to_test(self, test_id: str, question_set_id: str):
        """Assign a question set to a test."""
        data = {
            "question_set_ids": [question_set_id]
        }

        try:
            response = self.session.post(
                f"{API_BASE_URL}/admin/tests/{test_id}/question-sets",
                json=data
            )
            response.raise_for_status()
            logger.info(f"  Assigned question set to test")
            return True
        except Exception as e:
            logger.error(f"Failed to assign question set: {e}")
            if hasattr(e, 'response') and e.response:
                logger.error(f"Response: {e.response.text}")
            return False

    def run(self):
        """Main execution."""
        logger.info("=" * 60)
        logger.info("Creating Question Sets for Maths Tests")
        logger.info("=" * 60)

        # Get existing question sets to avoid duplicates
        existing_sets = self.get_existing_question_sets()
        existing_set_names = {s.get("name") for s in existing_sets}
        logger.info(f"Found {len(existing_sets)} existing question sets")

        # Get all tests
        all_tests = self.get_all_tests()
        logger.info(f"Found {len(all_tests)} total tests")

        # Debug: show unique types and statuses
        types = set(t.get("type", "N/A") for t in all_tests)
        statuses = set(t.get("status", "N/A") for t in all_tests)
        logger.info(f"Test types: {types}")
        logger.info(f"Test statuses: {statuses}")

        # Type can be "Mathematics" or "MATHEMATICS" depending on API version
        maths_tests = [t for t in all_tests if t.get("type", "").upper() == "MATHEMATICS" and t.get("status", "").upper() == "PUBLISHED"]
        logger.info(f"Found {len(maths_tests)} published Maths tests")

        success_count = 0
        skip_count = 0
        fail_count = 0

        for test in sorted(maths_tests, key=lambda t: t.get("title", "")):
            test_id = test.get("id")
            test_title = test.get("title", "Unknown")

            # Extract test number from title
            try:
                test_num = int(test_title.split("Test ")[-1])
            except:
                test_num = 0

            set_name = f"11+ Maths Test {test_num} Questions"

            logger.info(f"\nProcessing: {test_title}")

            # Check if question set already exists
            if set_name in existing_set_names:
                logger.info(f"  Skipping - question set already exists")
                skip_count += 1
                continue

            # Get test details including questions
            test_details = self.get_test_details(test_id)
            if not test_details:
                logger.error(f"  Failed to get test details")
                fail_count += 1
                continue

            # Get question IDs from test_questions
            test_questions = test_details.get("test_questions", [])
            if not test_questions:
                logger.warning(f"  No questions found for test")
                fail_count += 1
                continue

            # Sort by order_number and extract question IDs
            test_questions_sorted = sorted(test_questions, key=lambda q: q.get("order_number", 0))
            question_ids = [q.get("question_id") for q in test_questions_sorted]

            logger.info(f"  Found {len(question_ids)} questions")

            # Create question set
            question_set_id = self.create_question_set(
                name=set_name,
                subject="Mathematics",
                question_ids=question_ids,
                grade_level="Year 5-7"
            )

            if question_set_id:
                # Assign question set to test
                if self.assign_question_set_to_test(test_id, question_set_id):
                    success_count += 1
                else:
                    fail_count += 1
            else:
                fail_count += 1

        logger.info("\n" + "=" * 60)
        logger.info(f"COMPLETED: {success_count} created, {skip_count} skipped, {fail_count} failed")
        logger.info("=" * 60)

        return fail_count == 0


def main():
    creator = QuestionSetCreator()

    if not creator.authenticate():
        sys.exit(1)

    success = creator.run()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
