"""Detect repeated questions by exact text or heavy word overlap."""

from collections.abc import Sequence
from dataclasses import dataclass

from contracts import Question, normalize

from engine.text import sanitize_question

REPEAT_THRESHOLD = 0.6
MIN_CONTENT_TOKENS = 3

EXACT_REPEAT = "repeat_exact"
OVERLAP_REPEAT = "repeat_overlap"

NEGATIONS = frozenset({"not", "no", "never", "without", "except", "neither", "nor"})

# Separate from contracts.skills.STOPWORDS: that set is too short for question text.
# Negations (not, no, never, without, except, neither, nor) are deliberately absent
# so that a question meaning the opposite never looks like a repeat of its pair.
REPEAT_STOPWORDS = frozenset(
    {
        # Question words.
        "what",
        "how",
        "why",
        "when",
        "where",
        "which",
        "who",
        "whom",
        "whose",
        # Auxiliaries and modals.
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "am",
        "do",
        "does",
        "did",
        "doing",
        "done",
        "have",
        "has",
        "had",
        "having",
        "can",
        "could",
        "will",
        "would",
        "shall",
        "should",
        "may",
        "might",
        "must",
        # Articles, conjunctions, prepositions.
        "a",
        "an",
        "the",
        "and",
        "or",
        "but",
        "so",
        "if",
        "then",
        "than",
        "as",
        "of",
        "for",
        "with",
        "by",
        "from",
        "to",
        "in",
        "on",
        "at",
        "into",
        "onto",
        "about",
        "over",
        "under",
        "between",
        "through",
        "during",
        "before",
        "after",
        "above",
        "below",
        "up",
        "down",
        "out",
        "off",
        # Pronouns and demonstratives.
        "i",
        "you",
        "he",
        "she",
        "it",
        "we",
        "they",
        "me",
        "him",
        "her",
        "us",
        "them",
        "my",
        "your",
        "his",
        "its",
        "our",
        "their",
        "mine",
        "yours",
        "hers",
        "ours",
        "theirs",
        "this",
        "that",
        "these",
        "those",
        "there",
        "here",
        # Question verbs and filler.
        "explain",
        "describe",
        "define",
        "tell",
        "discuss",
        "give",
        "provide",
        "list",
        "name",
        "walk",
        "compare",
        "contrast",
        "outline",
        "summarize",
        "summarise",
        "please",
        "briefly",
    }
)


@dataclass(frozen=True)
class RepeatMatch:
    """An earlier question that the new text repeats, and how it repeats it."""

    kind: str
    """`EXACT_REPEAT` after normalization, or `OVERLAP_REPEAT` by word overlap."""

    earlier_question: str
    """The earlier question text, quoted only to tell the model what to avoid."""


def content_tokens(text: str) -> tuple[str, ...]:
    """The meaningful words of a question: normalized, without the question stopwords."""
    return tuple(token for token in normalize(text).split() if token not in REPEAT_STOPWORDS)


def _overlap(first: Sequence[str], second: Sequence[str]) -> float:
    """Jaccard similarity: shared words divided by all words in either question."""
    first_words, second_words = set(first), set(second)
    return len(first_words & second_words) / len(first_words | second_words)


def _has_negation(tokens: Sequence[str]) -> bool:
    """True when a question contains one of the words that reverse its meaning."""
    return any(token in NEGATIONS for token in tokens)


def find_repeat(
    text: str, earlier_questions: Sequence[Question], *, skill_id: str
) -> RepeatMatch | None:
    """Find the first earlier question this text repeats, exactly or by overlap.

    Exact matching covers every earlier question, whatever its skill. Word overlap
    is scoped to the same skill, because similar wording about another skill is a
    different question. Overlap is skipped when either question has fewer than
    three content words, and when only one of the two is negated.
    """
    sanitized_text = sanitize_question(text)
    normalized_text = normalize(sanitized_text)
    for earlier in earlier_questions:
        if normalize(sanitize_question(earlier.text)) == normalized_text:
            return RepeatMatch(kind=EXACT_REPEAT, earlier_question=earlier.text)

    text_tokens = content_tokens(sanitized_text)
    if len(text_tokens) < MIN_CONTENT_TOKENS:
        return None
    for earlier in earlier_questions:
        if earlier.skill_id != skill_id:
            continue
        earlier_tokens = content_tokens(sanitize_question(earlier.text))
        if len(earlier_tokens) < MIN_CONTENT_TOKENS:
            continue
        if _has_negation(text_tokens) != _has_negation(earlier_tokens):
            continue
        if _overlap(text_tokens, earlier_tokens) >= REPEAT_THRESHOLD:
            return RepeatMatch(kind=OVERLAP_REPEAT, earlier_question=earlier.text)
    return None
