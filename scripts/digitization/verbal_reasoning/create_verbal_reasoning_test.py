#!/usr/bin/env python3
"""
Script to digitize the 11+ Verbal Reasoning Year 5-7 CEM Style Testbook 1
into the AE-Tuition platform.

This script:
1. Authenticates as admin
2. Uploads test page images to S3
3. Creates text-based questions for tests with extracted content
4. Falls back to image-based questions for tests without extracted content
5. Groups questions into question sets (one per test)
6. Creates tests linked to question sets

Usage:
    python scripts/create_verbal_reasoning_test.py [--reset]

Requirements:
    - requests library
    - Backend running at http://localhost:9000
    - Valid admin credentials
"""

import os
import sys
import json
import time
import logging
import requests
import argparse
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict

# Add the scripts directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from answer_keys import ANSWER_KEYS, get_question_type, get_answer, TEST_METADATA
from test_content import TEST_CONTENT, has_extracted_content, get_passage, get_question, get_cloze_data, get_synonym_data
from question_types import (
    get_q11_20_type, get_q21_25_type,
    is_q11_20_text_capable, is_q21_25_text_capable,
    get_instruction, QUESTION_INSTRUCTIONS
)

# Configuration
BASE_URL = os.getenv("API_BASE_URL", "http://localhost:9000/api/v1")
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "support@ae-tuition.com")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "Admin123!!")
IMAGES_DIR = os.getenv(
    "IMAGES_DIR",
    "/Users/timothymbaka/tesh/kaziflex/ae-tuition/11+_Verbal_Reasoning_Year_5-7_CEM_Style_Testbook_1"
)

# Progress file for checkpoint/resume
PROGRESS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "progress.json")

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(os.path.join(os.path.dirname(os.path.abspath(__file__)), "digitization.log"))
    ]
)
logger = logging.getLogger(__name__)


@dataclass
class ImageUploadResult:
    """Result from uploading an image to S3"""
    s3_key: str
    public_url: str
    file_name: str


class ProgressTracker:
    """Track progress for checkpoint/resume support"""

    def __init__(self, checkpoint_file: str = PROGRESS_FILE):
        self.checkpoint_file = checkpoint_file
        self.progress = self._load()

    def _load(self) -> Dict:
        """Load progress from checkpoint file"""
        if os.path.exists(self.checkpoint_file):
            try:
                with open(self.checkpoint_file) as f:
                    return json.load(f)
            except json.JSONDecodeError:
                logger.warning("Corrupted progress file, starting fresh")
        return self._empty_progress()

    def _empty_progress(self) -> Dict:
        return {
            "uploaded_images": {},
            "uploaded_passage_images": {},
            "created_passages": {},
            "created_questions": {},
            "created_question_sets": {},
            "created_tests": {}
        }

    def save(self):
        """Save progress to checkpoint file"""
        with open(self.checkpoint_file, 'w') as f:
            json.dump(self.progress, f, indent=2)

    def is_image_uploaded(self, filename: str) -> bool:
        return filename in self.progress["uploaded_images"]

    def get_image_upload_result(self, filename: str) -> Optional[Dict]:
        return self.progress["uploaded_images"].get(filename)

    def mark_image_uploaded(self, filename: str, result: Dict):
        self.progress["uploaded_images"][filename] = result
        self.save()

    def is_question_created(self, test_num: int, q_num: int) -> bool:
        key = f"{test_num}_{q_num}"
        return key in self.progress["created_questions"]

    def get_question_id(self, test_num: int, q_num: int) -> Optional[str]:
        key = f"{test_num}_{q_num}"
        return self.progress["created_questions"].get(key)

    def mark_question_created(self, test_num: int, q_num: int, question_id: str):
        key = f"{test_num}_{q_num}"
        self.progress["created_questions"][key] = question_id
        self.save()

    def is_question_set_created(self, test_num: int) -> bool:
        return str(test_num) in self.progress["created_question_sets"]

    def get_question_set_id(self, test_num: int) -> Optional[str]:
        return self.progress["created_question_sets"].get(str(test_num))

    def mark_question_set_created(self, test_num: int, question_set_id: str):
        self.progress["created_question_sets"][str(test_num)] = question_set_id
        self.save()

    def is_test_created(self, test_num: int) -> bool:
        return str(test_num) in self.progress["created_tests"]

    def get_test_id(self, test_num: int) -> Optional[str]:
        return self.progress["created_tests"].get(str(test_num))

    def mark_test_created(self, test_num: int, test_id: str):
        self.progress["created_tests"][str(test_num)] = test_id
        self.save()

    # Passage image tracking
    def is_passage_image_uploaded(self, test_num: int) -> bool:
        return str(test_num) in self.progress.get("uploaded_passage_images", {})

    def get_passage_image_result(self, test_num: int) -> Optional[Dict]:
        return self.progress.get("uploaded_passage_images", {}).get(str(test_num))

    def mark_passage_image_uploaded(self, test_num: int, result: Dict):
        if "uploaded_passage_images" not in self.progress:
            self.progress["uploaded_passage_images"] = {}
        self.progress["uploaded_passage_images"][str(test_num)] = result
        self.save()

    # Passage tracking
    def is_passage_created(self, test_num: int) -> bool:
        return str(test_num) in self.progress.get("created_passages", {})

    def get_passage_id(self, test_num: int) -> Optional[str]:
        return self.progress.get("created_passages", {}).get(str(test_num))

    def mark_passage_created(self, test_num: int, passage_id: str):
        if "created_passages" not in self.progress:
            self.progress["created_passages"] = {}
        self.progress["created_passages"][str(test_num)] = passage_id
        self.save()

    def reset(self):
        """Reset all progress"""
        self.progress = self._empty_progress()
        self.save()
        logger.info("Progress reset successfully")


class AETuitionClient:
    """Client for interacting with AE-Tuition API"""

    def __init__(self, base_url: str):
        self.base_url = base_url
        self.session = requests.Session()
        self.token: Optional[str] = None

    def login(self, email: str, password: str) -> bool:
        """Authenticate and store token"""
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
                logger.error(f"Authentication failed: {response.status_code} - {response.text}")
                return False
        except requests.RequestException as e:
            logger.error(f"Authentication error: {e}")
            return False

    def upload_image(self, file_path: str, max_retries: int = 3) -> Optional[ImageUploadResult]:
        """Upload image to S3 via API with retry logic"""
        for attempt in range(max_retries):
            try:
                with open(file_path, 'rb') as f:
                    files = {'file': (os.path.basename(file_path), f, 'image/png')}
                    response = self.session.post(
                        f"{self.base_url}/admin/questions/upload-image",
                        files=files,
                        timeout=120
                    )
                if response.status_code == 200:
                    data = response.json()
                    return ImageUploadResult(
                        s3_key=data["s3_key"],
                        public_url=data["public_url"],
                        file_name=data["file_name"]
                    )
                else:
                    logger.warning(f"Upload attempt {attempt + 1} failed: {response.status_code} - {response.text}")
            except requests.RequestException as e:
                logger.warning(f"Upload attempt {attempt + 1} error: {e}")

            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)  # Exponential backoff

        logger.error(f"Failed to upload {file_path} after {max_retries} attempts")
        return None

    def create_question(self, question_data: Dict, max_retries: int = 3) -> Optional[str]:
        """Create question and return ID"""
        for attempt in range(max_retries):
            try:
                response = self.session.post(
                    f"{self.base_url}/admin/questions",
                    json=question_data,
                    timeout=30
                )
                if response.status_code == 200:
                    return response.json()["id"]
                else:
                    logger.warning(f"Question creation attempt {attempt + 1} failed: {response.status_code} - {response.text}")
            except requests.RequestException as e:
                logger.warning(f"Question creation attempt {attempt + 1} error: {e}")

            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)

        return None

    def create_question_set(self, name: str, subject: str, grade_level: str,
                           question_items: List[Dict], max_retries: int = 3) -> Optional[str]:
        """Create question set and return ID"""
        for attempt in range(max_retries):
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
                else:
                    logger.warning(f"Question set creation attempt {attempt + 1} failed: {response.status_code} - {response.text}")
            except requests.RequestException as e:
                logger.warning(f"Question set creation attempt {attempt + 1} error: {e}")

            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)

        return None

    def create_test(self, test_data: Dict, max_retries: int = 3) -> Optional[str]:
        """Create test and return ID"""
        for attempt in range(max_retries):
            try:
                response = self.session.post(
                    f"{self.base_url}/admin/tests",
                    json=test_data,
                    timeout=30
                )
                if response.status_code == 200:
                    return response.json()["id"]
                else:
                    logger.warning(f"Test creation attempt {attempt + 1} failed: {response.status_code} - {response.text}")
            except requests.RequestException as e:
                logger.warning(f"Test creation attempt {attempt + 1} error: {e}")

            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)

        return None

    def assign_question_sets_to_test(self, test_id: str, question_set_ids: List[str],
                                     max_retries: int = 3) -> bool:
        """Assign question sets to test"""
        for attempt in range(max_retries):
            try:
                response = self.session.post(
                    f"{self.base_url}/admin/tests/{test_id}/question-sets",
                    json={"question_set_ids": question_set_ids},
                    timeout=30
                )
                if response.status_code == 200:
                    return True
                else:
                    logger.warning(f"Question set assignment attempt {attempt + 1} failed: {response.status_code} - {response.text}")
            except requests.RequestException as e:
                logger.warning(f"Question set assignment attempt {attempt + 1} error: {e}")

            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)

        return False

    def upload_passage_image(self, file_path: str, max_retries: int = 3) -> Optional[ImageUploadResult]:
        """Upload image for reading passage via API with retry logic"""
        for attempt in range(max_retries):
            try:
                with open(file_path, 'rb') as f:
                    files = {'file': (os.path.basename(file_path), f, 'image/png')}
                    response = self.session.post(
                        f"{self.base_url}/admin/questions/passages/upload-image",
                        files=files,
                        timeout=120
                    )
                if response.status_code == 200:
                    data = response.json()
                    return ImageUploadResult(
                        s3_key=data["s3_key"],
                        public_url=data["public_url"],
                        file_name=data["file_name"]
                    )
                else:
                    logger.warning(f"Passage image upload attempt {attempt + 1} failed: {response.status_code} - {response.text}")
            except requests.RequestException as e:
                logger.warning(f"Passage image upload attempt {attempt + 1} error: {e}")

            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)

        logger.error(f"Failed to upload passage image {file_path} after {max_retries} attempts")
        return None

    def create_passage(self, passage_data: Dict, max_retries: int = 3) -> Optional[str]:
        """Create reading passage and return ID"""
        for attempt in range(max_retries):
            try:
                response = self.session.post(
                    f"{self.base_url}/admin/questions/passages",
                    json=passage_data,
                    timeout=30
                )
                if response.status_code == 200:
                    return response.json()["id"]
                else:
                    logger.warning(f"Passage creation attempt {attempt + 1} failed: {response.status_code} - {response.text}")
            except requests.RequestException as e:
                logger.warning(f"Passage creation attempt {attempt + 1} error: {e}")

            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)

        return None


def get_test_pages(test_num: int) -> List[int]:
    """
    Get page numbers for a specific test.
    Each test spans approximately 4 pages.
    Page 1 = cover, Pages 2-5 = Test 1, etc.
    """
    start_page = 2 + (test_num - 1) * 4
    return list(range(start_page, min(start_page + 4, 82)))


def get_page_for_question(test_num: int, q_num: int) -> int:
    """
    Get the page number that contains a specific question.
    """
    pages = get_test_pages(test_num)

    # Mapping based on typical test layout:
    # Page 1: Passage + Q1
    # Page 2: Q2-7
    # Page 3: Q8-10 + Q11-15 (or start of cloze)
    # Page 4: Q16-25

    if q_num == 1:
        return pages[0] if len(pages) > 0 else pages[0]
    elif 2 <= q_num <= 7:
        return pages[1] if len(pages) > 1 else pages[0]
    elif 8 <= q_num <= 15:
        return pages[2] if len(pages) > 2 else pages[-1]
    else:  # q_num 16-25
        return pages[3] if len(pages) > 3 else pages[-1]


def build_text_based_mc_question(test_num: int, q_num: int, passage_id: Optional[str] = None) -> Optional[Dict]:
    """Build text-based multiple choice question for Q1-10 (reading comprehension)"""
    question_content = get_question(test_num, q_num)
    if not question_content:
        return None

    answer = get_answer(test_num, q_num)

    # Build answer options with full text
    answer_options = []
    for i, (letter, text) in enumerate(question_content["options"].items()):
        answer_options.append({
            "option_text": text,
            "is_correct": answer.lower() == letter.lower(),
            "order_number": i + 1
        })

    return {
        "question_text": question_content["text"],
        "question_type": "multiple_choice",
        "question_format": "passage_based" if passage_id else "standard",
        "passage_id": passage_id,
        "subject": "Verbal Reasoning",
        "points": 1,
        "instruction_text": "Read the passage carefully and select the correct answer.",
        "correct_answer": answer.lower(),
        "case_sensitive": False,
        "answer_options": answer_options
    }


def build_text_based_cloze_question(test_num: int, q_num: int) -> Optional[Dict]:
    """Build text-based cloze select question for Q11-20 (where applicable)"""
    cloze_data = get_cloze_data(test_num)
    if not cloze_data or not cloze_data.get("passage_text"):
        return None

    blanks = cloze_data.get("blanks", {})
    if q_num not in blanks:
        return None

    options = blanks[q_num]
    answer = get_answer(test_num, q_num)

    # Build answer options
    answer_options = []
    for i, option in enumerate(options):
        answer_options.append({
            "option_text": option,
            "is_correct": option.lower() == answer.lower(),
            "order_number": i + 1
        })

    q11_20_type = get_q11_20_type(test_num)
    instruction = get_instruction(q11_20_type)

    return {
        "question_text": f"Question {q_num}: Select the correct word for blank {q_num}.",
        "question_type": "cloze_select",
        "question_format": "standard",
        "subject": "Verbal Reasoning",
        "points": 1,
        "instruction_text": instruction,
        "correct_answer": answer.lower(),
        "case_sensitive": False,
        "answer_options": answer_options
    }


def build_text_based_synonym_question(test_num: int, q_num: int) -> Optional[Dict]:
    """Build text-based synonym/antonym question for Q21-25 (where applicable)"""
    synonym_data = get_synonym_data(test_num, q_num)
    if not synonym_data:
        return None

    given_word = synonym_data.get("given")
    answer = get_answer(test_num, q_num)

    q21_25_type = get_q21_25_type(test_num)
    instruction = get_instruction(q21_25_type)

    return {
        "question_text": f"Word: {given_word}",
        "question_type": "synonym_completion",
        "question_format": "standard",
        "subject": "Verbal Reasoning",
        "points": 1,
        "instruction_text": instruction,
        "correct_answer": answer.lower(),
        "case_sensitive": False,
        "answer_options": []
    }


def build_image_based_question(test_num: int, q_num: int, image_data: Dict, passage_id: Optional[str] = None) -> Dict:
    """Build image-based question for any question type"""
    q_type = get_question_type(q_num)
    answer = get_answer(test_num, q_num)
    metadata = TEST_METADATA.get(test_num, {"passage": "Unknown", "author": "Unknown"})

    # Determine specific question format for Q11-20 and Q21-25
    if 11 <= q_num <= 20:
        format_type = get_q11_20_type(test_num)
        instruction = get_instruction(format_type)
    elif 21 <= q_num <= 25:
        format_type = get_q21_25_type(test_num)
        instruction = get_instruction(format_type)
    else:
        instruction = "Read the passage and select the correct answer (a, b, c, or d)."

    # Determine question format
    is_passage_based = 1 <= q_num <= 10 and passage_id is not None
    question_format = "passage_based" if is_passage_based else "standard"

    base_data = {
        "question_type": q_type,
        "question_format": question_format,
        "image_url": image_data["public_url"],
        "s3_key": image_data["s3_key"],
        "subject": "Verbal Reasoning",
        "points": 1,
        "instruction_text": instruction,
        "explanation": f"Test {test_num}, Question {q_num} - {metadata['passage']}",
        "case_sensitive": False,
        "answer_options": []
    }

    # Link to passage for questions 1-10
    if is_passage_based:
        base_data["passage_id"] = passage_id

    if q_type == "multiple_choice":
        base_data["correct_answer"] = answer.lower()
        base_data["answer_options"] = [
            {"option_text": "a", "is_correct": answer.lower() == "a", "order_number": 1},
            {"option_text": "b", "is_correct": answer.lower() == "b", "order_number": 2},
            {"option_text": "c", "is_correct": answer.lower() == "c", "order_number": 3},
            {"option_text": "d", "is_correct": answer.lower() == "d", "order_number": 4}
        ]
    else:
        base_data["correct_answer"] = answer.lower()

    return base_data


def build_passage_data(test_num: int, image_data: Optional[Dict] = None) -> Dict:
    """Build reading passage payload"""
    metadata = TEST_METADATA.get(test_num, {"passage": "Unknown", "author": "Unknown"})
    passage_content = get_passage(test_num)

    passage_data = {
        "title": f"Test {test_num}: {metadata['passage']}",
        "subject": "Verbal Reasoning",
        "author": metadata.get("author", "Unknown"),
        "genre": "Educational",
        "reading_level": "Year 5-7"
    }

    # Use text content if available, otherwise use image
    if passage_content.get("text"):
        passage_data["content"] = passage_content["text"]
        if passage_content.get("source"):
            passage_data["source"] = passage_content["source"]
    elif image_data:
        passage_data["image_url"] = image_data["public_url"]
        passage_data["s3_key"] = image_data["s3_key"]

    return passage_data


def build_test_data(test_num: int) -> Dict:
    """Build test payload"""
    metadata = TEST_METADATA.get(test_num, {"passage": "Unknown", "author": "Unknown"})
    q11_20_type = get_q11_20_type(test_num)
    q21_25_type = get_q21_25_type(test_num)

    return {
        "title": f"11+ Verbal Reasoning CEM Style - Test {test_num}",
        "description": f"Test {test_num} from 11+ Verbal Reasoning Year 5-7 CEM Style Testbook 1. "
                      f"Based on passage: {metadata['passage']}. "
                      f"Contains 25 questions: Reading Comprehension (Q1-10), "
                      f"{q11_20_type.replace('_', ' ').title()} (Q11-20), "
                      f"and {q21_25_type.replace('_', ' ').title()} (Q21-25).",
        "type": "Verbal Reasoning",
        "test_format": "mixed_format",
        "duration_minutes": 20,
        "warning_intervals": [10, 5, 1],
        "pass_mark": 50,
        "instructions": f"""Answer all 25 questions within 20 minutes.

Questions 1-10: Reading Comprehension
- Read the passage carefully before answering
- Select the correct answer from options a, b, c, or d

Questions 11-20: {q11_20_type.replace('_', ' ').title()}
- {get_instruction(q11_20_type)}

Questions 21-25: {q21_25_type.replace('_', ' ').title()}
- {get_instruction(q21_25_type)}""",
        "question_order": "sequential"
    }


def main():
    """Main execution function"""
    parser = argparse.ArgumentParser(description='Digitize Verbal Reasoning Testbook')
    parser.add_argument('--reset', action='store_true', help='Reset progress and start fresh')
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("Starting digitization of Verbal Reasoning Testbook 1")
    logger.info("=" * 60)

    # Initialize client and tracker
    client = AETuitionClient(BASE_URL)
    tracker = ProgressTracker()

    if args.reset:
        tracker.reset()

    # Step 1: Authenticate
    logger.info("Step 1: Authenticating...")
    if not client.login(ADMIN_EMAIL, ADMIN_PASSWORD):
        logger.error("Failed to authenticate. Exiting.")
        sys.exit(1)
    logger.info("Authentication successful")

    # Step 2: Get list of image files (sorted)
    logger.info("Step 2: Loading image files...")
    image_files = sorted([
        f for f in os.listdir(IMAGES_DIR)
        if f.endswith('.png') and '21.07.21' in f
    ])
    logger.info(f"Found {len(image_files)} image files")

    # Step 3: Upload images
    logger.info("Step 3: Uploading images to S3...")
    uploaded_images = {}

    for i, filename in enumerate(image_files):
        if tracker.is_image_uploaded(filename):
            logger.info(f"[{i+1}/{len(image_files)}] Skipping already uploaded: {filename}")
            uploaded_images[filename] = tracker.get_image_upload_result(filename)
            continue

        file_path = os.path.join(IMAGES_DIR, filename)
        logger.info(f"[{i+1}/{len(image_files)}] Uploading: {filename}")

        result = client.upload_image(file_path)
        if result:
            uploaded_images[filename] = {
                "s3_key": result.s3_key,
                "public_url": result.public_url
            }
            tracker.mark_image_uploaded(filename, uploaded_images[filename])
            logger.info(f"  Uploaded successfully")
        else:
            logger.error(f"  Failed to upload {filename}")

        time.sleep(0.3)

    logger.info(f"Uploaded {len(uploaded_images)} images")

    # Step 4: Create passages, questions and tests for each of 20 tests
    logger.info("Step 4: Creating passages, questions, question sets, and tests...")

    stats = {
        "text_based_questions": 0,
        "image_based_questions": 0,
        "passages_created": 0,
        "tests_created": 0
    }

    for test_num in range(1, 21):
        logger.info(f"\n{'='*40}")
        logger.info(f"Processing Test {test_num}")
        logger.info(f"{'='*40}")

        has_content = has_extracted_content(test_num)
        q11_20_type = get_q11_20_type(test_num)
        q21_25_type = get_q21_25_type(test_num)

        logger.info(f"  Content available: {has_content}")
        logger.info(f"  Q11-20 format: {q11_20_type}")
        logger.info(f"  Q21-25 format: {q21_25_type}")

        # Step 4a: Create reading passage
        passage_id = None
        pages = get_test_pages(test_num)
        passage_page = pages[0]
        passage_filename = f"11+ Verbal Reasoning Year 5-7 CEM Style Testbook 1 21.07.21-{passage_page:02d}.png"

        if tracker.is_passage_created(test_num):
            passage_id = tracker.get_passage_id(test_num)
            logger.info(f"  Passage already created (ID: {passage_id[:8]}...)")
        else:
            # Upload passage image
            passage_image_data = None
            if tracker.is_passage_image_uploaded(test_num):
                passage_image_data = tracker.get_passage_image_result(test_num)
            else:
                passage_file_path = os.path.join(IMAGES_DIR, passage_filename)
                if os.path.exists(passage_file_path):
                    logger.info(f"  Uploading passage image...")
                    result = client.upload_passage_image(passage_file_path)
                    if result:
                        passage_image_data = {
                            "s3_key": result.s3_key,
                            "public_url": result.public_url
                        }
                        tracker.mark_passage_image_uploaded(test_num, passage_image_data)

            # Create passage
            passage_data = build_passage_data(test_num, passage_image_data)
            passage_id = client.create_passage(passage_data)
            if passage_id:
                tracker.mark_passage_created(test_num, passage_id)
                stats["passages_created"] += 1
                content_type = "TEXT" if has_content else "IMAGE"
                logger.info(f"  Passage created ({content_type})")
            else:
                logger.error(f"  Failed to create passage")

            time.sleep(0.2)

        # Step 4b: Create questions
        question_ids = []

        for q_num in range(1, 26):
            if tracker.is_question_created(test_num, q_num):
                q_id = tracker.get_question_id(test_num, q_num)
                question_ids.append({"question_id": q_id, "order_number": q_num})
                continue

            question_data = None
            is_text_based = False

            # Try to create text-based question
            if 1 <= q_num <= 10 and has_content:
                # Reading comprehension - text based if content available
                question_data = build_text_based_mc_question(test_num, q_num, passage_id)
                is_text_based = question_data is not None

            elif 11 <= q_num <= 20 and has_content and is_q11_20_text_capable(test_num):
                # Cloze questions - text based if format allows
                question_data = build_text_based_cloze_question(test_num, q_num)
                is_text_based = question_data is not None

            elif 21 <= q_num <= 25 and has_content and is_q21_25_text_capable(test_num):
                # Synonym questions - text based if format allows
                question_data = build_text_based_synonym_question(test_num, q_num)
                is_text_based = question_data is not None

            # Fall back to image-based if text not available
            if question_data is None:
                page_num = get_page_for_question(test_num, q_num)
                filename = f"11+ Verbal Reasoning Year 5-7 CEM Style Testbook 1 21.07.21-{page_num:02d}.png"

                if filename in uploaded_images:
                    image_data = uploaded_images[filename]
                    question_data = build_image_based_question(
                        test_num, q_num, image_data,
                        passage_id if q_num <= 10 else None
                    )

            if question_data:
                q_id = client.create_question(question_data)
                if q_id:
                    tracker.mark_question_created(test_num, q_num, q_id)
                    question_ids.append({"question_id": q_id, "order_number": q_num})

                    if is_text_based:
                        stats["text_based_questions"] += 1
                        q_mode = "TEXT"
                    else:
                        stats["image_based_questions"] += 1
                        q_mode = "IMAGE"

                    answer = get_answer(test_num, q_num)
                    logger.info(f"  Q{q_num}: Created ({q_mode}, answer: {answer})")
                else:
                    logger.error(f"  Q{q_num}: Failed to create")
            else:
                logger.warning(f"  Q{q_num}: No data available")

            time.sleep(0.15)

        # Create question set
        if tracker.is_question_set_created(test_num):
            qs_id = tracker.get_question_set_id(test_num)
            logger.info(f"  Question set already exists")
        else:
            qs_name = f"VR CEM Testbook 1 - Test {test_num}"
            qs_id = client.create_question_set(
                name=qs_name,
                subject="Verbal Reasoning",
                grade_level="Year 5-7",
                question_items=question_ids
            )

            if qs_id:
                tracker.mark_question_set_created(test_num, qs_id)
                logger.info(f"  Question set created ({len(question_ids)} questions)")
            else:
                logger.error(f"  Failed to create question set")
                continue

        # Create test
        if tracker.is_test_created(test_num):
            test_id = tracker.get_test_id(test_num)
            logger.info(f"  Test already exists")
        else:
            test_data = build_test_data(test_num)
            test_id = client.create_test(test_data)

            if test_id:
                tracker.mark_test_created(test_num, test_id)
                stats["tests_created"] += 1
                logger.info(f"  Test created")

                if client.assign_question_sets_to_test(test_id, [qs_id]):
                    logger.info(f"  Question set assigned to test")
                else:
                    logger.error(f"  Failed to assign question set")
            else:
                logger.error(f"  Failed to create test")

    # Summary
    logger.info("\n" + "=" * 60)
    logger.info("DIGITIZATION COMPLETE")
    logger.info("=" * 60)
    logger.info(f"Images uploaded: {len(tracker.progress['uploaded_images'])}")
    logger.info(f"Passages created: {stats['passages_created']}")
    logger.info(f"Questions created: {len(tracker.progress['created_questions'])}")
    logger.info(f"  - Text-based: {stats['text_based_questions']}")
    logger.info(f"  - Image-based: {stats['image_based_questions']}")
    logger.info(f"Question sets created: {len(tracker.progress['created_question_sets'])}")
    logger.info(f"Tests created: {stats['tests_created']}")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
