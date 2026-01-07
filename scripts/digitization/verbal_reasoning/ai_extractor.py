#!/usr/bin/env python3
"""
AI-powered content extraction for 11+ Verbal Reasoning Testbook using OpenAI GPT-4 Vision.

This module sends test page images to GPT-4o and extracts:
- Question text
- Answer options
- Question type
- Correct answers (from answer key pages)
"""

import os
import sys
import json
import base64
import logging
import time
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from openai import OpenAI

# Logging setup
logger = logging.getLogger(__name__)

# OpenAI client - initialized lazily
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
    question_type: str  # multiple_choice, cloze_select, synonym_completion, etc.
    options: List[Dict[str, str]]  # [{"letter": "a", "text": "Option A"}, ...]
    instruction_text: Optional[str] = None
    context_text: Optional[str] = None  # For cloze passages, the surrounding text


@dataclass
class ExtractedPassage:
    """Extracted reading passage from AI"""
    title: str
    content: str
    source: Optional[str] = None
    glossary: Optional[Dict[str, str]] = None


@dataclass
class PageExtractionResult:
    """Result from extracting content from a single page"""
    page_number: int
    passage: Optional[ExtractedPassage] = None
    questions: List[ExtractedQuestion] = None
    raw_response: str = ""

    def __post_init__(self):
        if self.questions is None:
            self.questions = []


def extract_passage_page(image_path: str, test_num: int, max_retries: int = 3) -> Optional[PageExtractionResult]:
    """
    Extract reading passage and Q1 from the first page of a test.
    This page typically contains the reading comprehension passage.
    """
    client = get_openai_client()

    prompt = f"""Analyze this test page image from 11+ Verbal Reasoning Test {test_num}.

This page should contain a READING PASSAGE and possibly Question 1.

Extract and return a JSON object with this EXACT structure:
{{
    "passage": {{
        "title": "The title of the passage",
        "content": "The full text of the reading passage exactly as written",
        "source": "Source attribution if shown",
        "glossary": {{"term": "definition"}} // if any glossary terms are shown
    }},
    "questions": [
        {{
            "question_number": 1,
            "question_text": "The complete question text",
            "question_type": "multiple_choice",
            "options": [
                {{"letter": "a", "text": "Full text of option a"}},
                {{"letter": "b", "text": "Full text of option b"}},
                {{"letter": "c", "text": "Full text of option c"}},
                {{"letter": "d", "text": "Full text of option d"}}
            ]
        }}
    ]
}}

IMPORTANT:
- Extract the COMPLETE passage text, preserving paragraphs
- Extract ALL answer options with their FULL text
- If the passage has numbered lines, note them but don't include line numbers in the content
- Be accurate and complete in your extraction
- Return ONLY valid JSON, no additional text"""

    base64_image = encode_image_to_base64(image_path)

    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/png;base64,{base64_image}",
                                    "detail": "high"
                                }
                            }
                        ]
                    }
                ],
                max_tokens=4096,
                temperature=0.1
            )

            raw_content = response.choices[0].message.content
            logger.debug(f"Raw API response: {raw_content}")

            # Parse JSON from response
            json_content = _extract_json_from_response(raw_content)
            data = json.loads(json_content)

            # Build result
            page_num = int(Path(image_path).stem.split('-')[-1])
            result = PageExtractionResult(page_number=page_num, raw_response=raw_content)

            # Extract passage
            if "passage" in data and data["passage"]:
                p = data["passage"]
                result.passage = ExtractedPassage(
                    title=p.get("title", ""),
                    content=p.get("content", ""),
                    source=p.get("source"),
                    glossary=p.get("glossary")
                )

            # Extract questions
            if "questions" in data:
                for q in data["questions"]:
                    result.questions.append(ExtractedQuestion(
                        question_number=q["question_number"],
                        question_text=q["question_text"],
                        question_type=q.get("question_type", "multiple_choice"),
                        options=q.get("options", []),
                        instruction_text=q.get("instruction_text"),
                        context_text=q.get("context_text")
                    ))

            return result

        except json.JSONDecodeError as e:
            logger.warning(f"JSON parse error on attempt {attempt + 1}: {e}")
        except Exception as e:
            logger.warning(f"API error on attempt {attempt + 1}: {e}")

        if attempt < max_retries - 1:
            time.sleep(2 ** attempt)

    return None


def extract_mc_questions_page(image_path: str, test_num: int, expected_questions: List[int],
                               max_retries: int = 3) -> Optional[PageExtractionResult]:
    """
    Extract multiple choice questions (typically Q2-10) from a test page.
    """
    client = get_openai_client()

    q_range = f"Q{min(expected_questions)}-{max(expected_questions)}" if expected_questions else "questions"

    prompt = f"""Analyze this test page image from 11+ Verbal Reasoning Test {test_num}.

This page contains MULTIPLE CHOICE QUESTIONS ({q_range}) related to a reading passage.

Extract and return a JSON object with this EXACT structure:
{{
    "questions": [
        {{
            "question_number": <number>,
            "question_text": "The complete question text",
            "question_type": "multiple_choice",
            "options": [
                {{"letter": "a", "text": "Full text of option a"}},
                {{"letter": "b", "text": "Full text of option b"}},
                {{"letter": "c", "text": "Full text of option c"}},
                {{"letter": "d", "text": "Full text of option d"}}
            ]
        }}
    ]
}}

IMPORTANT:
- Extract EVERY question visible on this page
- Include the COMPLETE question text
- Include ALL answer options with their FULL text (not just letters)
- Question numbers should match exactly what's shown
- Return ONLY valid JSON, no additional text"""

    base64_image = encode_image_to_base64(image_path)

    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/png;base64,{base64_image}",
                                    "detail": "high"
                                }
                            }
                        ]
                    }
                ],
                max_tokens=4096,
                temperature=0.1
            )

            raw_content = response.choices[0].message.content
            logger.debug(f"Raw API response: {raw_content}")

            json_content = _extract_json_from_response(raw_content)
            data = json.loads(json_content)

            page_num = int(Path(image_path).stem.split('-')[-1])
            result = PageExtractionResult(page_number=page_num, raw_response=raw_content)

            if "questions" in data:
                for q in data["questions"]:
                    result.questions.append(ExtractedQuestion(
                        question_number=q["question_number"],
                        question_text=q["question_text"],
                        question_type=q.get("question_type", "multiple_choice"),
                        options=q.get("options", []),
                        instruction_text=q.get("instruction_text"),
                        context_text=q.get("context_text")
                    ))

            return result

        except json.JSONDecodeError as e:
            logger.warning(f"JSON parse error on attempt {attempt + 1}: {e}")
        except Exception as e:
            logger.warning(f"API error on attempt {attempt + 1}: {e}")

        if attempt < max_retries - 1:
            time.sleep(2 ** attempt)

    return None


def extract_cloze_questions_page(image_path: str, test_num: int, expected_questions: List[int],
                                  max_retries: int = 3) -> Optional[PageExtractionResult]:
    """
    Extract cloze-style questions (typically Q11-20) from a test page.
    These may include: fill-in-the-blank passages, odd-one-out, letter completion, etc.
    """
    client = get_openai_client()

    q_range = f"Q{min(expected_questions)}-{max(expected_questions)}" if expected_questions else "questions"

    prompt = f"""Analyze this test page image from 11+ Verbal Reasoning Test {test_num}.

This page contains VERBAL REASONING QUESTIONS ({q_range}). These could be:
- CLOZE/FILL-IN-THE-BLANK: A passage with numbered blanks to fill in from word options
- ODD-ONE-OUT: Groups of words where one doesn't belong
- LETTER COMPLETION: Words with missing letters to complete
- SENTENCE REARRANGEMENT: Jumbled words to form sentences

Extract and return a JSON object with this EXACT structure:
{{
    "section_type": "cloze_passage" | "odd_one_out" | "letter_completion" | "sentence_rearrange",
    "instruction_text": "The instruction text shown for this section",
    "context_passage": "If there's a passage with blanks, include it here with {{11}}, {{12}} etc. for blanks",
    "questions": [
        {{
            "question_number": <number>,
            "question_text": "Description of what to do for this question",
            "question_type": "cloze_select" | "odd_one_out" | "letter_completion",
            "options": [
                {{"text": "option1"}},
                {{"text": "option2"}},
                {{"text": "option3"}}
            ],
            "context_text": "The sentence or context where this blank appears (if applicable)"
        }}
    ]
}}

IMPORTANT:
- For CLOZE passages: Extract the full passage with blank markers, and list the word options for each blank
- For ODD-ONE-OUT: List all the words in the group as options
- For LETTER COMPLETION: Include the partial word shown and what needs to be completed
- Extract the EXACT instruction text shown at the top of the section
- Be precise with question numbers
- Return ONLY valid JSON, no additional text"""

    base64_image = encode_image_to_base64(image_path)

    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/png;base64,{base64_image}",
                                    "detail": "high"
                                }
                            }
                        ]
                    }
                ],
                max_tokens=4096,
                temperature=0.1
            )

            raw_content = response.choices[0].message.content
            logger.debug(f"Raw API response: {raw_content}")

            json_content = _extract_json_from_response(raw_content)
            data = json.loads(json_content)

            page_num = int(Path(image_path).stem.split('-')[-1])
            result = PageExtractionResult(page_number=page_num, raw_response=raw_content)

            # Store the context passage if present
            context_passage = data.get("context_passage", "")
            instruction_text = data.get("instruction_text", "")
            section_type = data.get("section_type", "cloze_passage")

            if "questions" in data:
                for q in data["questions"]:
                    # Determine question type based on section
                    q_type = q.get("question_type", section_type)
                    if q_type == "cloze_passage":
                        q_type = "cloze_select"

                    result.questions.append(ExtractedQuestion(
                        question_number=q["question_number"],
                        question_text=q.get("question_text", ""),
                        question_type=q_type,
                        options=q.get("options", []),
                        instruction_text=instruction_text or q.get("instruction_text"),
                        context_text=q.get("context_text") or context_passage
                    ))

            return result

        except json.JSONDecodeError as e:
            logger.warning(f"JSON parse error on attempt {attempt + 1}: {e}")
        except Exception as e:
            logger.warning(f"API error on attempt {attempt + 1}: {e}")

        if attempt < max_retries - 1:
            time.sleep(2 ** attempt)

    return None


def extract_synonym_questions_page(image_path: str, test_num: int, expected_questions: List[int],
                                    max_retries: int = 3) -> Optional[PageExtractionResult]:
    """
    Extract synonym/antonym questions (typically Q21-25) from a test page.
    These may include: letter box completion, word selection, etc.
    """
    client = get_openai_client()

    q_range = f"Q{min(expected_questions)}-{max(expected_questions)}" if expected_questions else "questions"

    prompt = f"""Analyze this test page image from 11+ Verbal Reasoning Test {test_num}.

This page contains SYNONYM/ANTONYM QUESTIONS ({q_range}). These could be:
- SYNONYM/ANTONYM LETTER BOXES: Complete letter boxes to form a word with same/opposite meaning
- SYNONYM/ANTONYM SELECT: Choose a word with same/opposite meaning from options
- ODD-ONE-OUT: Find the word that doesn't belong

Extract and return a JSON object with this EXACT structure:
{{
    "section_type": "synonym_letter" | "antonym_letter" | "synonym_select" | "antonym_select" | "odd_one_out",
    "instruction_text": "The instruction text shown for this section",
    "questions": [
        {{
            "question_number": <number>,
            "given_word": "The word shown that needs a synonym/antonym",
            "question_text": "Description of the question",
            "question_type": "synonym_completion" | "antonym_completion" | "synonym_select" | "odd_one_out",
            "partial_answer": "If letter boxes shown, the partial letters visible (e.g., 'i_t_ll_g_n_')",
            "options": [
                {{"text": "option1"}}
            ]
        }}
    ]
}}

IMPORTANT:
- For LETTER BOX questions: Extract the given word AND any partial letters shown in boxes
- For SELECT questions: Extract all the option words provided
- Include the EXACT instruction text
- Note whether it's asking for SYNONYM (same meaning) or ANTONYM (opposite meaning)
- Return ONLY valid JSON, no additional text"""

    base64_image = encode_image_to_base64(image_path)

    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/png;base64,{base64_image}",
                                    "detail": "high"
                                }
                            }
                        ]
                    }
                ],
                max_tokens=4096,
                temperature=0.1
            )

            raw_content = response.choices[0].message.content
            logger.debug(f"Raw API response: {raw_content}")

            json_content = _extract_json_from_response(raw_content)
            data = json.loads(json_content)

            page_num = int(Path(image_path).stem.split('-')[-1])
            result = PageExtractionResult(page_number=page_num, raw_response=raw_content)

            instruction_text = data.get("instruction_text", "")
            section_type = data.get("section_type", "synonym_letter")

            if "questions" in data:
                for q in data["questions"]:
                    # Build question text with given word
                    given_word = q.get("given_word", "")
                    q_text = q.get("question_text", "")
                    if given_word and not q_text:
                        q_text = f"Find a word that means the same as: {given_word}"

                    q_type = q.get("question_type", "synonym_completion")

                    result.questions.append(ExtractedQuestion(
                        question_number=q["question_number"],
                        question_text=f"{given_word}" if given_word else q_text,
                        question_type=q_type,
                        options=q.get("options", []),
                        instruction_text=instruction_text or q.get("instruction_text"),
                        context_text=q.get("partial_answer")  # Store partial letters in context
                    ))

            return result

        except json.JSONDecodeError as e:
            logger.warning(f"JSON parse error on attempt {attempt + 1}: {e}")
        except Exception as e:
            logger.warning(f"API error on attempt {attempt + 1}: {e}")

        if attempt < max_retries - 1:
            time.sleep(2 ** attempt)

    return None


def extract_full_test(images_dir: str, test_num: int, answer_keys: Dict[int, str]) -> Dict[str, Any]:
    """
    Extract all content from a complete test (all 4 pages).

    Args:
        images_dir: Directory containing test images
        test_num: Test number (1-20)
        answer_keys: Dict mapping question number to correct answer

    Returns:
        Dict with extracted passage and questions
    """
    # Calculate page numbers for this test
    start_page = 2 + (test_num - 1) * 4
    pages = list(range(start_page, min(start_page + 4, 82)))

    logger.info(f"Extracting Test {test_num} from pages {pages}")

    result = {
        "test_num": test_num,
        "passage": None,
        "questions": {},
        "errors": []
    }

    for i, page_num in enumerate(pages):
        filename = f"11+ Verbal Reasoning Year 5-7 CEM Style Testbook 1 21.07.21-{page_num:02d}.png"
        image_path = os.path.join(images_dir, filename)

        if not os.path.exists(image_path):
            result["errors"].append(f"Image not found: {filename}")
            continue

        logger.info(f"  Processing page {page_num} ({i+1}/{len(pages)})")

        try:
            if i == 0:
                # First page: Passage + Q1
                extraction = extract_passage_page(image_path, test_num)
                if extraction:
                    result["passage"] = extraction.passage
                    for q in extraction.questions:
                        result["questions"][q.question_number] = q

            elif i == 1:
                # Second page: Q2-7 (multiple choice)
                extraction = extract_mc_questions_page(image_path, test_num, list(range(2, 8)))
                if extraction:
                    for q in extraction.questions:
                        result["questions"][q.question_number] = q

            elif i == 2:
                # Third page: Q8-10 + Q11-15 (MC + start of cloze)
                # Extract MC questions first
                extraction = extract_mc_questions_page(image_path, test_num, list(range(8, 11)))
                if extraction:
                    for q in extraction.questions:
                        result["questions"][q.question_number] = q

                # Then cloze questions
                extraction = extract_cloze_questions_page(image_path, test_num, list(range(11, 21)))
                if extraction:
                    for q in extraction.questions:
                        result["questions"][q.question_number] = q

            elif i == 3:
                # Fourth page: remaining cloze (Q16-20) + synonyms (Q21-25)
                # First try cloze questions
                extraction = extract_cloze_questions_page(image_path, test_num, list(range(11, 21)))
                if extraction:
                    for q in extraction.questions:
                        if q.question_number not in result["questions"]:
                            result["questions"][q.question_number] = q

                # Then synonym questions
                extraction = extract_synonym_questions_page(image_path, test_num, list(range(21, 26)))
                if extraction:
                    for q in extraction.questions:
                        result["questions"][q.question_number] = q

        except Exception as e:
            logger.error(f"Error processing page {page_num}: {e}")
            result["errors"].append(f"Page {page_num}: {str(e)}")

        # Rate limiting
        time.sleep(1)

    # Add correct answers from answer keys
    for q_num, question in result["questions"].items():
        if q_num in answer_keys:
            question.correct_answer = answer_keys[q_num]

    logger.info(f"  Extracted: {len(result['questions'])} questions")
    return result


def _extract_json_from_response(response: str) -> str:
    """Extract JSON from API response, handling markdown code blocks"""
    response = response.strip()

    # Remove markdown code blocks
    if response.startswith("```json"):
        response = response[7:]
    elif response.startswith("```"):
        response = response[3:]

    if response.endswith("```"):
        response = response[:-3]

    return response.strip()


# Test function
def test_extraction(image_path: str):
    """Test extraction on a single image"""
    print(f"Testing extraction on: {image_path}")

    result = extract_passage_page(image_path, 1)

    if result:
        print(f"\nPassage: {result.passage.title if result.passage else 'None'}")
        print(f"Questions found: {len(result.questions)}")
        for q in result.questions:
            print(f"  Q{q.question_number}: {q.question_text[:50]}...")
    else:
        print("Extraction failed")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    if len(sys.argv) > 1:
        test_extraction(sys.argv[1])
    else:
        print("Usage: python ai_extractor.py <image_path>")
