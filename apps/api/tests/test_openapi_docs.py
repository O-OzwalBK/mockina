"""Tests that the OpenAPI document describes every product route completely."""

import pytest


def test_the_documentation_sweep_finds_routes(product_operations):
    """Guard: the checks below would pass vacuously if no route were found."""
    assert len(product_operations) >= 10


def label(method: str, path: str) -> str:
    """How a failing route is named in an assertion message."""
    return f"{method} {path}"


def test_every_product_route_has_a_summary_and_a_description(product_operations):
    """Each route shows a title and a longer explanation in the generated docs."""
    for method, path, operation in product_operations:
        assert operation.get("summary"), label(method, path)
        assert operation.get("description"), label(method, path)


def test_every_success_response_has_its_own_description(product_operations):
    """No route keeps FastAPI's placeholder 'Successful Response' text."""
    for method, path, operation in product_operations:
        success = [code for code in operation["responses"] if code.startswith("2")]
        assert success, label(method, path)
        for code in success:
            description = operation["responses"][code]["description"]
            assert description and description != "Successful Response", label(method, path)


def test_every_json_success_response_names_its_model(product_operations):
    """A route that returns a body points at a named model, never at an anonymous object."""
    for method, path, operation in product_operations:
        for code, response in operation["responses"].items():
            if not code.startswith("2") or code == "204":
                continue
            schema = response["content"]["application/json"]["schema"]
            assert "$ref" in schema, label(method, path)


def test_protected_routes_document_a_401_and_public_ones_do_not(product_operations, public_routes):
    """Whether a route needs a token is visible in its documented responses."""
    for method, path, operation in product_operations:
        documents_401 = "401" in operation["responses"]
        assert documents_401 == ((method, path) not in public_routes), label(method, path)


def test_error_responses_use_the_shared_error_model(product_operations):
    """Every documented 4xx/5xx body is the shared error envelope, not FastAPI's own shape."""
    for method, path, operation in product_operations:
        for code, response in operation["responses"].items():
            if code.startswith("2"):
                continue
            reference = response["content"]["application/json"]["schema"]["$ref"]
            assert reference.endswith("/ErrorResponse"), f"{label(method, path)} {code}"


def test_routes_with_path_ids_or_bodies_document_a_422(product_operations):
    """A route that validates input says so, because it can answer 422."""
    for method, path, operation in product_operations:
        takes_input = "{" in path or "requestBody" in operation
        if takes_input:
            assert "422" in operation["responses"], label(method, path)


@pytest.mark.parametrize("path", ["/v1/preparations/{preparation_id}", "/v1/sessions/{session_id}"])
def test_not_found_is_documented_where_ids_are_looked_up(product_operations, path):
    """Routes that look an item up by id document the 404 for missing and foreign items."""
    operations = [item for item in product_operations if item[1] == path]
    assert operations
    for method, route_path, operation in operations:
        assert "404" in operation["responses"], label(method, route_path)
