#!/usr/bin/env python3
"""
Create Test from Manual Content

This script uses the manually extracted content from test_content.py to create
properly formatted questions with:
- Q1-10: Multiple choice with answer_options
- Q11-20: Cloze select with answer_options from blanks
- Q21-25: Synonym completion with given_word and letter_template

Usage:
    cd ae-tuition-backend/scripts

    # Digitize only (creates test in DRAFT status)
    python create_test_from_content.py --test 1

    # Digitize and publish
    python create_test_from_content.py --test 1 --publish

    # Digitize, assign to classes, and publish
    python create_test_from_content.py --test 1 --publish --assign-classes 6A,7A

    # Recreate existing test
    python create_test_from_content.py --test 1 --reset --publish

    # List available classes
    python create_test_from_content.py --list-classes
"""

import os
import sys
import json
import time
import logging
import requests
import argparse
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from answer_keys import ANSWER_KEYS, get_answer, TEST_METADATA
from test_content import TEST_CONTENT, get_cloze_data, get_synonym_data

BASE_URL = os.getenv("API_BASE_URL", "http://localhost:9000/api/v1")
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "support@ae-tuition.com")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "Admin123!!")

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class AETuitionClient:
    """Client for AE-Tuition API"""

    def __init__(self, base_url: str):
        self.base_url = base_url
        self.session = requests.Session()
        self.token: Optional[str] = None

    def login(self, email: str, password: str) -> bool:
        try:
            response = self.session.post(
                f"{self.base_url}/auth/login",
                json={"identifier": email, "password": password},
                timeout=30
            )
            if response.status_code == 200:
                data = response.json()
                self.token = data["access_token"]
                self.session.headers.update({
                    "Authorization": f"Bearer {self.token}"
                })
                logger.info(f"Authenticated as {email}")
                return True
            else:
                logger.error(f"Auth failed: {response.status_code}")
                return False
        except requests.RequestException as e:
            logger.error(f"Auth error: {e}")
            return False

    def create_passage(self, passage_data: Dict) -> Optional[str]:
        try:
            response = self.session.post(
                f"{self.base_url}/admin/questions/passages",
                json=passage_data,
                timeout=30
            )
            if response.status_code == 200:
                return response.json()["id"]
            else:
                logger.warning(f"Passage creation failed: {response.status_code} - {response.text}")
        except requests.RequestException as e:
            logger.warning(f"Passage error: {e}")
        return None

    def create_question(self, question_data: Dict) -> Optional[str]:
        try:
            response = self.session.post(
                f"{self.base_url}/admin/questions",
                json=question_data,
                timeout=30
            )
            if response.status_code == 200:
                return response.json()["id"]
            else:
                logger.warning(f"Question creation failed: {response.status_code} - {response.text}")
        except requests.RequestException as e:
            logger.warning(f"Question error: {e}")
        return None

    def create_question_set(self, name: str, subject: str, grade_level: str,
                           question_items: List[Dict]) -> Optional[str]:
        try:
            response = self.session.post(
                f"{self.base_url}/admin/question-sets",
                json={
                    "name": name,
                    "subject": subject,
                    "grade_level": grade_level,
                    "question_items": question_items,
                    "is_active": True
                },
                timeout=30
            )
            if response.status_code == 200:
                return response.json()["id"]
        except requests.RequestException as e:
            logger.warning(f"Question set error: {e}")
        return None

    def create_test(self, test_data: Dict) -> Optional[str]:
        try:
            response = self.session.post(
                f"{self.base_url}/admin/tests",
                json=test_data,
                timeout=30
            )
            if response.status_code == 200:
                return response.json()["id"]
        except requests.RequestException as e:
            logger.warning(f"Test creation error: {e}")
        return None

    def assign_question_sets_to_test(self, test_id: str, question_set_ids: List[str]) -> bool:
        try:
            response = self.session.post(
                f"{self.base_url}/admin/tests/{test_id}/question-sets",
                json={"question_set_ids": question_set_ids},
                timeout=30
            )
            return response.status_code == 200
        except requests.RequestException as e:
            logger.warning(f"Assignment error: {e}")
        return False

    def publish_test(self, test_id: str) -> bool:
        """Publish a test."""
        try:
            response = self.session.put(
                f"{self.base_url}/admin/tests/{test_id}",
                json={"status": "published"},
                timeout=30
            )
            return response.status_code == 200
        except requests.RequestException as e:
            logger.warning(f"Publish error: {e}")
        return False

    def delete_test_by_title(self, title: str) -> bool:
        """Find and delete a test by title"""
        try:
            # Get all tests
            response = self.session.get(
                f"{self.base_url}/admin/tests",
                params={"limit": 100},
                timeout=30
            )
            if response.status_code == 200:
                tests = response.json().get("tests", [])
                for test in tests:
                    if test.get("title") == title:
                        test_id = test["id"]
                        del_response = self.session.delete(
                            f"{self.base_url}/admin/tests/{test_id}",
                            timeout=30
                        )
                        if del_response.status_code in [200, 204]:
                            logger.info(f"Deleted test: {title}")
                            return True
                        else:
                            logger.warning(f"Failed to delete test: {del_response.status_code}")
            return False
        except requests.RequestException as e:
            logger.warning(f"Delete error: {e}")
            return False

    def get_classes(self) -> List[Dict]:
        """Get all available classes."""
        try:
            response = self.session.get(
                f"{self.base_url}/admin/classes",
                timeout=30
            )
            if response.status_code == 200:
                data = response.json()
                # Handle paginated response
                return data.get("classes", data) if isinstance(data, dict) else data
        except requests.RequestException as e:
            logger.warning(f"Get classes error: {e}")
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
                f"{self.base_url}/admin/tests/{test_id}/assign",
                json=assignment_data,
                timeout=30
            )
            if response.status_code == 200:
                assignments = response.json()
                logger.info(f"Test assigned to {len(assignments)} class(es)")
                return True
            else:
                logger.error(f"Failed to assign test: {response.status_code}")
                logger.error(f"Response: {response.text}")
                return False
        except requests.RequestException as e:
            logger.error(f"Failed to assign test: {e}")
            return False


def create_letter_template(answer: str) -> str:
    """Create a letter template hint from the answer word.
    Shows about 30% of the letters as hints."""
    if not answer:
        return ""

    # Show approximately every 3rd letter
    template = []
    for i, char in enumerate(answer):
        if char.isalpha():
            # Show hints at positions 0, 3, 6, etc.
            if i % 3 == 0:
                template.append(char)
            else:
                template.append("_")
        else:
            template.append(char)

    return " ".join(template)


def build_q1_10_question(test_num: int, q_num: int, content: Dict, passage_id: str) -> Dict:
    """Build Q1-10 multiple choice question"""
    q_content = content.get("questions", {}).get(q_num, {})
    answer = get_answer(test_num, q_num)

    q_text = q_content.get("text", f"Question {q_num}")
    options = q_content.get("options", {})

    answer_options = []
    for i, (letter, text) in enumerate(sorted(options.items())):
        answer_options.append({
            "option_text": text,
            "is_correct": answer.lower() == letter.lower(),
            "order_number": i + 1
        })

    return {
        "question_text": q_text,
        "question_type": "multiple_choice",
        "question_format": "passage_based",
        "passage_id": passage_id,
        "subject": "Verbal Reasoning",
        "points": 1,
        "instruction_text": "Read the passage carefully and select the correct answer.",
        "correct_answer": answer.lower(),
        "case_sensitive": False,
        "answer_options": answer_options
    }


def build_q11_20_question(test_num: int, q_num: int, content: Dict, cloze_passage_id: Optional[str]) -> Dict:
    """Build Q11-20 cloze select question with answer options"""
    cloze_data = content.get("cloze", {})
    blanks = cloze_data.get("blanks", {})
    answer = get_answer(test_num, q_num)

    # Get word options for this blank
    options = blanks.get(q_num, [])

    # Build answer_options from the word choices
    answer_options = []
    for i, word in enumerate(options):
        answer_options.append({
            "option_text": word,
            "is_correct": answer.lower() == word.lower(),
            "order_number": i + 1
        })

    question_data = {
        "question_text": f"Select the correct word for blank {q_num}",
        "question_type": "cloze_select",
        "question_format": "passage_based" if cloze_passage_id else "standard",
        "subject": "Verbal Reasoning",
        "points": 1,
        "instruction_text": "Select the correct word to complete the passage.",
        "correct_answer": answer.lower(),
        "case_sensitive": False,
        "answer_options": answer_options
    }

    if cloze_passage_id:
        question_data["passage_id"] = cloze_passage_id

    return question_data


def build_q21_25_question(test_num: int, q_num: int, content: Dict) -> Dict:
    """Build Q21-25 synonym completion question with given_word and letter_template"""
    synonyms = content.get("synonyms", {})
    synonym_data = synonyms.get(q_num, {})
    answer = get_answer(test_num, q_num)

    given_word = synonym_data.get("given", "")
    expected_answer = synonym_data.get("answer", answer)

    # Create letter template hint
    template = create_letter_template(expected_answer)

    return {
        "question_text": f"Find a word meaning the same as: {given_word}",
        "question_type": "synonym_completion",
        "question_format": "standard",
        "subject": "Verbal Reasoning",
        "points": 1,
        "instruction_text": "Complete the word on the right so that it means the same as, or nearly the same as, the word on the left.",
        "correct_answer": expected_answer.lower(),
        "case_sensitive": False,
        "given_word": given_word,
        "letter_template": {
            "template": template,
            "answer": expected_answer
        },
        "answer_options": []
    }


def create_test_from_content(test_num: int, client: AETuitionClient,
                              publish: bool = False, class_names: List[str] = None) -> bool:
    """Create a complete test from manual content

    Args:
        test_num: Test number (1-20)
        client: AETuitionClient instance
        publish: Whether to publish the test after creation
        class_names: List of class names to assign the test to
    """

    content = TEST_CONTENT.get(test_num)
    if not content:
        logger.error(f"No content found for Test {test_num}")
        return False

    passage_data = content.get("passage", {})
    if not passage_data.get("text"):
        logger.error(f"No passage text for Test {test_num}")
        return False

    metadata = TEST_METADATA.get(test_num, {"passage": "Unknown", "author": "Unknown"})

    logger.info(f"\n{'='*50}")
    logger.info(f"Creating Test {test_num}: {metadata['passage']}")
    logger.info(f"{'='*50}")

    # 1. Create reading passage for Q1-10
    logger.info("Creating reading passage...")
    reading_passage = {
        "title": passage_data.get("title", f"Test {test_num} Passage"),
        "content": passage_data.get("text"),
        "subject": "Verbal Reasoning",
        "author": metadata.get("author", "Unknown"),
        "genre": "Educational",
        "reading_level": "Year 5-7"
    }
    if passage_data.get("source"):
        reading_passage["source"] = passage_data["source"]

    reading_passage_id = client.create_passage(reading_passage)
    if not reading_passage_id:
        logger.error("Failed to create reading passage")
        return False
    logger.info(f"  Reading passage created: {reading_passage['title']}")

    # 2. Create cloze passage for Q11-20
    cloze_data = content.get("cloze", {})
    cloze_passage_id = None

    if cloze_data.get("passage_text"):
        logger.info("Creating cloze passage...")
        cloze_passage = {
            "title": f"Test {test_num} - Cloze Passage",
            "content": cloze_data["passage_text"],
            "subject": "Verbal Reasoning",
            "genre": "Cloze Passage",
            "reading_level": "Year 5-7"
        }
        cloze_passage_id = client.create_passage(cloze_passage)
        if cloze_passage_id:
            logger.info(f"  Cloze passage created")
        else:
            logger.warning("  Failed to create cloze passage")

    # 3. Create all 25 questions
    question_ids = []

    # Q1-10: Multiple choice
    logger.info("Creating Q1-10 (multiple choice)...")
    for q_num in range(1, 11):
        q_data = build_q1_10_question(test_num, q_num, content, reading_passage_id)
        q_id = client.create_question(q_data)
        if q_id:
            question_ids.append({"question_id": q_id, "order_number": q_num})
            answer = get_answer(test_num, q_num)
            logger.info(f"    Q{q_num}: multiple_choice, answer: {answer}")
        time.sleep(0.1)

    # Q11-20: Cloze select with options
    logger.info("Creating Q11-20 (cloze select with options)...")
    cloze_blanks = cloze_data.get("blanks", {})
    for q_num in range(11, 21):
        q_data = build_q11_20_question(test_num, q_num, content, cloze_passage_id)
        q_id = client.create_question(q_data)
        if q_id:
            question_ids.append({"question_id": q_id, "order_number": q_num})
            options = cloze_blanks.get(q_num, [])
            answer = get_answer(test_num, q_num)
            logger.info(f"    Q{q_num}: cloze_select, options: {options}, answer: {answer}")
        time.sleep(0.1)

    # Q21-25: Synonym completion
    logger.info("Creating Q21-25 (synonym completion with letter hints)...")
    synonyms = content.get("synonyms", {})
    for q_num in range(21, 26):
        q_data = build_q21_25_question(test_num, q_num, content)
        q_id = client.create_question(q_data)
        if q_id:
            question_ids.append({"question_id": q_id, "order_number": q_num})
            syn = synonyms.get(q_num, {})
            given = syn.get("given", "")
            answer = get_answer(test_num, q_num)
            template = q_data.get("letter_template", {}).get("template", "")
            logger.info(f"    Q{q_num}: synonym_completion, given: {given}, template: {template}, answer: {answer}")
        time.sleep(0.1)

    logger.info(f"Created {len(question_ids)} questions")

    # 4. Create question set
    logger.info("Creating question set...")
    qs_id = client.create_question_set(
        name=f"VR CEM Test {test_num} (Manual)",
        subject="Verbal Reasoning",
        grade_level="Year 5-7",
        question_items=question_ids
    )
    if not qs_id:
        logger.error("Failed to create question set")
        return False
    logger.info(f"  Question set created")

    # 5. Create test
    logger.info("Creating test...")
    test_data = {
        "title": f"11+ Verbal Reasoning CEM Style - Test {test_num}",
        "description": f"Test {test_num} from 11+ Verbal Reasoning Year 5-7 CEM Style Testbook 1. "
                      f"Based on passage: {metadata['passage']}. Contains 25 questions.",
        "type": "Verbal Reasoning",
        "test_format": "mixed_format",
        "duration_minutes": 20,
        "warning_intervals": [10, 5, 1],
        "pass_mark": 50,
        "instructions": """Answer all 25 questions within 20 minutes.

Questions 1-10: Reading Comprehension
- Read the passage carefully before answering
- Select the correct answer from options a, b, c, or d

Questions 11-20: Cloze Passage
- Read the passage about Bats
- Select the correct word for each numbered blank

Questions 21-25: Synonyms
- Find words that mean the same as the given word
- Use the letter hint template as a guide
- Type the complete word as your answer""",
        "question_order": "sequential"
    }

    test_id = client.create_test(test_data)
    if not test_id:
        logger.error("Failed to create test")
        return False

    # 6. Assign question set to test
    if client.assign_question_sets_to_test(test_id, [qs_id]):
        logger.info(f"  Test created and linked successfully!")
    else:
        logger.error("Failed to link question set")
        return False

    # 7. Assign to classes (if requested)
    if class_names:
        class_ids = client.get_class_ids_by_names(class_names)
        if class_ids:
            logger.info(f"Assigning test to classes: {', '.join(class_names)}")
            client.assign_test_to_classes(test_id, class_ids)
        else:
            logger.warning("No valid class IDs found for assignment")

    # 8. Publish the test (if requested)
    if publish:
        if client.publish_test(test_id):
            logger.info(f"  Test published successfully!")
        else:
            logger.error("Failed to publish test")
            return False
    else:
        logger.info("Test created in DRAFT status (use --publish to publish)")

    logger.info(f"\n{'='*50}")
    logger.info(f"TEST {test_num} CREATED SUCCESSFULLY")
    logger.info(f"{'='*50}")

    return True


def main():
    parser = argparse.ArgumentParser(
        description='Create Verbal Reasoning Test from Manual Content',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Digitize only (creates test in DRAFT status)
  python create_test_from_content.py --test 1

  # Digitize and publish
  python create_test_from_content.py --test 1 --publish

  # Digitize, assign to classes, and publish
  python create_test_from_content.py --test 1 --publish --assign-classes 6A,7A

  # Recreate existing test and publish
  python create_test_from_content.py --test 1 --reset --publish

  # List available classes
  python create_test_from_content.py --list-classes
        """
    )
    parser.add_argument('--test', type=int, help='Test number (1-20)')
    parser.add_argument('--reset', action='store_true', help='Delete existing test first')
    parser.add_argument('--publish', action='store_true', help='Publish the test after creation')
    parser.add_argument('--assign-classes', type=str,
                        help="Comma-separated list of class names to assign (e.g., '6A,7A')")
    parser.add_argument('--list-classes', action='store_true', help='List available classes')
    args = parser.parse_args()

    # Validate arguments
    if not args.test and not args.list_classes:
        parser.print_help()
        sys.exit(1)

    if args.test and (args.test < 1 or args.test > 20):
        logger.error("Test number must be between 1 and 20")
        sys.exit(1)

    client = AETuitionClient(BASE_URL)

    logger.info("Authenticating...")
    if not client.login(ADMIN_EMAIL, ADMIN_PASSWORD):
        logger.error("Authentication failed!")
        sys.exit(1)

    # Handle --list-classes
    if args.list_classes:
        client.list_classes()
        sys.exit(0)

    test_title = f"11+ Verbal Reasoning CEM Style - Test {args.test}"

    if args.reset:
        logger.info(f"Looking for existing test: {test_title}")
        client.delete_test_by_title(test_title)

    # Parse class names
    class_names = None
    if args.assign_classes:
        class_names = [c.strip() for c in args.assign_classes.split(",")]

    success = create_test_from_content(
        args.test, client,
        publish=args.publish,
        class_names=class_names
    )

    if success:
        logger.info("\nDone! Test created successfully.")
    else:
        logger.error("\nFailed to create test.")
        sys.exit(1)


if __name__ == "__main__":
    main()
