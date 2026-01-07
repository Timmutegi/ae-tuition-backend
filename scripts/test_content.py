"""
Comprehensive test content for 11+ Verbal Reasoning Year 5-7 CEM Style Testbook 1

This file contains:
- Passage text for each test (Q1-10 reading comprehension)
- Question text and answer options for multiple choice questions (Q1-10)
- Cloze passage text with blanks for Q11-20
- Synonym/antonym word pairs for Q21-25

Structure:
- TEST_CONTENT[test_num] contains all content for that test
- Each test has: passage, questions (1-10), cloze_passage (11-20), synonyms (21-25)
"""

# Test content extracted from testbook images
# Each test has the following structure:
# {
#     "passage": {
#         "title": "Title of the passage",
#         "text": "Full passage text...",
#         "source": "Source attribution",
#         "glossary": {"term": "definition", ...}
#     },
#     "questions": {
#         1: {
#             "text": "Question text?",
#             "options": {
#                 "a": "Option A text",
#                 "b": "Option B text",
#                 "c": "Option C text",
#                 "d": "Option D text"
#             }
#         },
#         ...
#     },
#     "cloze": {
#         "passage_text": "Cloze passage with {11} blanks...",
#         "blanks": {
#             11: ["option1", "option2", "option3"],
#             12: ["option1", "option2", "option3"],
#             ...
#         }
#     },
#     "synonyms": {
#         21: {"given": "smart", "answer": "intelligent", "template": "_n t _ l _ g e _ t"},
#         ...
#     }
# }

TEST_CONTENT = {
    1: {
        "passage": {
            "title": "Five Children and It",
            "text": """Five siblings moved to the country from London. While playing in a gravel pit they discovered a grumpy sand-fairy, who had the ability to grant one shared wish each day, which would expire at sunset. Their first wish was to be beautiful. The next day:

Anthea woke in the morning from a very real sort of dream, in which she was walking in the Zoological Gardens on a pouring wet day without an umbrella. The animals seemed desperately unhappy because of the rain, and were all growling gloomily. When she awoke, both the growling and the rain went on just the same. The growling was the heavy regular breathing of her sister Jane, who had a slight cold and was still asleep. The rain fell in slow drops on to Anthea's face from the wet corner of a bath-towel out of which her brother Robert was gently squeezing the water, to wake her up, as he now explained.

"Oh, drop it!" she said rather crossly; so he did, for he was not a brutal brother, though very ingenious in apple-pie beds, booby-traps, original methods of waking sleeping relatives, and the other little accomplishments which made home happy.

"I had such a funny dream," Anthea began.

"So did I," said Jane, waking suddenly and without warning. "I dreamed we found a Sand-fairy in the gravel-pits, and it said it was a nymph, and we might have a new wish every day, and"—

"But that's what I dreamed," said Robert; "I was just going to tell you,— and we had the first wish directly it said so. And I dreamed you girls were donkeys enough to ask for us all to be beautiful as day, and we jolly well were, and it was perfectly beastly."

An adapted extract from Five Children and It by Edith Nesbit (1858-1924).""",
            "source": "An adapted extract from Five Children and It by Edith Nesbit (1858-1924).",
            "glossary": {
                "Apple-pie beds": "the sheets in a bed have been folded in such a way that a person cannot stretch their legs out"
            }
        },
        "questions": {
            1: {
                "text": "How are Jane and Robert related to each other?",
                "options": {
                    "a": "They are cousins",
                    "b": "They are brother and sister",
                    "c": "They are not related",
                    "d": "They are friends"
                }
            },
            2: {
                "text": "What was the growling noise that Anthea could hear?",
                "options": {
                    "a": "Her sister breathing",
                    "b": "The animals making noise",
                    "c": "Her brother trying to wake her",
                    "d": "She was snoring"
                }
            },
            3: {
                "text": "What location did Jane dream about?",
                "options": {
                    "a": "The Zoological Gardens",
                    "b": "Their house in the country",
                    "c": "London",
                    "d": "The gravel-pits"
                }
            },
            4: {
                "text": "What does ingenious (line 10) mean in this context?",
                "options": {
                    "a": "Foolish",
                    "b": "Intrusive",
                    "c": "Inventive",
                    "d": "Silly"
                }
            },
            5: {
                "text": "Which of the siblings was unwell?",
                "options": {
                    "a": "Anthea",
                    "b": "Robert",
                    "c": "Jane",
                    "d": "None of them"
                }
            },
            6: {
                "text": "What sort of character lived in the gravel-pits?",
                "options": {
                    "a": "A donkey",
                    "b": "A magical creature",
                    "c": "A beast",
                    "d": "A newt"
                }
            },
            7: {
                "text": "Why had the children all had the same dream?",
                "options": {
                    "a": "They had imagined a Sand-fairy had cast a spell on them.",
                    "b": "They were all told the same bedtime story.",
                    "c": "They were not fully asleep.",
                    "d": "In their dreams they were remembering the previous day."
                }
            },
            8: {
                "text": "How do you think Anthea felt when she awoke?",
                "options": {
                    "a": "Weary",
                    "b": "Collected",
                    "c": "Refreshed",
                    "d": "Irritated"
                }
            },
            9: {
                "text": "What was Robert's opinion of his sisters' choice of wish?",
                "options": {
                    "a": "Robert was delighted with their choice.",
                    "b": "Robert was upset and thought it was a silly idea.",
                    "c": "Robert wanted to make everybody ugly.",
                    "d": "Robert was pleased with the outcome of the wish."
                }
            },
            10: {
                "text": "Robert is described as 'not a brutal brother' (lines 9-10), what does this suggest about his character?",
                "options": {
                    "a": "He liked to be mean to his sisters.",
                    "b": "He was just a nasty prankster.",
                    "c": "His practical jokes were not intended to be harmful.",
                    "d": "Robert and his sister were not friendly towards each other."
                }
            }
        },
        "cloze": {
            "passage_text": """There are ____11____ 1,240 species of bat across the world. Bats are the only mammals that can truly fly, rather than just ____12____. About 70% of bats ____13____ insects, the remainder consist of fruit-eating bats; nectar-eating bats; carnivorous bats that ____14____ on small mammals, birds, lizards and frogs; fish-eating bats, and the famous blood-sucking vampire bats of South America. Bats have ____15____ very ____16____ hearing. They ____17____ rapid high-pitched squeaks that ____18____ off of objects in their ____19____, echoing back to the bats. From these echoes, the bats can ____20____ the size of objects and how far away they are.""",
            "blanks": {
                11: ["roughly", "roguishly", "roundly"],
                12: ["diving", "gliding", "fleeting"],
                13: ["consume", "ate", "inhale"],
                14: ["pry", "prey", "pray"],
                15: ["evolve", "developed", "produced"],
                16: ["nimble", "precision", "sensitive"],
                17: ["omit", "emit", "remit"],
                18: ["shock", "contact", "bounce"],
                19: ["path", "track", "lane"],
                20: ["shape", "determine", "disprove"]
            }
        },
        "synonyms": {
            21: {"given": "smart", "answer": "intelligent"},
            22: {"given": "exact", "answer": "accurate"},
            23: {"given": "sterile", "answer": "clean"},
            24: {"given": "wrong", "answer": "incorrect"},
            25: {"given": "level", "answer": "balanced"}
        }
    },

    # Test 2-20 content will be added here
    # For now, these use placeholder structure that falls back to image-based questions

    2: {
        "passage": {
            "title": "Robin Hood",
            "text": None,  # Will use image
            "source": None,
            "glossary": {}
        },
        "questions": {},  # Will use image-based
        "cloze": {"passage_text": None, "blanks": {}},
        "synonyms": {}
    },

    3: {
        "passage": {
            "title": "A Christmas Carol",
            "text": None,
            "source": None,
            "glossary": {}
        },
        "questions": {},
        "cloze": {"passage_text": None, "blanks": {}},
        "synonyms": {}
    },

    4: {
        "passage": {
            "title": "Abraham Lincoln",
            "text": None,
            "source": None,
            "glossary": {}
        },
        "questions": {},
        "cloze": {"passage_text": None, "blanks": {}},
        "synonyms": {}
    },

    5: {
        "passage": {
            "title": "Tom Sawyer",
            "text": None,
            "source": None,
            "glossary": {}
        },
        "questions": {},
        "cloze": {"passage_text": None, "blanks": {}},
        "synonyms": {}
    },

    6: {
        "passage": {
            "title": "Titanic Disaster",
            "text": None,
            "source": None,
            "glossary": {}
        },
        "questions": {},
        "cloze": {"passage_text": None, "blanks": {}},
        "synonyms": {}
    },

    7: {
        "passage": {
            "title": "The Shepherd Boy",
            "text": None,
            "source": None,
            "glossary": {}
        },
        "questions": {},
        "cloze": {"passage_text": None, "blanks": {}},
        "synonyms": {}
    },

    8: {
        "passage": {
            "title": "Saint Valentine's Day",
            "text": None,
            "source": None,
            "glossary": {}
        },
        "questions": {},
        "cloze": {"passage_text": None, "blanks": {}},
        "synonyms": {}
    },

    9: {
        "passage": {
            "title": "Scrooge",
            "text": None,
            "source": None,
            "glossary": {}
        },
        "questions": {},
        "cloze": {"passage_text": None, "blanks": {}},
        "synonyms": {}
    },

    10: {
        "passage": {
            "title": "Anne Frank",
            "text": None,
            "source": None,
            "glossary": {}
        },
        "questions": {},
        "cloze": {"passage_text": None, "blanks": {}},
        "synonyms": {}
    },

    11: {
        "passage": {
            "title": "The Nile River",
            "text": None,
            "source": None,
            "glossary": {}
        },
        "questions": {},
        "cloze": {"passage_text": None, "blanks": {}},
        "synonyms": {}
    },

    12: {
        "passage": {
            "title": "T-Rex",
            "text": None,
            "source": None,
            "glossary": {}
        },
        "questions": {},
        "cloze": {"passage_text": None, "blanks": {}},
        "synonyms": {}
    },

    13: {
        "passage": {
            "title": "Alexei Nikolaevich",
            "text": None,
            "source": None,
            "glossary": {}
        },
        "questions": {},
        "cloze": {"passage_text": None, "blanks": {}},
        "synonyms": {}
    },

    14: {
        "passage": {
            "title": "The Benevolent Goblin",
            "text": None,
            "source": None,
            "glossary": {}
        },
        "questions": {},
        "cloze": {"passage_text": None, "blanks": {}},
        "synonyms": {}
    },

    15: {
        "passage": {
            "title": "Mowgli",
            "text": None,
            "source": None,
            "glossary": {}
        },
        "questions": {},
        "cloze": {"passage_text": None, "blanks": {}},
        "synonyms": {}
    },

    16: {
        "passage": {
            "title": "Sir Francis Drake",
            "text": None,
            "source": None,
            "glossary": {}
        },
        "questions": {},
        "cloze": {"passage_text": None, "blanks": {}},
        "synonyms": {}
    },

    17: {
        "passage": {
            "title": "The Piano",
            "text": None,
            "source": None,
            "glossary": {}
        },
        "questions": {},
        "cloze": {"passage_text": None, "blanks": {}},
        "synonyms": {}
    },

    18: {
        "passage": {
            "title": "Shirley Temple",
            "text": None,
            "source": None,
            "glossary": {}
        },
        "questions": {},
        "cloze": {"passage_text": None, "blanks": {}},
        "synonyms": {}
    },

    19: {
        "passage": {
            "title": "The Internet",
            "text": None,
            "source": None,
            "glossary": {}
        },
        "questions": {},
        "cloze": {"passage_text": None, "blanks": {}},
        "synonyms": {}
    },

    20: {
        "passage": {
            "title": "The Children of the New Forest",
            "text": None,
            "source": None,
            "glossary": {}
        },
        "questions": {},
        "cloze": {"passage_text": None, "blanks": {}},
        "synonyms": {}
    }
}


def has_extracted_content(test_num: int) -> bool:
    """Check if a test has extracted text content (not just images)"""
    content = TEST_CONTENT.get(test_num, {})
    passage = content.get("passage", {})
    questions = content.get("questions", {})

    # Check if passage text exists and questions are defined
    return passage.get("text") is not None and len(questions) > 0


def get_passage(test_num: int) -> dict:
    """Get passage data for a test"""
    return TEST_CONTENT.get(test_num, {}).get("passage", {})


def get_question(test_num: int, q_num: int) -> dict:
    """Get question data for a specific question"""
    return TEST_CONTENT.get(test_num, {}).get("questions", {}).get(q_num, {})


def get_cloze_data(test_num: int) -> dict:
    """Get cloze passage data for a test"""
    return TEST_CONTENT.get(test_num, {}).get("cloze", {})


def get_synonym_data(test_num: int, q_num: int) -> dict:
    """Get synonym data for a specific question"""
    return TEST_CONTENT.get(test_num, {}).get("synonyms", {}).get(q_num, {})
