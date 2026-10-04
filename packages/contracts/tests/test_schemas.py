import json

from contracts.schemas import all_schemas

EXPECTED_SCHEMAS = {
    "Answer",
    "Evaluation",
    "InterviewSession",
    "MetricScore",
    "Preparation",
    "PreparationCreate",
    "Question",
    "Turn",
    "WordTiming",
}


def test_schemas_cover_every_public_model_with_fields():
    """There is one schema for each public model that has fields."""
    assert set(all_schemas()) == EXPECTED_SCHEMAS


def test_schemas_describe_every_property():
    """Every property in every schema carries its description, so the docs reach the output."""
    for model_name, schema in all_schemas().items():
        for property_name, details in schema["properties"].items():
            assert "description" in details, f"{model_name}.{property_name} has no description"


def test_schemas_include_limits_and_examples():
    """Limits and examples written on a field show up in its schema."""
    score = all_schemas()["MetricScore"]["properties"]["score"]
    assert score["minimum"] == 0
    assert score["maximum"] == 10
    assert score["examples"] == [7]


def test_schemas_can_be_written_as_json():
    """The schemas contain only plain JSON values, so they can be written to files."""
    assert json.loads(json.dumps(all_schemas())) == all_schemas()