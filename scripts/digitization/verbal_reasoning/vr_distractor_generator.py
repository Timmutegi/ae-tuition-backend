#!/usr/bin/env python3
"""
Distractor Generator for Verbal Reasoning MCQ Tests (Q21-25)

Uses OpenAI GPT-4 to generate plausible wrong answers (distractors) for
synonym/antonym completion questions in 11+ Verbal Reasoning tests.

Usage:
    from vr_distractor_generator import VRDistractorGenerator

    generator = VRDistractorGenerator()
    distractors = generator.generate_distractors(
        given_word="smart",
        correct_answer="intelligent",
        question_type="synonym",  # or "antonym"
        test_num=1,
        question_num=21
    )
"""

import os
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
CACHE_FILE = SCRIPT_DIR / "vr_distractor_cache.json"


class VRDistractorGenerator:
    """
    Generates plausible wrong answers (distractors) for VR synonym/antonym MCQ questions.

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

    def _get_cache_key(self, test_num: int, question_num: int, letter_template: Optional[str] = None) -> str:
        """Generate cache key for a question."""
        base_key = f"vr_test_{test_num}_q_{question_num}"
        if letter_template:
            # Include template in key for Q11-20 letter-based questions
            base_key += f"_tpl_{letter_template}"
        return base_key

    def _generate_with_ai(self, given_word: str, correct_answer: str,
                         question_type: str, test_num: int, question_num: int,
                         letter_template: Optional[str] = None) -> List[str]:
        """
        Generate distractors using GPT-4.

        Args:
            given_word: The word given in the question (e.g., "smart")
            correct_answer: The correct answer (e.g., "intelligent")
            question_type: Either "synonym" or "antonym"
            test_num: Test number for context
            question_num: Question number for context
            letter_template: Optional template pattern (e.g., "a_a_h_tic") for Q11-20

        Returns:
            List of 3 distractor strings
        """
        relationship = "the same as" if question_type == "synonym" else "the opposite of"

        # Add template context if provided (for Q11-20 letter-based questions)
        template_context = ""
        if letter_template:
            template_context = f"""
IMPORTANT CONTEXT:
The question shows a letter template hint: "{letter_template}"
The correct answer "{correct_answer}" fits this template pattern.
Generate distractors that:
- Could be plausible guesses when students see the template
- Are similar in structure/length to the correct answer
- Would be common mistakes for students trying to decode the pattern
"""

        prompt = f"""You are an English language education expert creating plausible wrong answers (distractors) for 11+ entrance exam questions targeted at Year 5-7 students (ages 10-12).

QUESTION TYPE: Find a word meaning {relationship} the given word
GIVEN WORD: {given_word}
CORRECT ANSWER: {correct_answer}
CONTEXT: 11+ Verbal Reasoning Test {test_num}, Question {question_num}
{template_context}

Generate exactly 3 WRONG answers that:
1. Are plausible words a student might confuse with the correct answer
2. Are similar in length to the correct answer (within 2-3 letters)
3. Are real English words that a Year 5-7 student would know
4. Are clearly distinct from the correct answer
5. Could be mistaken for {"synonyms" if question_type == "synonym" else "antonyms"} of "{given_word}" but are NOT correct

IMPORTANT RULES:
- DO NOT include the correct answer "{correct_answer}"
- Choose words that are related but not correct (similar meaning, same category, common confusions)
- For synonyms: use words with slightly different meanings, or words that look/sound similar
- For antonyms: use words that are related but not true opposites
- Make distractors realistic - words that might appear in similar contexts
- Avoid very obscure words that Year 5-7 students wouldn't know

EXAMPLE for "smart" -> "intelligent" (synonym):
clever (too similar to correct - avoid if correct is "intelligent")
brilliant
wise

EXAMPLE for "happy" -> "sad" (antonym):
angry
upset
gloomy

OUTPUT FORMAT:
Return ONLY 3 distractors, one per line, with no explanations, numbering, or extra text.
Each distractor should be a single word in lowercase.
"""

        try:
            response = self.client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": "You are an English language expert. Return only the requested distractors, no explanations."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=100
            )

            # Parse response
            content = response.choices[0].message.content.strip()
            distractors = [line.strip().lower() for line in content.split('\n') if line.strip()]

            # Ensure exactly 3 distractors
            if len(distractors) >= 3:
                distractors = distractors[:3]
            else:
                logger.warning(f"AI returned {len(distractors)} distractors, expected 3")
                # Pad with variations if needed
                while len(distractors) < 3:
                    distractors.append(f"word{len(distractors) + 1}")

            # Remove any that match the correct answer
            correct_lower = correct_answer.lower().strip()
            distractors = [d for d in distractors if d.lower().strip() != correct_lower]

            # If we removed any, regenerate or add placeholder
            while len(distractors) < 3:
                distractors.append(f"option{len(distractors) + 1}")

            return distractors[:3]

        except Exception as e:
            logger.error(f"Error calling OpenAI API: {e}")
            # Return fallback distractors
            return ["option1", "option2", "option3"]

    def generate_distractors(self, given_word: str, correct_answer: str,
                            question_type: str, test_num: int,
                            question_num: int, letter_template: Optional[str] = None,
                            force_regenerate: bool = False) -> List[str]:
        """
        Generate 3 plausible wrong answers for a synonym/antonym question.

        Args:
            given_word: The word given in the question (e.g., "smart")
            correct_answer: The correct answer string (e.g., "intelligent")
            question_type: "synonym" or "antonym"
            test_num: Test number (1-20)
            question_num: Question number within test (11-25)
            letter_template: Optional template pattern for Q11-20 (e.g., "a_a_h_tic")
            force_regenerate: If True, bypass cache and regenerate

        Returns:
            List of 3 distractor strings
        """
        cache_key = self._get_cache_key(test_num, question_num, letter_template)

        # Check cache first (unless force_regenerate)
        if not force_regenerate and cache_key in self.cache:
            cached = self.cache[cache_key]
            if cached.get('correct_answer') == correct_answer:
                logger.info(f"Using cached distractors for Test {test_num} Q{question_num}")
                return cached['distractors']

        template_info = f" [template: {letter_template}]" if letter_template else ""
        logger.info(f"Generating distractors for Test {test_num} Q{question_num}: '{given_word}' -> '{correct_answer}' ({question_type}){template_info}")

        # Generate distractors using AI
        distractors = self._generate_with_ai(
            given_word, correct_answer, question_type, test_num, question_num, letter_template
        )

        # Cache the result
        self.cache[cache_key] = {
            'given_word': given_word,
            'correct_answer': correct_answer,
            'question_type': question_type,
            'letter_template': letter_template,
            'distractors': distractors
        }
        self._save_cache()

        return distractors

    def get_shuffled_options(self, correct_answer: str, distractors: List[str]) -> Tuple[List[Dict], int]:
        """
        Combine correct answer with distractors and shuffle, returning answer_options format.

        Args:
            correct_answer: The correct answer
            distractors: List of 3 distractors

        Returns:
            Tuple of (answer_options list, correct answer index)
        """
        all_options = [correct_answer] + distractors
        random.shuffle(all_options)
        correct_index = all_options.index(correct_answer)

        answer_options = []
        for i, option in enumerate(all_options):
            answer_options.append({
                "option_text": option,
                "is_correct": option == correct_answer,
                "order_number": i + 1
            })

        return answer_options, correct_index


# CLI for testing
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Test VR distractor generation")
    parser.add_argument("--given", type=str, help="Given word (e.g., 'smart')")
    parser.add_argument("--answer", type=str, help="Correct answer (e.g., 'intelligent')")
    parser.add_argument("--type", type=str, default="synonym", choices=["synonym", "antonym"],
                       help="Question type")
    parser.add_argument("--test", type=int, default=1, help="Test number")
    parser.add_argument("--question", type=int, default=21, help="Question number")
    args = parser.parse_args()

    generator = VRDistractorGenerator()

    if args.given and args.answer:
        # Test with provided word pair
        distractors = generator.generate_distractors(
            given_word=args.given,
            correct_answer=args.answer,
            question_type=args.type,
            test_num=args.test,
            question_num=args.question
        )
        print(f"Given word: {args.given}")
        print(f"Correct answer: {args.answer}")
        print(f"Question type: {args.type}")
        print(f"Distractors: {distractors}")

        options, correct_idx = generator.get_shuffled_options(args.answer, distractors)
        print(f"Answer options: {[o['option_text'] for o in options]}")
        print(f"Correct index: {correct_idx}")
    else:
        # Test with sample word pairs
        test_pairs = [
            ("smart", "intelligent", "synonym"),
            ("exact", "accurate", "synonym"),
            ("happy", "sad", "antonym"),
            ("friend", "foe", "antonym"),
            ("wrong", "incorrect", "synonym"),
            ("level", "balanced", "synonym"),
        ]

        print("Testing VR distractor generation:\n")
        for i, (given, answer, q_type) in enumerate(test_pairs, 21):
            distractors = generator.generate_distractors(
                given_word=given,
                correct_answer=answer,
                question_type=q_type,
                test_num=1,
                question_num=i
            )
            print(f"{given:15} -> {answer:15} ({q_type:8}) -> {distractors}")
