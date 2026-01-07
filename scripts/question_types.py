"""
Question type mappings for 11+ Verbal Reasoning Year 5-7 CEM Style Testbook 1

This file defines the question format types for each test's Q11-25 sections.
Different tests use different formats:
- CLOZE_PASSAGE: Fill in blanks in a passage with word options
- ODD_ONE_OUT: Find the word that doesn't belong in a group
- SENTENCE_REARRANGE: Find the word that doesn't fit in a jumbled sentence
- LETTER_COMPLETION_CLOZE: Fill in missing letters in words within a passage
- ANTONYM_LETTER: Complete word boxes to form antonym
- SYNONYM_LETTER: Complete word boxes to form synonym
- ANTONYM_SELECT: Select antonym from multiple choices
- SYNONYM_SELECT: Select synonym from multiple choices
- LETTER_WORD_MATCH: Match letters to words in a grid
"""

# Question format types for Q11-20 section
Q11_20_TYPES = {
    1: "CLOZE_PASSAGE",           # Fill in blanks with word options
    2: "ODD_ONE_OUT",             # Find word that doesn't belong + sentence rearrange
    3: "LETTER_COMPLETION_CLOZE", # Fill in missing letters in passage
    4: "ANTONYM_LETTER",          # Complete antonym with letter boxes
    5: "LETTER_WORD_MATCH",       # Match letters to words
    6: "ODD_ONE_OUT",             # Find word that doesn't belong
    7: "LETTER_COMPLETION_CLOZE", # Fill in missing letters
    8: "ODD_ONE_OUT",             # Find word that doesn't belong
    9: "LETTER_COMPLETION_CLOZE", # Fill in missing letters
    10: "ANTONYM_LETTER",         # Complete antonym with letter boxes
    11: "LETTER_WORD_MATCH",      # Match letters to words
    12: "ANTONYM_LETTER",         # Complete antonym with letter boxes
    13: "LETTER_COMPLETION_CLOZE", # Fill in missing letters
    14: "ODD_ONE_OUT",            # Find word that doesn't belong
    15: "LETTER_COMPLETION_CLOZE", # Fill in missing letters
    16: "ANTONYM_LETTER",         # Complete antonym with letter boxes
    17: "LETTER_WORD_MATCH",      # Match letters to words
    18: "ANTONYM_LETTER",         # Complete antonym with letter boxes
    19: "LETTER_COMPLETION_CLOZE", # Fill in missing letters
    20: "ANTONYM_LETTER",         # Complete antonym with letter boxes
}

# Question format types for Q21-25 section
Q21_25_TYPES = {
    1: "SYNONYM_LETTER",    # Complete synonym with letter boxes
    2: "ANTONYM_SELECTION",    # Select antonym from choices (matches API enum)
    3: "SYNONYM_SELECTION",    # Select synonym from choices (matches API enum)
    4: "SYNONYM_LETTER",    # Complete synonym with letter boxes
    5: "LETTER_WORD_MATCH", # Fill in missing words (simple)
    6: "SYNONYM_LETTER",    # Complete synonym with letter boxes
    7: "SYNONYM_LETTER",    # Complete synonym with letter boxes
    8: "SYNONYM_LETTER",    # Complete synonym with letter boxes
    9: "LETTER_WORD_MATCH", # Fill in missing words
    10: "SYNONYM_LETTER",   # Complete synonym with letter boxes
    11: "LETTER_WORD_MATCH",# Fill in missing words
    12: "SYNONYM_LETTER",   # Complete synonym with letter boxes
    13: "SYNONYM_LETTER",   # Complete synonym with letter boxes
    14: "SYNONYM_LETTER",   # Complete synonym with letter boxes
    15: "LETTER_WORD_MATCH",# Fill in missing words
    16: "SYNONYM_LETTER",   # Complete synonym with letter boxes
    17: "LETTER_WORD_MATCH",# Fill in missing words
    18: "ODD_ONE_OUT",      # Find word that doesn't belong (homographs)
    19: "SYNONYM_LETTER",   # Complete synonym with letter boxes
    20: "SYNONYM_LETTER",   # Complete synonym with letter boxes
}

# Whether Q11-20 can be text-based (vs requiring image)
Q11_20_TEXT_CAPABLE = {
    "CLOZE_PASSAGE": True,         # Can show passage with blanks and options
    "ODD_ONE_OUT": True,           # Can list words and ask which doesn't belong
    "SENTENCE_REARRANGE": True,    # Can list words and ask which doesn't fit
    "LETTER_COMPLETION_CLOZE": False,  # Requires letter boxes (visual)
    "ANTONYM_LETTER": False,       # Requires letter boxes (visual)
    "LETTER_WORD_MATCH": False,    # Requires grid layout (visual)
}

# Whether Q21-25 can be text-based
Q21_25_TEXT_CAPABLE = {
    "SYNONYM_LETTER": False,   # Requires letter boxes (visual)
    "ANTONYM_SELECTION": True,    # Can show word and options (matches API enum)
    "SYNONYM_SELECTION": True,    # Can show word and options (matches API enum)
    "LETTER_WORD_MATCH": False,# Requires specific format
    "ODD_ONE_OUT": True,       # Can list words
}


def get_q11_20_type(test_num: int) -> str:
    """Get the question format type for Q11-20 section of a test"""
    return Q11_20_TYPES.get(test_num, "LETTER_COMPLETION_CLOZE")


def get_q21_25_type(test_num: int) -> str:
    """Get the question format type for Q21-25 section of a test"""
    return Q21_25_TYPES.get(test_num, "SYNONYM_LETTER")


def is_q11_20_text_capable(test_num: int) -> bool:
    """Check if Q11-20 can be rendered as text"""
    q_type = get_q11_20_type(test_num)
    return Q11_20_TEXT_CAPABLE.get(q_type, False)


def is_q21_25_text_capable(test_num: int) -> bool:
    """Check if Q21-25 can be rendered as text"""
    q_type = get_q21_25_type(test_num)
    return Q21_25_TEXT_CAPABLE.get(q_type, False)


# Instructions for each question type
QUESTION_INSTRUCTIONS = {
    "CLOZE_PASSAGE": "Select the correct word to complete each blank in the passage.",
    "ODD_ONE_OUT": "Four of the words in each list are linked. Select the word that is NOT related to the others.",
    "SENTENCE_REARRANGE": "Rearrange the words to make a sentence. Select the word which does NOT fit into the sentence.",
    "LETTER_COMPLETION_CLOZE": "Fill in the missing letters to complete each word in the passage.",
    "ANTONYM_LETTER": "Complete the word on the right so that it means the opposite of the word on the left.",
    "SYNONYM_LETTER": "Complete the word on the right so that it means the same as the word on the left.",
    "ANTONYM_SELECTION": "Choose the word that means the opposite of the word on the left.",
    "SYNONYM_SELECTION": "Choose the word that means the same as the word on the left.",
    "LETTER_WORD_MATCH": "Match each letter to the correct word to complete the passage.",
}


def get_instruction(q_type: str) -> str:
    """Get instruction text for a question type"""
    return QUESTION_INSTRUCTIONS.get(q_type, "Answer the question.")
