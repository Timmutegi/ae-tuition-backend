#!/usr/bin/env python3
"""
AI-Powered Digitization Script V2 for 11+ Verbal Reasoning Testbook

Key improvements over V1:
1. Uses type-aware extraction from ai_extractor_v2.py
2. Creates separate cloze passages for Q11-20 (not truncated)
3. Handles different Q11-20 question types appropriately
4. Sends multiple pages together to GPT for better context

Usage:
    python scripts/create_verbal_reasoning_test_ai_v2.py [--reset] [--test N] [--extract-only]

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
from question_types import get_q11_20_type, get_q21_25_type, Q11_20_TEXT_CAPABLE
from ai_extractor_v2 import (
    extract_full_test_v2, TestExtractionResult, ExtractedQuestion, ExtractedPassage
)
from vr_distractor_generator import VRDistractorGenerator

# Initialize VR distractor generator (lazy loading)
_vr_distractor_generator = None

def get_vr_distractor_generator():
    """Get or create VR distractor generator instance."""
    global _vr_distractor_generator
    if _vr_distractor_generator is None:
        _vr_distractor_generator = VRDistractorGenerator()
    return _vr_distractor_generator

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
PROGRESS_FILE = os.path.join(SCRIPT_DIR, "progress_ai_v2.json")
EXTRACTION_CACHE_FILE = os.path.join(SCRIPT_DIR, "extraction_cache_v2.json")

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(os.path.join(SCRIPT_DIR, "digitization_ai_v2.log"))
    ]
)
logger = logging.getLogger(__name__)


@dataclass
class ImageUploadResult:
    """Result from uploading an image to S3"""
    s3_key: str
    public_url: str
    file_name: str


class ExtractionCacheV2:
    """Cache for V2 AI extraction results"""

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
        return {"tests": {}}

    def save(self):
        with open(self.cache_file, 'w') as f:
            json.dump(self.cache, f, indent=2, default=str)

    def get_test_extraction(self, test_num: int) -> Optional[Dict]:
        return self.cache["tests"].get(str(test_num))

    def set_test_extraction(self, test_num: int, result: TestExtractionResult):
        """Serialize TestExtractionResult to dict for caching"""
        data = {
            "test_num": result.test_num,
            "q11_20_type": result.q11_20_type,
            "q21_25_type": result.q21_25_type,
            "errors": result.errors,
            "reading_passage": None,
            "cloze_passage": None,
            "questions": {}
        }

        if result.reading_passage:
            data["reading_passage"] = {
                "title": result.reading_passage.title,
                "content": result.reading_passage.content,
                "passage_type": result.reading_passage.passage_type,
                "source": result.reading_passage.source,
                "blank_options": result.reading_passage.blank_options
            }

        if result.cloze_passage:
            data["cloze_passage"] = {
                "title": result.cloze_passage.title,
                "content": result.cloze_passage.content,
                "passage_type": result.cloze_passage.passage_type,
                "blank_options": result.cloze_passage.blank_options
            }

        for q_num, q in result.questions.items():
            data["questions"][str(q_num)] = {
                "question_number": q.question_number,
                "question_text": q.question_text,
                "question_type": q.question_type,
                "options": q.options,
                "instruction_text": q.instruction_text,
                "context_text": q.context_text,
                "given_word": q.given_word
            }

        self.cache["tests"][str(test_num)] = data
        self.save()

    def reset(self):
        self.cache = {"tests": {}}
        self.save()


class ProgressTrackerV2:
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
            "created_cloze_passages": {},  # NEW: Track cloze passages separately
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

    # Reading Passage tracking
    def is_passage_created(self, test_num: int) -> bool:
        return str(test_num) in self.progress.get("created_passages", {})

    def get_passage_id(self, test_num: int) -> Optional[str]:
        return self.progress.get("created_passages", {}).get(str(test_num))

    def mark_passage_created(self, test_num: int, passage_id: str):
        if "created_passages" not in self.progress:
            self.progress["created_passages"] = {}
        self.progress["created_passages"][str(test_num)] = passage_id
        self.save()

    # Cloze Passage tracking (NEW)
    def is_cloze_passage_created(self, test_num: int) -> bool:
        return str(test_num) in self.progress.get("created_cloze_passages", {})

    def get_cloze_passage_id(self, test_num: int) -> Optional[str]:
        return self.progress.get("created_cloze_passages", {}).get(str(test_num))

    def mark_cloze_passage_created(self, test_num: int, passage_id: str):
        if "created_cloze_passages" not in self.progress:
            self.progress["created_cloze_passages"] = {}
        self.progress["created_cloze_passages"][str(test_num)] = passage_id
        self.save()

    # Image tracking
    def is_image_uploaded(self, filename: str) -> bool:
        return filename in self.progress.get("uploaded_images", {})

    def get_image_upload_result(self, filename: str) -> Optional[Dict]:
        return self.progress.get("uploaded_images", {}).get(filename)

    def mark_image_uploaded(self, filename: str, result: Dict):
        if "uploaded_images" not in self.progress:
            self.progress["uploaded_images"] = {}
        self.progress["uploaded_images"][filename] = result
        self.save()

    def is_passage_image_uploaded(self, test_num: int) -> bool:
        return str(test_num) in self.progress.get("uploaded_passage_images", {})

    def get_passage_image_result(self, test_num: int) -> Optional[Dict]:
        return self.progress.get("uploaded_passage_images", {}).get(str(test_num))

    def mark_passage_image_uploaded(self, test_num: int, result: Dict):
        if "uploaded_passage_images" not in self.progress:
            self.progress["uploaded_passage_images"] = {}
        self.progress["uploaded_passage_images"][str(test_num)] = result
        self.save()

    # Question tracking
    def is_question_created(self, test_num: int, q_num: int) -> bool:
        key = f"{test_num}_{q_num}"
        return key in self.progress.get("created_questions", {})

    def get_question_id(self, test_num: int, q_num: int) -> Optional[str]:
        key = f"{test_num}_{q_num}"
        return self.progress.get("created_questions", {}).get(key)

    def mark_question_created(self, test_num: int, q_num: int, question_id: str):
        if "created_questions" not in self.progress:
            self.progress["created_questions"] = {}
        key = f"{test_num}_{q_num}"
        self.progress["created_questions"][key] = question_id
        self.save()

    # Question set tracking
    def is_question_set_created(self, test_num: int) -> bool:
        return str(test_num) in self.progress.get("created_question_sets", {})

    def get_question_set_id(self, test_num: int) -> Optional[str]:
        return self.progress.get("created_question_sets", {}).get(str(test_num))

    def mark_question_set_created(self, test_num: int, question_set_id: str):
        if "created_question_sets" not in self.progress:
            self.progress["created_question_sets"] = {}
        self.progress["created_question_sets"][str(test_num)] = question_set_id
        self.save()

    # Test tracking
    def is_test_created(self, test_num: int) -> bool:
        return str(test_num) in self.progress.get("created_tests", {})

    def get_test_id(self, test_num: int) -> Optional[str]:
        return self.progress.get("created_tests", {}).get(str(test_num))

    def mark_test_created(self, test_num: int, test_id: str):
        if "created_tests" not in self.progress:
            self.progress["created_tests"] = {}
        self.progress["created_tests"][str(test_num)] = test_id
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


def build_reading_passage_data(test_num: int, extracted: Dict) -> Dict:
    """Build reading passage data from extracted content"""
    metadata = TEST_METADATA.get(test_num, {"passage": "Unknown", "author": "Unknown"})
    passage_info = extracted.get("reading_passage", {}) or {}

    passage_data = {
        "title": passage_info.get("title") or f"Test {test_num}: {metadata['passage']}",
        "subject": "Verbal Reasoning",
        "author": metadata.get("author", "Unknown"),
        "genre": "Educational",
        "reading_level": "Year 5-7"
    }

    # Use extracted text content
    if passage_info.get("content"):
        passage_data["content"] = passage_info["content"]
        if passage_info.get("source"):
            passage_data["source"] = passage_info["source"]

    return passage_data


def build_cloze_passage_data(test_num: int, extracted: Dict) -> Optional[Dict]:
    """Build cloze passage data for Q11-20 from extracted content"""
    cloze_info = extracted.get("cloze_passage", {})
    if not cloze_info or not cloze_info.get("content"):
        return None

    q11_20_type = extracted.get("q11_20_type", "UNKNOWN")

    passage_data = {
        "title": cloze_info.get("title") or f"Test {test_num} - {q11_20_type}",
        "subject": "Verbal Reasoning",
        "genre": "Cloze Passage",
        "reading_level": "Year 5-7",
        "content": cloze_info["content"]  # FULL passage, not truncated
    }

    return passage_data


def build_question_data_v2(
    test_num: int,
    q_num: int,
    extracted: Dict,
    reading_passage_id: Optional[str] = None,
    cloze_passage_id: Optional[str] = None
) -> Optional[Dict]:
    """
    Build question data for API from V2 extracted content.
    Uses the appropriate passage ID based on question number.
    """
    answer = get_answer(test_num, q_num)
    q_data = extracted.get("questions", {}).get(str(q_num))

    if not q_data:
        logger.warning(f"  No extracted data for Q{q_num}")
        return None

    q_type = q_data.get("question_type", "multiple_choice")
    q_text = q_data.get("question_text", "")
    options = q_data.get("options", [])
    instruction = q_data.get("instruction_text", "")
    context = q_data.get("context_text", "")
    given_word = q_data.get("given_word", "")

    # Q1-10: Reading Comprehension (Multiple Choice)
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
            "question_format": "passage_based" if reading_passage_id else "standard",
            "passage_id": reading_passage_id,
            "subject": "Verbal Reasoning",
            "points": 1,
            "instruction_text": instruction or "Read the passage carefully and select the correct answer.",
            "correct_answer": answer.lower(),
            "case_sensitive": False,
            "answer_options": answer_options
        }

    # Q11-20: Various formats based on q11_20_type
    elif 11 <= q_num <= 20:
        q11_20_type = extracted.get("q11_20_type", "UNKNOWN")

        # Build answer options from extracted options
        answer_options = []
        for i, opt in enumerate(options):
            text = opt.get("text", "")
            if text:
                answer_options.append({
                    "option_text": text,
                    "is_correct": answer.lower() == text.lower(),
                    "order_number": i + 1
                })

        # Determine question type mapping (must match QuestionType enum in backend)
        if q11_20_type == "CLOZE_PASSAGE":
            db_question_type = "cloze_select"
            default_instruction = "Select the correct word to complete the passage."
        elif q11_20_type == "LETTER_COMPLETION_CLOZE":
            db_question_type = "fill_missing_letters"
            default_instruction = "Fill in the missing letters to complete the word."
        elif q11_20_type == "ODD_ONE_OUT":
            db_question_type = "odd_one_out"
            default_instruction = "Select the word that does NOT belong with the others."
        elif q11_20_type == "SENTENCE_REARRANGE":
            db_question_type = "sentence_rearrangement"
            default_instruction = "Rearrange the words to form a sentence. Select the word that doesn't fit."
        elif q11_20_type in ["ANTONYM_LETTER", "ANTONYM_SELECTION"]:
            db_question_type = "antonym_completion"
            default_instruction = "Complete the word on the right with the OPPOSITE meaning."
        elif q11_20_type in ["SYNONYM_LETTER", "SYNONYM_SELECTION"]:
            db_question_type = "synonym_completion"
            default_instruction = "Complete the word on the right with the SAME meaning."
        else:
            db_question_type = "reading_comprehension"
            default_instruction = instruction or "Answer the question."

        question_data = {
            "question_text": q_text or f"Question {q_num}",
            "question_type": db_question_type,
            "question_format": "passage_based" if cloze_passage_id else "standard",
            "subject": "Verbal Reasoning",
            "points": 1,
            "instruction_text": instruction or default_instruction,
            "correct_answer": answer.lower(),
            "case_sensitive": False,
            "answer_options": answer_options
        }

        # Link to cloze passage if available
        if cloze_passage_id:
            question_data["passage_id"] = cloze_passage_id

        return question_data

    # Q21-25: Synonym/Antonym - Now converted to MCQ with AI-generated distractors
    else:
        q21_25_type = extracted.get("q21_25_type", "SYNONYM_LETTER")

        # Determine if it's synonym or antonym
        is_antonym = "ANTONYM" in q21_25_type
        question_type_str = "antonym" if is_antonym else "synonym"

        if is_antonym:
            default_instruction = "Select the word with the OPPOSITE meaning."
            question_prefix = "opposite"
        else:
            default_instruction = "Select the word with the SAME meaning."
            question_prefix = "same"

        # Extract letter template from options if available
        letter_template = None
        if options:
            # Try to extract letter template from the first option or q_data
            letter_template = q_data.get("letter_template", "")
            if not letter_template and options:
                # Build template from options (letters shown in boxes)
                template_parts = []
                for opt in options:
                    letter = opt.get("letter", "_")
                    template_parts.append(letter if letter else "_")
                letter_template = " ".join(template_parts)

        # Generate MCQ options using AI distractor generator
        try:
            generator = get_vr_distractor_generator()
            distractors = generator.generate_distractors(
                given_word=given_word or q_text,
                correct_answer=answer,
                question_type=question_type_str,
                test_num=test_num,
                question_num=q_num
            )
            answer_options, _ = generator.get_shuffled_options(answer.lower(), distractors)
        except Exception as e:
            logger.warning(f"Error generating distractors for Q{q_num}: {e}")
            # Fallback to simple options if distractor generation fails
            answer_options = [
                {"option_text": answer.lower(), "is_correct": True, "order_number": 1},
                {"option_text": "option1", "is_correct": False, "order_number": 2},
                {"option_text": "option2", "is_correct": False, "order_number": 3},
                {"option_text": "option3", "is_correct": False, "order_number": 4}
            ]

        # Build question data with MCQ format
        question_data = {
            "question_text": f"Find a word meaning the {question_prefix} as: {given_word}" if given_word else q_text,
            "question_type": "multiple_choice",  # Changed to MCQ for easier student interaction
            "question_format": "standard",
            "subject": "Verbal Reasoning",
            "points": 1,
            "instruction_text": instruction or default_instruction,
            "correct_answer": answer.lower(),
            "case_sensitive": False,
            "given_word": given_word,  # Store the given word for display
            "letter_template": {"template": letter_template, "answer": answer} if letter_template else None,
            "answer_options": answer_options
        }

        return question_data


def build_test_data(test_num: int) -> Dict:
    """Build test data"""
    metadata = TEST_METADATA.get(test_num, {"passage": "Unknown", "author": "Unknown"})
    q11_20_type = get_q11_20_type(test_num)

    return {
        "title": f"11+ Verbal Reasoning CEM Style - Test {test_num}",
        "description": f"Test {test_num} from 11+ Verbal Reasoning Year 5-7 CEM Style Testbook 1. "
                      f"Based on passage: {metadata['passage']}. "
                      f"Q11-20 type: {q11_20_type}. Contains 25 questions.",
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
- Follow the instructions for each question type
- Read the passage/context carefully

Questions 21-25: Synonyms/Antonyms
- Find words that mean the same or opposite
- Type the complete word as your answer""",
        "question_order": "sequential"
    }


def extract_test_with_ai_v2(test_num: int, cache: ExtractionCacheV2) -> Dict:
    """
    Use AI V2 to extract all content from a test.
    Results are cached to avoid re-processing.
    """
    # Check cache first
    cached = cache.get_test_extraction(test_num)
    if cached:
        logger.info(f"  Using cached extraction for Test {test_num}")
        return cached

    logger.info(f"  Extracting Test {test_num} using AI V2...")

    # Use the new V2 extractor
    result = extract_full_test_v2(IMAGES_DIR, test_num)

    # Cache the result
    cache.set_test_extraction(test_num, result)

    # Convert to dict for return
    cached = cache.get_test_extraction(test_num)
    return cached or {}


def main():
    parser = argparse.ArgumentParser(description='AI-Powered Verbal Reasoning Digitization V2')
    parser.add_argument('--reset', action='store_true', help='Reset all progress and cache')
    parser.add_argument('--reset-extraction', action='store_true', help='Reset only extraction cache')
    parser.add_argument('--test', type=int, help='Process only a specific test number')
    parser.add_argument('--extract-only', action='store_true', help='Only extract, do not create in database')
    parser.add_argument('--questions-only', action='store_true', help='Create questions and question sets only, skip test creation')
    args = parser.parse_args()

    # Check for OpenAI API key
    if not os.getenv("OPENAI_API_KEY"):
        logger.error("OPENAI_API_KEY environment variable is not set!")
        logger.error("Please add your OpenAI API key to the .env file")
        sys.exit(1)

    logger.info("=" * 60)
    logger.info("AI-Powered Verbal Reasoning Digitization V2")
    logger.info("=" * 60)

    # Initialize
    client = AETuitionClient(BASE_URL)
    tracker = ProgressTrackerV2()
    cache = ExtractionCacheV2()

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

    # Determine which tests to process
    test_range = [args.test] if args.test else range(1, 21)

    stats = {
        "text_questions": 0,
        "reading_passages": 0,
        "cloze_passages": 0,
        "tests": 0
    }

    for test_num in test_range:
        logger.info(f"\n{'='*50}")
        logger.info(f"Processing Test {test_num}")
        q11_20_type = get_q11_20_type(test_num)
        q21_25_type = get_q21_25_type(test_num)
        logger.info(f"  Q11-20 Type: {q11_20_type}")
        logger.info(f"  Q21-25 Type: {q21_25_type}")
        logger.info(f"{'='*50}")

        # Extract content using AI V2
        extracted = extract_test_with_ai_v2(test_num, cache)

        if args.extract_only:
            # Just log extraction results
            reading_passage = extracted.get("reading_passage", {})
            cloze_passage = extracted.get("cloze_passage", {})
            questions = extracted.get("questions", {})

            logger.info(f"  Reading Passage: {'Yes' if reading_passage and reading_passage.get('content') else 'No'}")
            if reading_passage and reading_passage.get('title'):
                logger.info(f"    Title: {reading_passage.get('title')}")

            logger.info(f"  Cloze Passage: {'Yes' if cloze_passage and cloze_passage.get('content') else 'No'}")
            if cloze_passage and cloze_passage.get('content'):
                content_preview = cloze_passage['content'][:100] + "..." if len(cloze_passage.get('content', '')) > 100 else cloze_passage.get('content', '')
                logger.info(f"    Preview: {content_preview}")

            logger.info(f"  Questions extracted: {len(questions)}")
            for q_num in sorted(questions.keys(), key=int):
                q = questions[q_num]
                q_text = q.get('question_text', '')[:50]
                logger.info(f"    Q{q_num} ({q.get('question_type', 'unknown')}): {q_text}...")
            continue

        # Create reading passage (Q1-10)
        reading_passage_id = None
        if tracker.is_passage_created(test_num):
            reading_passage_id = tracker.get_passage_id(test_num)
            logger.info(f"  Reading passage already exists")
        else:
            passage_data = build_reading_passage_data(test_num, extracted)
            if passage_data.get("content"):
                reading_passage_id = client.create_passage(passage_data)
                if reading_passage_id:
                    tracker.mark_passage_created(test_num, reading_passage_id)
                    stats["reading_passages"] += 1
                    logger.info(f"  Reading passage created: {passage_data.get('title', 'Unknown')}")
            else:
                logger.warning(f"  No reading passage content extracted")

        # Create cloze passage (Q11-20) if applicable
        cloze_passage_id = None
        if tracker.is_cloze_passage_created(test_num):
            cloze_passage_id = tracker.get_cloze_passage_id(test_num)
            logger.info(f"  Cloze passage already exists")
        else:
            cloze_data = build_cloze_passage_data(test_num, extracted)
            if cloze_data:
                cloze_passage_id = client.create_passage(cloze_data)
                if cloze_passage_id:
                    tracker.mark_cloze_passage_created(test_num, cloze_passage_id)
                    stats["cloze_passages"] += 1
                    logger.info(f"  Cloze passage created: {cloze_data.get('title', 'Unknown')}")
                    # Log passage content length
                    content_len = len(cloze_data.get('content', ''))
                    logger.info(f"    Full passage length: {content_len} chars")

        # Create questions
        question_ids = []
        for q_num in range(1, 26):
            if tracker.is_question_created(test_num, q_num):
                q_id = tracker.get_question_id(test_num, q_num)
                question_ids.append({"question_id": q_id, "order_number": q_num})
                continue

            # Build question data with appropriate passage reference
            question_data = build_question_data_v2(
                test_num, q_num, extracted,
                reading_passage_id=reading_passage_id if q_num <= 10 else None,
                cloze_passage_id=cloze_passage_id if 11 <= q_num <= 20 else None
            )

            if question_data:
                q_id = client.create_question(question_data)
                if q_id:
                    tracker.mark_question_created(test_num, q_num, q_id)
                    question_ids.append({"question_id": q_id, "order_number": q_num})
                    stats["text_questions"] += 1

                    answer = get_answer(test_num, q_num)
                    q_type = question_data.get("question_type", "unknown")
                    passage_linked = "P" if question_data.get("passage_id") else "-"
                    logger.info(f"    Q{q_num}: {q_type} [{passage_linked}] answer: {answer}")

            time.sleep(0.15)

        # Create question set
        if tracker.is_question_set_created(test_num):
            qs_id = tracker.get_question_set_id(test_num)
            logger.info(f"  Question set exists")
        else:
            qs_id = client.create_question_set(
                name=f"VR CEM Test {test_num} V2",
                subject="Verbal Reasoning",
                grade_level="Year 5-7",
                question_items=question_ids
            )
            if qs_id:
                tracker.mark_question_set_created(test_num, qs_id)
                logger.info(f"  Question set created ({len(question_ids)} questions)")

        # Create test (skip if --questions-only flag is set)
        if args.questions_only:
            logger.info(f"  Skipping test creation (--questions-only mode)")
        elif tracker.is_test_created(test_num):
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
        logger.info("DIGITIZATION V2 COMPLETE")
        logger.info("=" * 60)
        logger.info(f"Reading passages created: {stats['reading_passages']}")
        logger.info(f"Cloze passages created: {stats['cloze_passages']}")
        logger.info(f"Questions created: {stats['text_questions']}")
        logger.info(f"Tests created: {stats['tests']}")
        logger.info("=" * 60)


if __name__ == "__main__":
    main()
