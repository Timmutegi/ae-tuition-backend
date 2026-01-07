#!/usr/bin/env python3
"""
AI-Powered Digitization Script for 11+ Verbal Reasoning Testbook

This script uses OpenAI GPT-4 Vision to:
1. Extract reading passages from test page images
2. Extract question text and options from images
3. Create properly formatted text-based questions in the AE-Tuition platform

Usage:
    python scripts/create_verbal_reasoning_test_ai.py [--reset] [--test N] [--extract-only]

Requirements:
    - requests library
    - openai library
    - Backend running at http://localhost:9000
    - Valid admin credentials
    - OPENAI_API_KEY in environment
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
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add the scripts directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from answer_keys import ANSWER_KEYS, get_answer, TEST_METADATA
from ai_extractor import (
    extract_passage_page, extract_mc_questions_page,
    extract_cloze_questions_page, extract_synonym_questions_page,
    ExtractedQuestion, ExtractedPassage, PageExtractionResult
)

# Configuration
BASE_URL = os.getenv("API_BASE_URL", "http://localhost:9000/api/v1")
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "support@ae-tuition.com")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "Admin123!!")
IMAGES_DIR = os.getenv(
    "IMAGES_DIR",
    "/Users/timothymbaka/tesh/kaziflex/ae-tuition/11+_Verbal_Reasoning_Year_5-7_CEM_Style_Testbook_1"
)

# Progress and extraction cache files
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROGRESS_FILE = os.path.join(SCRIPT_DIR, "progress_ai.json")
EXTRACTION_CACHE_FILE = os.path.join(SCRIPT_DIR, "extraction_cache.json")

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(os.path.join(SCRIPT_DIR, "digitization_ai.log"))
    ]
)
logger = logging.getLogger(__name__)


@dataclass
class ImageUploadResult:
    """Result from uploading an image to S3"""
    s3_key: str
    public_url: str
    file_name: str


class ExtractionCache:
    """Cache for AI extraction results to avoid re-processing"""

    def __init__(self, cache_file: str = EXTRACTION_CACHE_FILE):
        self.cache_file = cache_file
        self.cache = self._load()

    def _load(self) -> Dict:
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file) as f:
                    return json.load(f)
            except:
                pass
        return {"tests": {}, "pages": {}}

    def save(self):
        with open(self.cache_file, 'w') as f:
            json.dump(self.cache, f, indent=2, default=str)

    def get_test_extraction(self, test_num: int) -> Optional[Dict]:
        return self.cache["tests"].get(str(test_num))

    def set_test_extraction(self, test_num: int, data: Dict):
        self.cache["tests"][str(test_num)] = data
        self.save()

    def get_page_extraction(self, page_num: int) -> Optional[Dict]:
        return self.cache["pages"].get(str(page_num))

    def set_page_extraction(self, page_num: int, data: Dict):
        self.cache["pages"][str(page_num)] = data
        self.save()

    def reset(self):
        self.cache = {"tests": {}, "pages": {}}
        self.save()


class ProgressTracker:
    """Track progress for checkpoint/resume support"""

    def __init__(self, checkpoint_file: str = PROGRESS_FILE):
        self.checkpoint_file = checkpoint_file
        self.progress = self._load()

    def _load(self) -> Dict:
        if os.path.exists(self.checkpoint_file):
            try:
                with open(self.checkpoint_file) as f:
                    return json.load(f)
            except:
                pass
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
        with open(self.checkpoint_file, 'w') as f:
            json.dump(self.progress, f, indent=2)

    def reset(self):
        self.progress = self._empty_progress()
        self.save()

    # Image tracking
    def is_image_uploaded(self, filename: str) -> bool:
        return filename in self.progress["uploaded_images"]

    def get_image_upload_result(self, filename: str) -> Optional[Dict]:
        return self.progress["uploaded_images"].get(filename)

    def mark_image_uploaded(self, filename: str, result: Dict):
        self.progress["uploaded_images"][filename] = result
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

    # Question tracking
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

    # Question set tracking
    def is_question_set_created(self, test_num: int) -> bool:
        return str(test_num) in self.progress["created_question_sets"]

    def get_question_set_id(self, test_num: int) -> Optional[str]:
        return self.progress["created_question_sets"].get(str(test_num))

    def mark_question_set_created(self, test_num: int, question_set_id: str):
        self.progress["created_question_sets"][str(test_num)] = question_set_id
        self.save()

    # Test tracking
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
                logger.error(f"Authentication failed: {response.status_code}")
                return False
        except requests.RequestException as e:
            logger.error(f"Authentication error: {e}")
            return False

    def upload_image(self, file_path: str, max_retries: int = 3) -> Optional[ImageUploadResult]:
        """Upload image to S3"""
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
            except requests.RequestException as e:
                logger.warning(f"Upload attempt {attempt + 1} error: {e}")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
        return None

    def upload_passage_image(self, file_path: str, max_retries: int = 3) -> Optional[ImageUploadResult]:
        """Upload passage image to S3"""
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
            except requests.RequestException as e:
                logger.warning(f"Passage upload attempt {attempt + 1} error: {e}")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
        return None

    def create_passage(self, passage_data: Dict, max_retries: int = 3) -> Optional[str]:
        """Create reading passage"""
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
                    logger.warning(f"Passage creation failed: {response.status_code} - {response.text}")
            except requests.RequestException as e:
                logger.warning(f"Passage creation error: {e}")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
        return None

    def create_question(self, question_data: Dict, max_retries: int = 3) -> Optional[str]:
        """Create question"""
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
                    logger.warning(f"Question creation failed: {response.status_code} - {response.text}")
            except requests.RequestException as e:
                logger.warning(f"Question creation error: {e}")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
        return None

    def create_question_set(self, name: str, subject: str, grade_level: str,
                           question_items: List[Dict], max_retries: int = 3) -> Optional[str]:
        """Create question set"""
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
            except requests.RequestException as e:
                logger.warning(f"Question set creation error: {e}")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
        return None

    def create_test(self, test_data: Dict, max_retries: int = 3) -> Optional[str]:
        """Create test"""
        for attempt in range(max_retries):
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
            except requests.RequestException as e:
                logger.warning(f"Question set assignment error: {e}")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
        return False


def get_test_pages(test_num: int) -> List[int]:
    """Get page numbers for a specific test"""
    start_page = 2 + (test_num - 1) * 4
    return list(range(start_page, min(start_page + 4, 82)))


def get_image_path(page_num: int) -> str:
    """Get full image path for a page number"""
    filename = f"11+ Verbal Reasoning Year 5-7 CEM Style Testbook 1 21.07.21-{page_num:02d}.png"
    return os.path.join(IMAGES_DIR, filename)


def extract_test_with_ai(test_num: int, cache: ExtractionCache) -> Dict:
    """
    Use AI to extract all content from a test.
    Results are cached to avoid re-processing.
    """
    # Check cache first
    cached = cache.get_test_extraction(test_num)
    if cached:
        logger.info(f"  Using cached extraction for Test {test_num}")
        return cached

    pages = get_test_pages(test_num)
    logger.info(f"  Extracting Test {test_num} from pages {pages} using AI...")

    result = {
        "passage": None,
        "passage_text": None,
        "questions": {},
        "cloze_context": None,
        "errors": []
    }

    for i, page_num in enumerate(pages):
        image_path = get_image_path(page_num)

        if not os.path.exists(image_path):
            result["errors"].append(f"Image not found: {image_path}")
            continue

        logger.info(f"    Processing page {page_num} ({i+1}/{len(pages)})...")

        try:
            if i == 0:
                # First page: Passage + Q1
                extraction = extract_passage_page(image_path, test_num)
                if extraction:
                    if extraction.passage:
                        result["passage"] = {
                            "title": extraction.passage.title,
                            "content": extraction.passage.content,
                            "source": extraction.passage.source,
                            "glossary": extraction.passage.glossary
                        }
                        result["passage_text"] = extraction.passage.content

                    for q in extraction.questions:
                        result["questions"][q.question_number] = _question_to_dict(q)

            elif i == 1:
                # Second page: Q2-7 (multiple choice)
                extraction = extract_mc_questions_page(image_path, test_num, list(range(2, 8)))
                if extraction:
                    for q in extraction.questions:
                        result["questions"][q.question_number] = _question_to_dict(q)

            elif i == 2:
                # Third page: Q8-10 + start of Q11-20
                # Try MC first
                extraction = extract_mc_questions_page(image_path, test_num, list(range(8, 11)))
                if extraction:
                    for q in extraction.questions:
                        result["questions"][q.question_number] = _question_to_dict(q)

                # Then cloze
                extraction = extract_cloze_questions_page(image_path, test_num, list(range(11, 21)))
                if extraction:
                    for q in extraction.questions:
                        result["questions"][q.question_number] = _question_to_dict(q)
                        # Store context for cloze questions
                        if q.context_text and not result["cloze_context"]:
                            result["cloze_context"] = q.context_text

            elif i == 3:
                # Fourth page: Q16-20 + Q21-25
                # Cloze questions (if any remaining)
                extraction = extract_cloze_questions_page(image_path, test_num, list(range(11, 21)))
                if extraction:
                    for q in extraction.questions:
                        if q.question_number not in result["questions"]:
                            result["questions"][q.question_number] = _question_to_dict(q)
                        if q.context_text and not result["cloze_context"]:
                            result["cloze_context"] = q.context_text

                # Synonym questions
                extraction = extract_synonym_questions_page(image_path, test_num, list(range(21, 26)))
                if extraction:
                    for q in extraction.questions:
                        result["questions"][q.question_number] = _question_to_dict(q)

        except Exception as e:
            logger.error(f"    Error processing page {page_num}: {e}")
            result["errors"].append(f"Page {page_num}: {str(e)}")

        # Rate limiting between API calls
        time.sleep(1.5)

    # Cache the result
    cache.set_test_extraction(test_num, result)

    logger.info(f"    Extracted {len(result['questions'])} questions")
    return result


def _question_to_dict(q: ExtractedQuestion) -> Dict:
    """Convert ExtractedQuestion to dict for caching"""
    return {
        "question_number": q.question_number,
        "question_text": q.question_text,
        "question_type": q.question_type,
        "options": q.options,
        "instruction_text": q.instruction_text,
        "context_text": q.context_text
    }


def build_question_data(test_num: int, q_num: int, extracted: Dict,
                        passage_id: Optional[str] = None,
                        image_data: Optional[Dict] = None) -> Dict:
    """
    Build question data for API from extracted content.
    Falls back to image-based if extraction failed.
    """
    answer = get_answer(test_num, q_num)
    q_data = extracted.get("questions", {}).get(q_num)

    # If we have extracted content, use it
    if q_data and q_data.get("question_text"):
        return _build_text_question(test_num, q_num, q_data, answer, passage_id, extracted)

    # Fall back to image-based
    if image_data:
        return _build_image_question(test_num, q_num, answer, image_data, passage_id)

    return None


def _build_text_question(test_num: int, q_num: int, q_data: Dict, answer: str,
                         passage_id: Optional[str], extracted: Dict) -> Dict:
    """Build text-based question from extracted data"""
    q_type = q_data.get("question_type", "multiple_choice")
    q_text = q_data.get("question_text", "")
    options = q_data.get("options", [])
    instruction = q_data.get("instruction_text", "")
    context = q_data.get("context_text", "")

    # Handle Q1-10: Multiple choice (reading comprehension)
    if 1 <= q_num <= 10:
        answer_options = []
        for i, opt in enumerate(options):
            letter = opt.get("letter", chr(ord('a') + i))
            text = opt.get("text", "")
            answer_options.append({
                "option_text": text,
                "is_correct": answer.lower() == letter.lower(),
                "order_number": i + 1
            })

        return {
            "question_text": q_text,
            "question_type": "multiple_choice",
            "question_format": "passage_based" if passage_id else "standard",
            "passage_id": passage_id,
            "subject": "Verbal Reasoning",
            "points": 1,
            "instruction_text": instruction or "Read the passage carefully and select the correct answer.",
            "correct_answer": answer.lower(),
            "case_sensitive": False,
            "answer_options": answer_options
        }

    # Handle Q11-20: Cloze/various formats
    elif 11 <= q_num <= 20:
        # Build context with the cloze passage if available
        cloze_context = extracted.get("cloze_context", "")

        # Build answer options from extracted options
        answer_options = []
        for i, opt in enumerate(options):
            text = opt.get("text", opt.get("letter", ""))
            answer_options.append({
                "option_text": text,
                "is_correct": answer.lower() == text.lower(),
                "order_number": i + 1
            })

        # If we have context, include it in instruction
        full_instruction = instruction
        if cloze_context:
            # Truncate if too long
            if len(cloze_context) > 500:
                cloze_context = cloze_context[:500] + "..."
            full_instruction = f"{instruction}\n\nPassage: {cloze_context}"

        return {
            "question_text": q_text or f"Question {q_num}",
            "question_type": "cloze_select",
            "question_format": "standard",
            "subject": "Verbal Reasoning",
            "points": 1,
            "instruction_text": full_instruction or "Select the correct word to complete the blank.",
            "correct_answer": answer.lower(),
            "case_sensitive": False,
            "answer_options": answer_options
        }

    # Handle Q21-25: Synonym/Antonym
    else:
        # For synonym questions, the question text is often the word itself
        given_word = q_text

        # Build answer options if any
        answer_options = []
        for i, opt in enumerate(options):
            text = opt.get("text", "")
            if text:
                answer_options.append({
                    "option_text": text,
                    "is_correct": answer.lower() == text.lower(),
                    "order_number": i + 1
                })

        return {
            "question_text": f"Find a word that means the same as: {given_word}" if given_word else f"Question {q_num}",
            "question_type": "synonym_completion",
            "question_format": "standard",
            "subject": "Verbal Reasoning",
            "points": 1,
            "instruction_text": instruction or "Complete the word on the right so that it means the same as the word on the left.",
            "correct_answer": answer.lower(),
            "case_sensitive": False,
            "answer_options": answer_options
        }


def _build_image_question(test_num: int, q_num: int, answer: str,
                          image_data: Dict, passage_id: Optional[str] = None) -> Dict:
    """Build image-based question (fallback)"""
    metadata = TEST_METADATA.get(test_num, {"passage": "Unknown", "author": "Unknown"})

    if 1 <= q_num <= 10:
        q_type = "multiple_choice"
        instruction = "Read the passage in the image and select the correct answer (a, b, c, or d)."
    elif 11 <= q_num <= 20:
        q_type = "cloze_select"
        instruction = "Look at the image and select the correct word to complete the blank."
    else:
        q_type = "synonym_completion"
        instruction = "Look at the image. Complete the word on the right so that it means the same as the word on the left."

    base_data = {
        "question_text": None,
        "question_type": q_type,
        "question_format": "passage_based" if passage_id and q_num <= 10 else "standard",
        "image_url": image_data["public_url"],
        "s3_key": image_data["s3_key"],
        "subject": "Verbal Reasoning",
        "points": 1,
        "instruction_text": instruction,
        "explanation": f"Test {test_num}, Question {q_num} - {metadata['passage']}",
        "correct_answer": answer.lower(),
        "case_sensitive": False,
        "answer_options": []
    }

    if passage_id and q_num <= 10:
        base_data["passage_id"] = passage_id

    if q_type == "multiple_choice":
        base_data["answer_options"] = [
            {"option_text": "a", "is_correct": answer.lower() == "a", "order_number": 1},
            {"option_text": "b", "is_correct": answer.lower() == "b", "order_number": 2},
            {"option_text": "c", "is_correct": answer.lower() == "c", "order_number": 3},
            {"option_text": "d", "is_correct": answer.lower() == "d", "order_number": 4}
        ]

    return base_data


def build_passage_data(test_num: int, extracted: Dict, image_data: Optional[Dict] = None) -> Dict:
    """Build passage data from extracted content"""
    metadata = TEST_METADATA.get(test_num, {"passage": "Unknown", "author": "Unknown"})
    passage_info = extracted.get("passage", {})

    passage_data = {
        "title": passage_info.get("title") or f"Test {test_num}: {metadata['passage']}",
        "subject": "Verbal Reasoning",
        "author": metadata.get("author", "Unknown"),
        "genre": "Educational",
        "reading_level": "Year 5-7"
    }

    # Use extracted text if available
    if passage_info.get("content"):
        passage_data["content"] = passage_info["content"]
        if passage_info.get("source"):
            passage_data["source"] = passage_info["source"]
    elif image_data:
        passage_data["image_url"] = image_data["public_url"]
        passage_data["s3_key"] = image_data["s3_key"]

    return passage_data


def build_test_data(test_num: int) -> Dict:
    """Build test data"""
    metadata = TEST_METADATA.get(test_num, {"passage": "Unknown", "author": "Unknown"})

    return {
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

Questions 11-20: Verbal Reasoning
- Follow the instructions for each question type
- Select or type the correct answer

Questions 21-25: Synonyms
- Find words that mean the same as the given word
- Type the complete word as your answer""",
        "question_order": "sequential"
    }


def main():
    parser = argparse.ArgumentParser(description='AI-Powered Verbal Reasoning Digitization')
    parser.add_argument('--reset', action='store_true', help='Reset all progress and cache')
    parser.add_argument('--reset-extraction', action='store_true', help='Reset only extraction cache')
    parser.add_argument('--test', type=int, help='Process only a specific test number')
    parser.add_argument('--extract-only', action='store_true', help='Only extract, do not create in database')
    args = parser.parse_args()

    # Check for OpenAI API key
    if not os.getenv("OPENAI_API_KEY"):
        logger.error("OPENAI_API_KEY environment variable is not set!")
        logger.error("Please add your OpenAI API key to the .env file")
        sys.exit(1)

    logger.info("=" * 60)
    logger.info("AI-Powered Verbal Reasoning Digitization")
    logger.info("=" * 60)

    # Initialize
    client = AETuitionClient(BASE_URL)
    tracker = ProgressTracker()
    cache = ExtractionCache()

    if args.reset:
        tracker.reset()
        cache.reset()
        logger.info("Progress and cache reset")

    if args.reset_extraction:
        cache.reset()
        logger.info("Extraction cache reset")

    # Authenticate
    if not args.extract_only:
        logger.info("Authenticating...")
        if not client.login(ADMIN_EMAIL, ADMIN_PASSWORD):
            logger.error("Authentication failed!")
            sys.exit(1)

    # Get image files
    image_files = sorted([
        f for f in os.listdir(IMAGES_DIR)
        if f.endswith('.png') and '21.07.21' in f
    ])
    logger.info(f"Found {len(image_files)} image files")

    # Upload images (if not extract-only)
    uploaded_images = {}
    if not args.extract_only:
        logger.info("\nUploading images...")
        for i, filename in enumerate(image_files):
            if tracker.is_image_uploaded(filename):
                uploaded_images[filename] = tracker.get_image_upload_result(filename)
                continue

            file_path = os.path.join(IMAGES_DIR, filename)
            logger.info(f"  [{i+1}/{len(image_files)}] Uploading: {filename}")

            result = client.upload_image(file_path)
            if result:
                uploaded_images[filename] = {
                    "s3_key": result.s3_key,
                    "public_url": result.public_url
                }
                tracker.mark_image_uploaded(filename, uploaded_images[filename])
            time.sleep(0.3)
    else:
        # Load existing uploaded images
        for filename in image_files:
            if tracker.is_image_uploaded(filename):
                uploaded_images[filename] = tracker.get_image_upload_result(filename)

    # Determine which tests to process
    test_range = [args.test] if args.test else range(1, 21)

    stats = {
        "text_questions": 0,
        "image_questions": 0,
        "passages": 0,
        "tests": 0
    }

    for test_num in test_range:
        logger.info(f"\n{'='*50}")
        logger.info(f"Processing Test {test_num}")
        logger.info(f"{'='*50}")

        # Extract content using AI
        extracted = extract_test_with_ai(test_num, cache)

        if args.extract_only:
            # Just log extraction results
            logger.info(f"  Passage: {'Yes' if extracted.get('passage') else 'No'}")
            logger.info(f"  Questions extracted: {len(extracted.get('questions', {}))}")
            for q_num in sorted(extracted.get('questions', {}).keys()):
                q = extracted['questions'][q_num]
                q_text = q.get('question_text', '')[:50]
                logger.info(f"    Q{q_num}: {q_text}...")
            continue

        # Get page info
        pages = get_test_pages(test_num)
        passage_page = pages[0]
        passage_filename = f"11+ Verbal Reasoning Year 5-7 CEM Style Testbook 1 21.07.21-{passage_page:02d}.png"

        # Create passage
        passage_id = None
        if tracker.is_passage_created(test_num):
            passage_id = tracker.get_passage_id(test_num)
            logger.info(f"  Passage already exists")
        else:
            # Upload passage image if needed
            passage_image_data = None
            if not tracker.is_passage_image_uploaded(test_num):
                passage_path = os.path.join(IMAGES_DIR, passage_filename)
                if os.path.exists(passage_path):
                    result = client.upload_passage_image(passage_path)
                    if result:
                        passage_image_data = {
                            "s3_key": result.s3_key,
                            "public_url": result.public_url
                        }
                        tracker.mark_passage_image_uploaded(test_num, passage_image_data)
            else:
                passage_image_data = tracker.get_passage_image_result(test_num)

            # Build and create passage
            passage_data = build_passage_data(test_num, extracted, passage_image_data)
            passage_id = client.create_passage(passage_data)
            if passage_id:
                tracker.mark_passage_created(test_num, passage_id)
                stats["passages"] += 1
                has_text = bool(extracted.get("passage", {}).get("content"))
                logger.info(f"  Passage created ({'TEXT' if has_text else 'IMAGE'})")

        # Create questions
        question_ids = []
        for q_num in range(1, 26):
            if tracker.is_question_created(test_num, q_num):
                q_id = tracker.get_question_id(test_num, q_num)
                question_ids.append({"question_id": q_id, "order_number": q_num})
                continue

            # Get image data for this question (as fallback)
            page_num = pages[min((q_num - 1) // 7, len(pages) - 1)]
            filename = f"11+ Verbal Reasoning Year 5-7 CEM Style Testbook 1 21.07.21-{page_num:02d}.png"
            image_data = uploaded_images.get(filename)

            # Build question data
            question_data = build_question_data(
                test_num, q_num, extracted,
                passage_id if q_num <= 10 else None,
                image_data
            )

            if question_data:
                q_id = client.create_question(question_data)
                if q_id:
                    tracker.mark_question_created(test_num, q_num, q_id)
                    question_ids.append({"question_id": q_id, "order_number": q_num})

                    is_text = question_data.get("question_text") is not None
                    if is_text:
                        stats["text_questions"] += 1
                    else:
                        stats["image_questions"] += 1

                    answer = get_answer(test_num, q_num)
                    logger.info(f"    Q{q_num}: {'TEXT' if is_text else 'IMAGE'}, answer: {answer}")

            time.sleep(0.15)

        # Create question set
        if tracker.is_question_set_created(test_num):
            qs_id = tracker.get_question_set_id(test_num)
            logger.info(f"  Question set exists")
        else:
            qs_id = client.create_question_set(
                name=f"VR CEM Test {test_num}",
                subject="Verbal Reasoning",
                grade_level="Year 5-7",
                question_items=question_ids
            )
            if qs_id:
                tracker.mark_question_set_created(test_num, qs_id)
                logger.info(f"  Question set created ({len(question_ids)} questions)")

        # Create test
        if tracker.is_test_created(test_num):
            logger.info(f"  Test exists")
        else:
            test_data = build_test_data(test_num)
            test_id = client.create_test(test_data)
            if test_id:
                tracker.mark_test_created(test_num, test_id)
                stats["tests"] += 1
                if client.assign_question_sets_to_test(test_id, [qs_id]):
                    logger.info(f"  Test created and linked")

    # Summary
    if not args.extract_only:
        logger.info("\n" + "=" * 60)
        logger.info("DIGITIZATION COMPLETE")
        logger.info("=" * 60)
        logger.info(f"Passages created: {stats['passages']}")
        logger.info(f"Questions created: {stats['text_questions'] + stats['image_questions']}")
        logger.info(f"  - Text-based: {stats['text_questions']}")
        logger.info(f"  - Image-based: {stats['image_questions']}")
        logger.info(f"Tests created: {stats['tests']}")
        logger.info("=" * 60)


if __name__ == "__main__":
    main()
