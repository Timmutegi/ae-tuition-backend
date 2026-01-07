#!/usr/bin/env python3
"""
Improved AI-powered content extraction for 11+ Verbal Reasoning Testbook.

Key improvements over v1:
1. Uses known question types from question_types.py to tailor extraction
2. Extracts FULL cloze passages by combining multiple pages
3. Type-specific prompts for better accuracy
4. Creates separate cloze passage objects for Q11-20
"""

import os
import sys
import json
import base64
import logging
import time
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from openai import OpenAI

# Import question type definitions
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from question_types import (
    get_q11_20_type, get_q21_25_type,
    Q11_20_TEXT_CAPABLE, QUESTION_INSTRUCTIONS
)

logger = logging.getLogger(__name__)

_openai_client: Optional[OpenAI] = None


def get_openai_client() -> OpenAI:
    """Get or create OpenAI client"""
    global _openai_client
    if _openai_client is None:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY environment variable is not set")
        _openai_client = OpenAI(api_key=api_key)
    return _openai_client


def encode_image_to_base64(image_path: str) -> str:
    """Encode image file to base64 string"""
    with open(image_path, "rb") as image_file:
        return base64.standard_b64encode(image_file.read()).decode("utf-8")


@dataclass
class ExtractedQuestion:
    """Extracted question data from AI"""
    question_number: int
    question_text: str
    question_type: str
    options: List[Dict[str, str]] = field(default_factory=list)
    instruction_text: Optional[str] = None
    context_text: Optional[str] = None  # For cloze: the sentence containing this blank
    given_word: Optional[str] = None  # For synonym/antonym questions


@dataclass
class ExtractedPassage:
    """Extracted passage (reading or cloze)"""
    title: str
    content: str
    passage_type: str = "reading"  # "reading" or "cloze"
    source: Optional[str] = None
    glossary: Optional[Dict[str, str]] = None
    blank_options: Optional[Dict[int, List[str]]] = None  # For cloze: {11: ["opt1", "opt2"], ...}


@dataclass
class TestExtractionResult:
    """Complete extraction result for a test"""
    test_num: int
    reading_passage: Optional[ExtractedPassage] = None
    cloze_passage: Optional[ExtractedPassage] = None
    questions: Dict[int, ExtractedQuestion] = field(default_factory=dict)
    q11_20_type: str = ""
    q21_25_type: str = ""
    errors: List[str] = field(default_factory=list)


def _extract_json_from_response(response: str) -> str:
    """Extract JSON from API response, handling markdown code blocks"""
    response = response.strip()
    if response.startswith("```json"):
        response = response[7:]
    elif response.startswith("```"):
        response = response[3:]
    if response.endswith("```"):
        response = response[:-3]
    return response.strip()


def _call_gpt_vision(
    prompt: str,
    image_paths: List[str],
    max_tokens: int = 4096,
    max_retries: int = 3
) -> Optional[Dict]:
    """
    Call GPT-4 Vision with one or more images.
    Returns parsed JSON or None on failure.
    """
    client = get_openai_client()

    # Build message content with all images
    content = [{"type": "text", "text": prompt}]
    for image_path in image_paths:
        if os.path.exists(image_path):
            base64_image = encode_image_to_base64(image_path)
            content.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/png;base64,{base64_image}",
                    "detail": "high"
                }
            })

    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": content}],
                max_tokens=max_tokens,
                temperature=0.1
            )

            raw_content = response.choices[0].message.content
            json_content = _extract_json_from_response(raw_content)
            return json.loads(json_content)

        except json.JSONDecodeError as e:
            logger.warning(f"JSON parse error on attempt {attempt + 1}: {e}")
        except Exception as e:
            logger.warning(f"API error on attempt {attempt + 1}: {e}")

        if attempt < max_retries - 1:
            time.sleep(2 ** attempt)

    return None


# ============== Reading Passage Extraction (Q1-10) ==============

def extract_reading_passage_and_q1_10(
    page1_path: str,
    page2_path: str,
    page3_path: str,
    test_num: int
) -> Tuple[Optional[ExtractedPassage], Dict[int, ExtractedQuestion]]:
    """
    Extract reading passage and Q1-10 from pages 1-3 of a test.
    Sends all 3 pages together for better context.
    """
    prompt = f"""Analyze these test pages from 11+ Verbal Reasoning Test {test_num}.

These pages contain:
- A READING PASSAGE (on page 1)
- MULTIPLE CHOICE QUESTIONS 1-10 about the passage (pages 1-3)

Extract and return a JSON object with this EXACT structure:
{{
    "passage": {{
        "title": "The title of the passage",
        "content": "The COMPLETE text of the reading passage, preserving all paragraphs",
        "source": "Source/author attribution if shown"
    }},
    "questions": [
        {{
            "question_number": 1,
            "question_text": "The complete question text",
            "options": [
                {{"letter": "a", "text": "Full text of option a"}},
                {{"letter": "b", "text": "Full text of option b"}},
                {{"letter": "c", "text": "Full text of option c"}},
                {{"letter": "d", "text": "Full text of option d"}}
            ]
        }}
        // ... questions 2-10
    ]
}}

IMPORTANT:
- Extract the COMPLETE passage text with all paragraphs
- Extract ALL 10 questions with their complete text
- Include ALL answer options with FULL text (not just letters)
- Return ONLY valid JSON"""

    data = _call_gpt_vision(prompt, [page1_path, page2_path, page3_path], max_tokens=8000)

    if not data:
        return None, {}

    passage = None
    if "passage" in data and data["passage"]:
        p = data["passage"]
        passage = ExtractedPassage(
            title=p.get("title", f"Test {test_num} Passage"),
            content=p.get("content", ""),
            passage_type="reading",
            source=p.get("source")
        )

    questions = {}
    if "questions" in data:
        for q in data["questions"]:
            q_num = q.get("question_number", 0)
            if 1 <= q_num <= 10:
                questions[q_num] = ExtractedQuestion(
                    question_number=q_num,
                    question_text=q.get("question_text", ""),
                    question_type="multiple_choice",
                    options=q.get("options", [])
                )

    return passage, questions


# ============== Cloze Passage Extraction (Q11-20) ==============

def extract_cloze_passage_questions(
    page3_path: str,
    page4_path: str,
    test_num: int,
    q_type: str
) -> Tuple[Optional[ExtractedPassage], Dict[int, ExtractedQuestion]]:
    """
    Extract Q11-20 based on the question type.
    Sends both pages together to capture the full context.
    """
    if q_type == "CLOZE_PASSAGE":
        return _extract_cloze_word_selection(page3_path, page4_path, test_num)
    elif q_type == "LETTER_COMPLETION_CLOZE":
        return _extract_cloze_letter_completion(page3_path, page4_path, test_num)
    elif q_type == "ODD_ONE_OUT":
        return _extract_odd_one_out(page3_path, page4_path, test_num)
    elif q_type in ["ANTONYM_LETTER", "SYNONYM_LETTER"]:
        return _extract_letter_box_questions(page3_path, page4_path, test_num, q_type)
    elif q_type == "LETTER_WORD_MATCH":
        return _extract_letter_word_match(page3_path, page4_path, test_num)
    else:
        # Generic extraction
        return _extract_generic_q11_20(page3_path, page4_path, test_num)


def _extract_cloze_word_selection(
    page3_path: str,
    page4_path: str,
    test_num: int
) -> Tuple[Optional[ExtractedPassage], Dict[int, ExtractedQuestion]]:
    """
    Extract CLOZE_PASSAGE type: A passage with numbered blanks and word options.
    Example: "There are {11} [roughly/roguishly/roundly] 1,240 species..."
    """
    prompt = f"""Analyze these test pages from 11+ Verbal Reasoning Test {test_num}.

These pages contain a CLOZE PASSAGE where students select words to fill numbered blanks (11-20).
The passage is CONTINUOUS - it flows across both pages.

Extract and return a JSON object with this EXACT structure:
{{
    "passage": {{
        "title": "Brief topic of the passage (e.g., 'Bats', 'Submarines')",
        "full_text": "The COMPLETE passage text with blank markers like {{11}}, {{12}}, etc.",
        "instruction": "The instruction text shown (e.g., 'Select the correct words to complete the passage')"
    }},
    "blanks": {{
        "11": {{
            "options": ["option1", "option2", "option3"],
            "sentence_context": "The sentence containing blank 11"
        }},
        "12": {{
            "options": ["option1", "option2", "option3"],
            "sentence_context": "The sentence containing blank 12"
        }}
        // ... blanks 13-20
    }}
}}

CRITICAL REQUIREMENTS:
1. The "full_text" must contain the ENTIRE passage from start to finish
2. Use {{11}}, {{12}}, etc. to mark where blanks appear in the text
3. Extract ALL options for each blank
4. The passage continues across both pages - combine them into one complete text
5. Return ONLY valid JSON"""

    data = _call_gpt_vision(prompt, [page3_path, page4_path], max_tokens=6000)

    if not data:
        return None, {}

    passage = None
    blank_options = {}
    questions = {}

    if "passage" in data:
        p = data["passage"]
        full_text = p.get("full_text", "")
        instruction = p.get("instruction", "Select the correct words to complete the passage.")

        # Collect blank options
        if "blanks" in data:
            for blank_num, blank_data in data["blanks"].items():
                try:
                    num = int(blank_num)
                    blank_options[num] = blank_data.get("options", [])

                    # Create question for each blank
                    questions[num] = ExtractedQuestion(
                        question_number=num,
                        question_text=f"Select the correct word for blank {num}",
                        question_type="cloze_select",
                        options=[{"text": opt} for opt in blank_data.get("options", [])],
                        instruction_text=instruction,
                        context_text=blank_data.get("sentence_context", "")
                    )
                except ValueError:
                    continue

        passage = ExtractedPassage(
            title=p.get("title", "Cloze Passage"),
            content=full_text,
            passage_type="cloze",
            blank_options=blank_options
        )

    return passage, questions


def _extract_cloze_letter_completion(
    page3_path: str,
    page4_path: str,
    test_num: int
) -> Tuple[Optional[ExtractedPassage], Dict[int, ExtractedQuestion]]:
    """
    Extract LETTER_COMPLETION_CLOZE type: A passage with words that have missing letters.
    Example: "Submarines are a form of 11) v_e_s_l that can operate underwater..."
    """
    prompt = f"""Analyze these test pages from 11+ Verbal Reasoning Test {test_num}.

These pages contain a LETTER COMPLETION CLOZE PASSAGE where students fill in missing letters.
Each numbered blank (11-20) shows a word with some letters in boxes and some missing.
The passage is CONTINUOUS across both pages.

Extract and return a JSON object with this EXACT structure:
{{
    "passage": {{
        "title": "Brief topic of the passage",
        "full_text": "The COMPLETE passage with {{11}}, {{12}}, etc. marking where incomplete words appear",
        "instruction": "The instruction text shown"
    }},
    "words": {{
        "11": {{
            "partial_letters": "v_e_s_l",
            "sentence_context": "The sentence containing this word"
        }},
        "12": {{
            "partial_letters": "_tr_ct_r_s",
            "sentence_context": "The sentence containing this word"
        }}
        // ... words 13-20
    }}
}}

IMPORTANT:
- Capture the ENTIRE continuous passage across both pages
- Show partial letters exactly as displayed (use _ for blank boxes)
- Return ONLY valid JSON"""

    data = _call_gpt_vision(prompt, [page3_path, page4_path], max_tokens=6000)

    if not data:
        return None, {}

    passage = None
    questions = {}

    if "passage" in data:
        p = data["passage"]
        instruction = p.get("instruction", "Fill in the missing letters to complete each word.")

        passage = ExtractedPassage(
            title=p.get("title", "Cloze Passage"),
            content=p.get("full_text", ""),
            passage_type="cloze_letter"
        )

        if "words" in data:
            for word_num, word_data in data["words"].items():
                try:
                    num = int(word_num)
                    partial = word_data.get("partial_letters", "")
                    questions[num] = ExtractedQuestion(
                        question_number=num,
                        question_text=f"Complete the word: {partial}",
                        question_type="letter_completion",
                        instruction_text=instruction,
                        context_text=word_data.get("sentence_context", "")
                    )
                except ValueError:
                    continue

    return passage, questions


def _extract_odd_one_out(
    page3_path: str,
    page4_path: str,
    test_num: int
) -> Tuple[None, Dict[int, ExtractedQuestion]]:
    """
    Extract ODD_ONE_OUT type: Groups of words where one doesn't belong.
    May also include SENTENCE_REARRANGE questions.
    """
    prompt = f"""Analyze these test pages from 11+ Verbal Reasoning Test {test_num}.

These pages contain two types of questions:
1. ODD ONE OUT: Lists of words where one doesn't belong (usually Q11-15)
2. SENTENCE REARRANGE: Jumbled words where one doesn't fit into the sentence (usually Q16-20)

Extract and return a JSON object:
{{
    "odd_one_out_instruction": "The instruction for odd-one-out section",
    "sentence_rearrange_instruction": "The instruction for sentence rearrange section",
    "questions": [
        {{
            "question_number": 11,
            "question_type": "odd_one_out",
            "words": ["word1", "word2", "word3", "word4", "word5"]
        }},
        {{
            "question_number": 16,
            "question_type": "sentence_rearrange",
            "words": ["word1", "word2", "word3", "word4", "word5", "word6", "word7"]
        }}
        // ... all questions 11-20
    ]
}}

IMPORTANT:
- Extract ALL words for each question in the exact order shown
- Correctly identify the question type
- Return ONLY valid JSON"""

    data = _call_gpt_vision(prompt, [page3_path, page4_path], max_tokens=4000)

    if not data:
        return None, {}

    questions = {}
    odd_instruction = data.get("odd_one_out_instruction",
        "Four of the words are linked. Select the word that is NOT related.")
    rearrange_instruction = data.get("sentence_rearrange_instruction",
        "Rearrange the words to make a sentence. Select the word that does NOT fit.")

    if "questions" in data:
        for q in data["questions"]:
            q_num = q.get("question_number", 0)
            q_type = q.get("question_type", "odd_one_out")
            words = q.get("words", [])

            if 11 <= q_num <= 20:
                instruction = odd_instruction if q_type == "odd_one_out" else rearrange_instruction
                questions[q_num] = ExtractedQuestion(
                    question_number=q_num,
                    question_text=" | ".join(words),
                    question_type=q_type,
                    options=[{"text": w} for w in words],
                    instruction_text=instruction
                )

    return None, questions


def _extract_letter_box_questions(
    page3_path: str,
    page4_path: str,
    test_num: int,
    q_type: str
) -> Tuple[None, Dict[int, ExtractedQuestion]]:
    """
    Extract ANTONYM_LETTER or SYNONYM_LETTER type questions.
    Given word on left, letter boxes on right to complete.
    """
    is_antonym = "ANTONYM" in q_type
    meaning_type = "opposite" if is_antonym else "same"

    prompt = f"""Analyze these test pages from 11+ Verbal Reasoning Test {test_num}.

These pages contain questions where:
- A word is given on the LEFT
- Letter boxes on the RIGHT need to be filled to spell a word with the {meaning_type} meaning

Extract and return a JSON object:
{{
    "instruction": "The instruction text shown",
    "questions": [
        {{
            "question_number": 11,
            "given_word": "happy",
            "partial_answer": "s_d"
        }}
        // ... all questions 11-20
    ]
}}

IMPORTANT:
- Extract the given word exactly as shown
- Show partial letters in boxes and use _ for empty boxes
- Return ONLY valid JSON"""

    data = _call_gpt_vision(prompt, [page3_path, page4_path], max_tokens=4000)

    if not data:
        return None, {}

    questions = {}
    instruction = data.get("instruction",
        f"Complete the word on the right so it means the {meaning_type} of the word on the left.")

    if "questions" in data:
        for q in data["questions"]:
            q_num = q.get("question_number", 0)
            given_word = q.get("given_word", "")
            partial = q.get("partial_answer", "")

            if 11 <= q_num <= 20:
                questions[q_num] = ExtractedQuestion(
                    question_number=q_num,
                    question_text=f"{given_word} -> {partial}",
                    question_type="antonym_completion" if is_antonym else "synonym_completion",
                    instruction_text=instruction,
                    given_word=given_word,
                    context_text=partial  # Store partial letters in context
                )

    return None, questions


def _extract_letter_word_match(
    page3_path: str,
    page4_path: str,
    test_num: int
) -> Tuple[None, Dict[int, ExtractedQuestion]]:
    """Extract LETTER_WORD_MATCH type: Match letters to words in a grid."""
    prompt = f"""Analyze these test pages from 11+ Verbal Reasoning Test {test_num}.

These pages contain a LETTER-WORD MATCHING exercise where letters need to be matched to words.

Extract and return a JSON object describing the exercise:
{{
    "instruction": "The instruction text shown",
    "questions": [
        {{
            "question_number": 11,
            "description": "Description of what needs to be matched",
            "options": ["option1", "option2", "option3"]
        }}
        // ... all questions 11-20
    ]
}}

Return ONLY valid JSON"""

    data = _call_gpt_vision(prompt, [page3_path, page4_path], max_tokens=4000)

    if not data:
        return None, {}

    questions = {}
    instruction = data.get("instruction", "Match letters to the correct words.")

    if "questions" in data:
        for q in data["questions"]:
            q_num = q.get("question_number", 0)
            if 11 <= q_num <= 20:
                questions[q_num] = ExtractedQuestion(
                    question_number=q_num,
                    question_text=q.get("description", f"Question {q_num}"),
                    question_type="letter_word_match",
                    options=[{"text": opt} for opt in q.get("options", [])],
                    instruction_text=instruction
                )

    return None, questions


def _extract_generic_q11_20(
    page3_path: str,
    page4_path: str,
    test_num: int
) -> Tuple[None, Dict[int, ExtractedQuestion]]:
    """Generic extraction for unknown Q11-20 types."""
    prompt = f"""Analyze these test pages from 11+ Verbal Reasoning Test {test_num}.

Extract questions 11-20. These could be various verbal reasoning formats.

Return a JSON object:
{{
    "instruction": "The instruction text shown",
    "questions": [
        {{
            "question_number": 11,
            "question_text": "The question or content shown",
            "options": ["option1", "option2", ...]
        }}
        // ... questions 11-20
    ]
}}

Return ONLY valid JSON"""

    data = _call_gpt_vision(prompt, [page3_path, page4_path], max_tokens=4000)

    if not data:
        return None, {}

    questions = {}
    instruction = data.get("instruction", "Answer the following questions.")

    if "questions" in data:
        for q in data["questions"]:
            q_num = q.get("question_number", 0)
            if 11 <= q_num <= 20:
                questions[q_num] = ExtractedQuestion(
                    question_number=q_num,
                    question_text=q.get("question_text", ""),
                    question_type="verbal_reasoning",
                    options=[{"text": opt} for opt in q.get("options", [])],
                    instruction_text=instruction
                )

    return None, questions


# ============== Synonym/Antonym Questions (Q21-25) ==============

def extract_q21_25(
    page4_path: str,
    test_num: int,
    q_type: str
) -> Dict[int, ExtractedQuestion]:
    """Extract Q21-25 based on question type."""

    if q_type in ["SYNONYM_SELECT", "ANTONYM_SELECT"]:
        return _extract_select_questions(page4_path, test_num, q_type)
    elif q_type in ["SYNONYM_LETTER", "ANTONYM_LETTER"]:
        return _extract_letter_completion_q21_25(page4_path, test_num, q_type)
    else:
        return _extract_generic_q21_25(page4_path, test_num)


def _extract_select_questions(
    page4_path: str,
    test_num: int,
    q_type: str
) -> Dict[int, ExtractedQuestion]:
    """Extract SYNONYM_SELECT or ANTONYM_SELECT type."""
    is_antonym = "ANTONYM" in q_type
    meaning = "opposite" if is_antonym else "same"

    prompt = f"""Analyze this test page from 11+ Verbal Reasoning Test {test_num}.

Questions 21-25 ask students to select a word with the {meaning} meaning.

Extract and return a JSON object:
{{
    "instruction": "The instruction text shown",
    "questions": [
        {{
            "question_number": 21,
            "given_word": "word",
            "options": ["option1", "option2", "option3", "option4"]
        }}
        // ... questions 22-25
    ]
}}

Return ONLY valid JSON"""

    data = _call_gpt_vision(prompt, [page4_path], max_tokens=2000)

    if not data:
        return {}

    questions = {}
    instruction = data.get("instruction",
        f"Choose the word that means the {meaning} of the word on the left.")

    if "questions" in data:
        for q in data["questions"]:
            q_num = q.get("question_number", 0)
            if 21 <= q_num <= 25:
                given_word = q.get("given_word", "")
                questions[q_num] = ExtractedQuestion(
                    question_number=q_num,
                    question_text=f"Find a word meaning the {meaning} as: {given_word}",
                    question_type="antonym_select" if is_antonym else "synonym_select",
                    options=[{"text": opt} for opt in q.get("options", [])],
                    instruction_text=instruction,
                    given_word=given_word
                )

    return questions


def _extract_letter_completion_q21_25(
    page4_path: str,
    test_num: int,
    q_type: str
) -> Dict[int, ExtractedQuestion]:
    """Extract SYNONYM_LETTER or ANTONYM_LETTER for Q21-25."""
    is_antonym = "ANTONYM" in q_type
    meaning = "opposite" if is_antonym else "same"

    prompt = f"""Analyze this test page from 11+ Verbal Reasoning Test {test_num}.

Questions 21-25 show a word on the left and letter boxes on the right.
Students complete the boxes to spell a word with the {meaning} meaning.

Extract and return a JSON object:
{{
    "instruction": "The instruction text shown",
    "questions": [
        {{
            "question_number": 21,
            "given_word": "smart",
            "partial_answer": "_n_t_l_g_n_t"
        }}
        // ... questions 22-25
    ]
}}

Use _ for empty letter boxes. Return ONLY valid JSON"""

    data = _call_gpt_vision(prompt, [page4_path], max_tokens=2000)

    if not data:
        return {}

    questions = {}
    instruction = data.get("instruction",
        f"Complete the word on the right so it means the {meaning} of the word on the left.")

    if "questions" in data:
        for q in data["questions"]:
            q_num = q.get("question_number", 0)
            if 21 <= q_num <= 25:
                given_word = q.get("given_word", "")
                partial = q.get("partial_answer", "")
                questions[q_num] = ExtractedQuestion(
                    question_number=q_num,
                    question_text=f"{given_word} -> {partial}",
                    question_type="antonym_completion" if is_antonym else "synonym_completion",
                    instruction_text=instruction,
                    given_word=given_word,
                    context_text=partial
                )

    return questions


def _extract_generic_q21_25(
    page4_path: str,
    test_num: int
) -> Dict[int, ExtractedQuestion]:
    """Generic extraction for Q21-25."""
    prompt = f"""Analyze this test page from 11+ Verbal Reasoning Test {test_num}.

Extract questions 21-25 (usually synonym or antonym questions).

Return a JSON object:
{{
    "instruction": "The instruction text",
    "questions": [
        {{
            "question_number": 21,
            "given_word": "word if shown",
            "question_text": "Description or partial letters",
            "options": ["option1", "option2"] // if any options shown
        }}
    ]
}}

Return ONLY valid JSON"""

    data = _call_gpt_vision(prompt, [page4_path], max_tokens=2000)

    if not data:
        return {}

    questions = {}
    instruction = data.get("instruction", "")

    if "questions" in data:
        for q in data["questions"]:
            q_num = q.get("question_number", 0)
            if 21 <= q_num <= 25:
                questions[q_num] = ExtractedQuestion(
                    question_number=q_num,
                    question_text=q.get("question_text", q.get("given_word", "")),
                    question_type="synonym_completion",
                    options=[{"text": opt} for opt in q.get("options", [])],
                    instruction_text=instruction,
                    given_word=q.get("given_word")
                )

    return questions


# ============== Main Extraction Function ==============

def extract_full_test_v2(
    images_dir: str,
    test_num: int
) -> TestExtractionResult:
    """
    Extract all content from a complete test using improved type-aware extraction.

    Args:
        images_dir: Directory containing test images
        test_num: Test number (1-20)

    Returns:
        TestExtractionResult with passages and questions
    """
    result = TestExtractionResult(
        test_num=test_num,
        q11_20_type=get_q11_20_type(test_num),
        q21_25_type=get_q21_25_type(test_num)
    )

    # Calculate page numbers for this test
    start_page = 2 + (test_num - 1) * 4
    pages = list(range(start_page, min(start_page + 4, 82)))

    def get_path(page_num: int) -> str:
        filename = f"11+ Verbal Reasoning Year 5-7 CEM Style Testbook 1 21.07.21-{page_num:02d}.png"
        return os.path.join(images_dir, filename)

    page_paths = [get_path(p) for p in pages]

    logger.info(f"Extracting Test {test_num} (Q11-20 type: {result.q11_20_type})")

    try:
        # Extract reading passage and Q1-10
        logger.info("  Extracting reading passage and Q1-10...")
        result.reading_passage, q1_10 = extract_reading_passage_and_q1_10(
            page_paths[0], page_paths[1], page_paths[2], test_num
        )
        result.questions.update(q1_10)
        time.sleep(2)  # Rate limiting

        # Extract Q11-20 based on type
        logger.info(f"  Extracting Q11-20 ({result.q11_20_type})...")
        result.cloze_passage, q11_20 = extract_cloze_passage_questions(
            page_paths[2], page_paths[3], test_num, result.q11_20_type
        )
        result.questions.update(q11_20)
        time.sleep(2)

        # Extract Q21-25
        logger.info(f"  Extracting Q21-25 ({result.q21_25_type})...")
        q21_25 = extract_q21_25(page_paths[3], test_num, result.q21_25_type)
        result.questions.update(q21_25)

    except Exception as e:
        logger.error(f"Error extracting Test {test_num}: {e}")
        result.errors.append(str(e))

    logger.info(f"  Extracted {len(result.questions)} questions")
    return result


# ============== Test Function ==============

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    import sys
    if len(sys.argv) > 1:
        test_num = int(sys.argv[1])
        images_dir = os.getenv(
            "IMAGES_DIR",
            "/Users/timothymbaka/tesh/kaziflex/ae-tuition/11+_Verbal_Reasoning_Year_5-7_CEM_Style_Testbook_1"
        )

        result = extract_full_test_v2(images_dir, test_num)

        print(f"\n=== Test {test_num} Extraction Results ===")
        print(f"Reading Passage: {result.reading_passage.title if result.reading_passage else 'None'}")
        print(f"Cloze Passage: {result.cloze_passage.title if result.cloze_passage else 'None'}")
        print(f"Questions: {len(result.questions)}")

        for q_num in sorted(result.questions.keys()):
            q = result.questions[q_num]
            print(f"  Q{q_num} ({q.question_type}): {q.question_text[:60]}...")
    else:
        print("Usage: python ai_extractor_v2.py <test_number>")
