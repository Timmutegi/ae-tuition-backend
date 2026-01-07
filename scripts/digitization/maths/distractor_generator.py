#!/usr/bin/env python3
"""
Distractor Generator for Maths MCQ Tests

Uses OpenAI GPT-4 to generate plausible wrong answers (distractors) for maths questions.
Includes answer type classification and caching to optimize API costs.

Usage:
    from distractor_generator import DistractorGenerator

    generator = DistractorGenerator()
    distractors = generator.generate_distractors(
        correct_answer="120",
        test_num=1,
        question_num=1
    )
"""

import os
import re
import json
import logging
import random
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from openai import OpenAI

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Cache file location
SCRIPT_DIR = Path(__file__).parent
CACHE_FILE = SCRIPT_DIR / "distractor_cache.json"


class AnswerType:
    """Answer type classifications"""
    INTEGER = "integer"
    DECIMAL = "decimal"
    FRACTION = "fraction"
    MIXED_FRACTION = "mixed_fraction"
    MULTIPLE_VALUES = "multiple_values"
    LETTER = "letter"
    YES_NO = "yes_no"
    TEXT_WORD = "text_word"
    RATIO = "ratio"
    TIME = "time"
    MONEY = "money"
    COMPASS = "compass"
    COMPOUND = "compound"
    PERCENTAGE = "percentage"
    DEGREE = "degree"
    MEASUREMENT = "measurement"
    EQUATION = "equation"
    SHAPE = "shape"
    UNKNOWN = "unknown"


class DistractorGenerator:
    """
    Generates plausible wrong answers (distractors) for maths MCQ questions.

    Uses GPT-4 for intelligent distractor generation with caching to minimize API costs.
    """

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize the distractor generator.

        Args:
            api_key: OpenAI API key. If not provided, reads from OPENAI_API_KEY env var.
        """
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OpenAI API key not found. Set OPENAI_API_KEY environment variable.")

        self.client = OpenAI(api_key=self.api_key)
        self.cache = self._load_cache()

    def _load_cache(self) -> Dict:
        """Load cached distractors from file."""
        if CACHE_FILE.exists():
            try:
                with open(CACHE_FILE, 'r') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                logger.warning(f"Error loading cache: {e}")
        return {}

    def _save_cache(self) -> None:
        """Save distractors cache to file."""
        try:
            with open(CACHE_FILE, 'w') as f:
                json.dump(self.cache, f, indent=2)
        except IOError as e:
            logger.warning(f"Error saving cache: {e}")

    def _get_cache_key(self, test_num: int, question_num: int) -> str:
        """Generate cache key for a question."""
        return f"test_{test_num}_q_{question_num}"

    def classify_answer(self, answer: str) -> str:
        """
        Classify the answer type for appropriate distractor generation.

        Args:
            answer: The correct answer string

        Returns:
            Answer type classification string
        """
        answer = str(answer).strip()
        answer_lower = answer.lower()

        # Letter answers (a, b, c, d, A, B, C, D)
        if re.match(r'^[a-dA-D]$', answer):
            return AnswerType.LETTER

        # Yes/No answers
        if answer_lower in ['yes', 'no', 'true', 'false']:
            return AnswerType.YES_NO

        # Compass directions
        compass_directions = ['north', 'south', 'east', 'west', 'north-east', 'north-west',
                            'south-east', 'south-west', 'n', 's', 'e', 'w', 'ne', 'nw', 'se', 'sw']
        if answer_lower in compass_directions:
            return AnswerType.COMPASS

        # Shapes
        shapes = ['square', 'rectangle', 'triangle', 'circle', 'pentagon', 'hexagon', 'heptagon',
                 'octagon', 'trapezium', 'parallelogram', 'rhombus', 'kite', 'regular heptagon',
                 'regular octagon', 'regular pentagon', 'regular hexagon']
        if answer_lower in shapes:
            return AnswerType.SHAPE

        # Money (£ symbol)
        if '£' in answer or answer.startswith('$'):
            return AnswerType.MONEY

        # Percentage
        if '%' in answer:
            return AnswerType.PERCENTAGE

        # Degree (angles, temperature)
        if '°' in answer:
            return AnswerType.DEGREE

        # Time patterns (8.29am, 10:30pm, 00:39)
        if re.match(r'^\d{1,2}[.:]\d{2}\s*(am|pm)?$', answer_lower) or \
           re.match(r'^\d{1,2}:\d{2}$', answer):
            return AnswerType.TIME

        # Measurement (cm, m, km, ft, etc.)
        if re.search(r'\d+\.?\d*\s*(cm|m|km|mm|ft|inches?|yards?|miles?|cm²|m²|cm³|m³)', answer_lower):
            return AnswerType.MEASUREMENT

        # Ratio (4:3, 3:1)
        if re.match(r'^\d+\s*:\s*\d+$', answer):
            return AnswerType.RATIO

        # Equation/variable assignment (A = 10, B = 12, C = 2)
        if re.search(r'[A-Za-z]\s*=\s*\d+', answer):
            return AnswerType.EQUATION

        # Compound answers with 'and' (20 days and 6 hours)
        if ' and ' in answer_lower and not re.match(r'^[\d,\s]+$', answer.replace(' and ', ', ')):
            return AnswerType.COMPOUND

        # Multiple values (13, 17 or 25 and 49 or 1, 2, 3, 4, 6)
        if ', ' in answer or ' and ' in answer_lower:
            return AnswerType.MULTIPLE_VALUES

        # Mixed fraction (1 3/4, 4 1/2)
        if re.match(r'^\d+\s+\d+/\d+$', answer):
            return AnswerType.MIXED_FRACTION

        # Simple fraction (1/100, 5/6)
        if re.match(r'^\d+/\d+$', answer):
            return AnswerType.FRACTION

        # Decimal (0.3, 1.76)
        if re.match(r'^-?\d+\.\d+$', answer):
            return AnswerType.DECIMAL

        # Integer (120, -6)
        if re.match(r'^-?\d+$', answer):
            return AnswerType.INTEGER

        # Text word (Thursday, vertical, reflex)
        if re.match(r'^[a-zA-Z]+$', answer):
            return AnswerType.TEXT_WORD

        return AnswerType.UNKNOWN

    def _generate_letter_distractors(self, correct: str) -> List[str]:
        """Generate distractors for letter answers (a, b, c, d)."""
        all_letters = ['a', 'b', 'c', 'd']
        correct_lower = correct.lower()
        distractors = [l for l in all_letters if l != correct_lower]
        # Match case of original
        if correct.isupper():
            distractors = [d.upper() for d in distractors]
        return distractors

    def _generate_yes_no_distractors(self, correct: str) -> List[str]:
        """Generate distractors for yes/no answers."""
        answer_lower = correct.lower()
        if answer_lower == 'yes':
            return ['no', 'maybe', 'cannot determine']
        elif answer_lower == 'no':
            return ['yes', 'maybe', 'cannot determine']
        elif answer_lower == 'true':
            return ['false', 'cannot determine', 'sometimes']
        elif answer_lower == 'false':
            return ['true', 'cannot determine', 'sometimes']
        return ['yes', 'no', 'maybe']

    def _generate_compass_distractors(self, correct: str) -> List[str]:
        """Generate distractors for compass direction answers."""
        all_directions = ['north', 'south', 'east', 'west', 'north-east',
                         'north-west', 'south-east', 'south-west']
        correct_lower = correct.lower()
        distractors = [d for d in all_directions if d != correct_lower]
        random.shuffle(distractors)
        return distractors[:3]

    def _generate_with_ai(self, correct_answer: str, answer_type: str,
                         test_num: int, question_num: int) -> List[str]:
        """
        Generate distractors using GPT-4.

        Args:
            correct_answer: The correct answer
            answer_type: Classification of the answer type
            test_num: Test number for context
            question_num: Question number for context

        Returns:
            List of 3 distractor strings
        """
        prompt = f"""You are a mathematics education expert creating plausible wrong answers (distractors) for 11+ entrance exam questions targeted at Year 5-7 students (ages 10-12).

CORRECT ANSWER: {correct_answer}
ANSWER TYPE: {answer_type}
CONTEXT: 11+ Maths Test {test_num}, Question {question_num}

Generate exactly 3 WRONG answers that:
1. Are plausible mistakes a student might make
2. Are similar in format to the correct answer (same units, similar structure)
3. Reflect common misconceptions or calculation errors
4. Are clearly distinct from each other AND from the correct answer

IMPORTANT RULES:
- For numbers: Use common calculation errors (off by 1, 10, or small amounts; wrong operation; decimal point errors)
- For fractions: Use inverted fractions, wrong simplification, or close fractions
- For decimals: Use decimal point shifts, rounding errors, or missing digits
- For ratios: Swap values or use similar but incorrect ratios
- For percentages: Use common mistakes like forgetting to multiply by 100, or confusing % with decimals
- For degrees/angles: Use complementary/supplementary angle errors, or close values
- For measurements: Use unit conversion errors or close values
- For shapes: Use shapes with similar properties but different names
- For time: Use am/pm confusion, close times, or time calculation errors
- For money: Use close amounts, decimal errors, or common pricing mistakes
- For text/words: Use similar but incorrect terms, related words, or common confusions
- For equations: Use similar variable assignments with different values
- For compound answers: Keep the same format but change the numbers

OUTPUT FORMAT:
Return ONLY 3 distractors, one per line, with no explanations, numbering, or extra text.
Each distractor should match the exact format of the correct answer.

Example for "120":
110
130
102

Example for "1/4":
1/2
3/4
1/3

Example for "Thursday":
Wednesday
Friday
Tuesday
"""

        try:
            response = self.client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": "You are a mathematics education expert. Return only the requested distractors, no explanations."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=150
            )

            # Parse response
            content = response.choices[0].message.content.strip()
            distractors = [line.strip() for line in content.split('\n') if line.strip()]

            # Ensure exactly 3 distractors
            if len(distractors) >= 3:
                distractors = distractors[:3]
            else:
                logger.warning(f"AI returned {len(distractors)} distractors, expected 3")
                # Pad with variations if needed
                while len(distractors) < 3:
                    distractors.append(f"{correct_answer}?")

            # Remove any that match the correct answer
            distractors = [d for d in distractors if d.lower().strip() != correct_answer.lower().strip()]

            # If we removed any, regenerate or add placeholder
            while len(distractors) < 3:
                distractors.append(f"Option {len(distractors) + 2}")

            return distractors[:3]

        except Exception as e:
            logger.error(f"Error calling OpenAI API: {e}")
            # Return fallback distractors
            return [f"Option A", f"Option B", f"Option C"]

    def generate_distractors(self, correct_answer: str, test_num: int,
                            question_num: int, force_regenerate: bool = False) -> List[str]:
        """
        Generate 3 plausible wrong answers for a question.

        Args:
            correct_answer: The correct answer string
            test_num: Test number (1-40)
            question_num: Question number within test (1-15)
            force_regenerate: If True, bypass cache and regenerate

        Returns:
            List of 3 distractor strings
        """
        cache_key = self._get_cache_key(test_num, question_num)

        # Check cache first (unless force_regenerate)
        if not force_regenerate and cache_key in self.cache:
            cached = self.cache[cache_key]
            if cached.get('correct_answer') == correct_answer:
                logger.info(f"Using cached distractors for Test {test_num} Q{question_num}")
                return cached['distractors']

        # Classify answer type
        answer_type = self.classify_answer(correct_answer)
        logger.info(f"Test {test_num} Q{question_num}: '{correct_answer}' classified as {answer_type}")

        # Generate distractors based on type
        if answer_type == AnswerType.LETTER:
            distractors = self._generate_letter_distractors(correct_answer)
        elif answer_type == AnswerType.YES_NO:
            distractors = self._generate_yes_no_distractors(correct_answer)
        elif answer_type == AnswerType.COMPASS:
            distractors = self._generate_compass_distractors(correct_answer)
        else:
            # Use AI for complex types
            distractors = self._generate_with_ai(correct_answer, answer_type, test_num, question_num)

        # Cache the result
        self.cache[cache_key] = {
            'correct_answer': correct_answer,
            'answer_type': answer_type,
            'distractors': distractors
        }
        self._save_cache()

        return distractors

    def generate_all_distractors(self, answer_keys: Dict[int, Dict[int, str]],
                                 force_regenerate: bool = False) -> Dict[int, Dict[int, List[str]]]:
        """
        Generate distractors for all questions in all tests.

        Args:
            answer_keys: Dictionary mapping test_num -> {question_num -> correct_answer}
            force_regenerate: If True, bypass cache and regenerate all

        Returns:
            Dictionary mapping test_num -> {question_num -> [distractors]}
        """
        all_distractors = {}

        for test_num, questions in answer_keys.items():
            all_distractors[test_num] = {}
            for q_num, correct_answer in questions.items():
                distractors = self.generate_distractors(
                    correct_answer=correct_answer,
                    test_num=test_num,
                    question_num=q_num,
                    force_regenerate=force_regenerate
                )
                all_distractors[test_num][q_num] = distractors
                logger.info(f"Test {test_num} Q{q_num}: {correct_answer} -> {distractors}")

        return all_distractors

    def get_shuffled_options(self, correct_answer: str, distractors: List[str]) -> Tuple[List[str], int]:
        """
        Combine correct answer with distractors and shuffle.

        Args:
            correct_answer: The correct answer
            distractors: List of 3 distractors

        Returns:
            Tuple of (shuffled options list, correct answer index)
        """
        options = [correct_answer] + distractors
        random.shuffle(options)
        correct_index = options.index(correct_answer)
        return options, correct_index


# CLI for testing
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Test distractor generation")
    parser.add_argument("--answer", type=str, help="Test with a specific answer")
    parser.add_argument("--test", type=int, default=1, help="Test number")
    parser.add_argument("--question", type=int, default=1, help="Question number")
    args = parser.parse_args()

    generator = DistractorGenerator()

    if args.answer:
        # Test with provided answer
        answer_type = generator.classify_answer(args.answer)
        print(f"Answer: {args.answer}")
        print(f"Type: {answer_type}")

        distractors = generator.generate_distractors(
            args.answer, args.test, args.question
        )
        print(f"Distractors: {distractors}")

        options, correct_idx = generator.get_shuffled_options(args.answer, distractors)
        print(f"Shuffled options: {options}")
        print(f"Correct index: {correct_idx}")
    else:
        # Test with sample answers
        test_answers = [
            "120",           # integer
            "0.3",           # decimal
            "1/4",           # fraction
            "1 3/4",         # mixed fraction
            "13, 17",        # multiple values
            "d",             # letter
            "yes",           # yes/no
            "Thursday",      # text word
            "4:3",           # ratio
            "8.29am",        # time
            "£9.50",         # money
            "south-east",    # compass
            "45%",           # percentage
            "90°",           # degree
            "7.5cm",         # measurement
            "A = 10, B = 12" # equation
        ]

        print("Testing answer classification and distractor generation:\n")
        for i, answer in enumerate(test_answers, 1):
            answer_type = generator.classify_answer(answer)
            distractors = generator.generate_distractors(answer, 1, i)
            print(f"{answer:20} -> {answer_type:20} -> {distractors}")
