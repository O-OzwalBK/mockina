import pytest
import skill_graph

EXPECTED_PUBLIC_NAMES = {
    "InMemorySkillCatalog",
    "InMemorySkillStore",
    "MAX_CATALOG_ENTRIES_IN_PROMPT",
    "SEED_CATALOG",
    "SEED_LABELS",
    "SkillCatalog",
    "SkillCatalogEntry",
    "SkillExtractionError",
    "SkillGraphError",
    "SkillGraphValidationError",
    "SkillParseError",
    "SkillStore",
    "build_prompt",
    "extract_skills",
    "parse_skill_tree",
    "select_catalog_entries",
}

EXPORTED_CLASSES = [
    getattr(skill_graph, name)
    for name in skill_graph.__all__
    if isinstance(getattr(skill_graph, name), type)
]


def test_public_names_are_exactly_the_expected_ones():
    """The skill_graph package API changes only when its pinned export set changes."""
    assert set(skill_graph.__all__) == EXPECTED_PUBLIC_NAMES


@pytest.mark.parametrize("item", EXPORTED_CLASSES, ids=lambda item: item.__name__)
def test_every_public_class_has_a_docstring(item):
    """Every public model, protocol, store, and error has a useful docstring."""
    assert item.__doc__ is not None
    assert item.__doc__.strip()
