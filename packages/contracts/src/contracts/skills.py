"""Shared skill-tree models and the stable skill identity scheme."""

import unicodedata
from collections import Counter
from uuid import UUID, uuid5

from pydantic import Field, field_validator, model_validator

from contracts.common import ImmutableModel
from contracts.interviewer import MAX_SKILL_ID_LENGTH

SKILL_NAMESPACE = UUID("f4a1c6d2-3b90-5e71-8a46-2c9d7e0b1f53")
MAX_SKILL_LABEL_LENGTH = 120
MIN_IMPORTANCE = 1
MAX_IMPORTANCE = 5
MIN_DIFFICULTY = 1
MAX_DIFFICULTY = 5
MIN_SKILL_LEAVES = 3
MAX_SKILL_LEAVES = 30
MAX_SKILL_TREE_DEPTH = 3
STOPWORDS = frozenset(
    {"in", "of", "the", "and", "for", "with", "to", "on", "at", "by", "from", "a", "an"}
)
DO_NOT_STRIP = frozenset(
    {
        "react native",
        "react router",
        "react query",
        "vue router",
        "angular router",
        "next js",
        "svelte kit",
    }
)


def normalize(text: str) -> str:
    """Normalize a label with NFKC, lowercase, punctuation spacing, and collapsed whitespace."""
    compatible_text = unicodedata.normalize("NFKC", text).lower()
    spaced_characters = (
        " "
        if unicodedata.category(character).startswith("P") and character not in {"+", "#"}
        else character
        for character in compatible_text
    )
    return " ".join("".join(spaced_characters).split())


def normalize_sorted(text: str) -> str:
    """Normalize a label, remove agreed stopwords, and sort the remaining tokens."""
    normalized = normalize(text)
    tokens = [token for token in normalized.split() if token not in STOPWORDS]
    return " ".join(sorted(tokens))


def skill_id(root_label: str, node_label: str) -> str:
    """Return the permanent UUIDv5 for a label under its root category."""
    root_key = normalize(root_label)
    node_key = normalize_sorted(node_label)
    if normalize(node_label) not in DO_NOT_STRIP:
        root_tokens = set(root_key.split())
        stripped_key = " ".join(token for token in node_key.split() if token not in root_tokens)
        node_key = stripped_key or node_key
    key = f"{root_key}|{node_key}"
    return str(uuid5(SKILL_NAMESPACE, key))


class SkillNode(ImmutableModel):
    """One category, intermediate node, or leaf in a preparation's skill tree."""

    id: str = Field(
        description="Stable UUIDv5 identity derived from this node's root and normalized label.",
        min_length=1,
        max_length=MAX_SKILL_ID_LENGTH,
        examples=["8dd8e540-014e-52e3-8f87-0fd42abe1678"],
    )
    label: str = Field(
        description="Short display label for this category or technical skill.",
        min_length=1,
        max_length=MAX_SKILL_LABEL_LENGTH,
        examples=["React hooks"],
    )
    parent_id: str | None = Field(
        default=None,
        description="ID of this node's parent, or None when this node is a root category.",
        min_length=1,
        max_length=MAX_SKILL_ID_LENGTH,
        examples=["a35c1455-ea0c-50a7-a5cc-073ac509bfbb"],
    )
    importance: int | None = Field(
        default=None,
        description="Importance from 1 to 5 for this skill in this preparation; set on leaves only.",
        ge=MIN_IMPORTANCE,
        le=MAX_IMPORTANCE,
        examples=[4],
    )
    difficulty: int | None = Field(
        default=None,
        description="Expected difficulty from 1 to 5 for this skill in this preparation; set on leaves only.",
        ge=MIN_DIFFICULTY,
        le=MAX_DIFFICULTY,
        examples=[3],
    )

    @field_validator("label")
    @classmethod
    def _label_has_identity_text(cls, value: str) -> str:
        """Require a label to retain at least one token after stopword removal."""
        if not normalize_sorted(value):
            raise ValueError("label must contain a non-stopword token")
        return value


class SkillGraph(ImmutableModel):
    """The validated skill hierarchy extracted for one preparation."""

    nodes: tuple[SkillNode, ...] = Field(
        description="Category, intermediate, and leaf nodes in the preparation's skill tree.",
        min_length=1,
        examples=[
            [
                {
                    "id": "cee9c65f-beef-5a90-8f32-34dc4048f4bc",
                    "label": "React",
                    "parent_id": None,
                    "importance": None,
                    "difficulty": None,
                },
                {
                    "id": "8dd8e540-014e-52e3-8f87-0fd42abe1678",
                    "label": "Hooks",
                    "parent_id": "cee9c65f-beef-5a90-8f32-34dc4048f4bc",
                    "importance": 4,
                    "difficulty": 3,
                },
                {
                    "id": "4ad725ae-ee80-5133-870a-3640ce7418e2",
                    "label": "Effects",
                    "parent_id": "cee9c65f-beef-5a90-8f32-34dc4048f4bc",
                    "importance": 3,
                    "difficulty": 2,
                },
                {
                    "id": "eb315a8a-1fb0-5829-b114-f5d805e4c26c",
                    "label": "State",
                    "parent_id": "cee9c65f-beef-5a90-8f32-34dc4048f4bc",
                    "importance": 3,
                    "difficulty": 3,
                },
            ]
        ],
    )

    @model_validator(mode="after")
    def _validate_tree(self) -> "SkillGraph":
        """Enforce unique IDs, valid parents, root-scoped identities, depth, and leaf metadata."""
        nodes_by_id = {node.id: node for node in self.nodes}
        if len(nodes_by_id) != len(self.nodes):
            raise ValueError("node IDs must be unique")

        sibling_labels = [(node.parent_id, normalize(node.label)) for node in self.nodes]
        if any(count > 1 for count in Counter(sibling_labels).values()):
            raise ValueError("sibling labels must be unique after normalization")

        parent_ids = {node.parent_id for node in self.nodes if node.parent_id is not None}
        leaves = [node for node in self.nodes if node.id not in parent_ids]
        if not MIN_SKILL_LEAVES <= len(leaves) <= MAX_SKILL_LEAVES:
            raise ValueError(
                f"the skill tree must contain between {MIN_SKILL_LEAVES} and "
                f"{MAX_SKILL_LEAVES} leaves"
            )

        for node in self.nodes:
            current = node
            visited: set[str] = set()
            depth = 1
            while current.parent_id is not None:
                if current.id in visited:
                    raise ValueError("the skill tree cannot contain a cycle")
                visited.add(current.id)
                parent = nodes_by_id.get(current.parent_id)
                if parent is None:
                    raise ValueError("each non-root node must refer to a parent in this graph")
                current = parent
                depth += 1
                if depth > MAX_SKILL_TREE_DEPTH:
                    raise ValueError(f"the skill tree cannot exceed depth {MAX_SKILL_TREE_DEPTH}")

            if node.id != skill_id(current.label, node.label):
                raise ValueError("each node ID must match its root and label")

            is_leaf = node.id not in parent_ids
            has_importance = node.importance is not None
            has_difficulty = node.difficulty is not None
            if is_leaf and not (has_importance and has_difficulty):
                raise ValueError("each leaf must have importance and difficulty")
            if not is_leaf and (has_importance or has_difficulty):
                raise ValueError("non-leaf nodes cannot have importance or difficulty")

        return self
