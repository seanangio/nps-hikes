"""Unit tests for the JSON schema validation hook.

Tests the validate_json_schema.py pre-commit hook that validates JSON
response examples in documentation against Pydantic API model schemas.
"""

import json
import tempfile
from pathlib import Path

import pytest

from scripts.hooks.validate_json_schema import (
    build_schemas,
    check_file,
    extract_annotated_blocks,
    make_schema_permissive,
    sanitize_json,
    validate_block,
)


class TestSanitizeJson:
    """Test ellipsis sanitization for partial JSON examples."""

    def test_inline_ellipsis_replaced(self):
        assert sanitize_json('"trails": [...]') == '"trails": []'

    def test_standalone_ellipsis_removed(self):
        result = sanitize_json('{\n    "a": 1,\n    ...\n}')
        assert "..." not in result

    def test_trailing_comma_stripped(self):
        result = sanitize_json('{"a": 1,\n}')
        assert result == '{"a": 1\n}'

    def test_combined_sanitization(self):
        content = '{\n    "items": [\n        {"id": 1},\n        ...\n    ]\n}'
        result = sanitize_json(content)
        parsed = json.loads(result)
        assert parsed == {"items": [{"id": 1}]}

    def test_no_ellipsis_unchanged(self):
        content = '{"key": "value"}'
        assert sanitize_json(content) == content


class TestExtractAnnotatedBlocks:
    """Test extraction of annotated JSON blocks from Markdown."""

    def test_finds_annotated_block(self):
        text = (
            "Some text\n\n"
            "<!-- response: GET /parks -->\n"
            "```json\n"
            '{"park_count": 1}\n'
            "```\n"
        )
        blocks = extract_annotated_blocks(text, "test.md")
        assert len(blocks) == 1
        _line_num, method, path, content = blocks[0]
        assert method == "GET"
        assert path == "/parks"
        assert '"park_count": 1' in content

    def test_skips_unannotated_block(self):
        text = '```json\n{"key": "value"}\n```\n'
        blocks = extract_annotated_blocks(text, "test.md")
        assert len(blocks) == 0

    def test_multiple_blocks(self):
        text = (
            "<!-- response: GET /parks -->\n"
            "```json\n{}\n```\n\n"
            "<!-- response: GET /trails -->\n"
            "```json\n{}\n```\n"
        )
        blocks = extract_annotated_blocks(text, "test.md")
        assert len(blocks) == 2
        assert blocks[0][1] == "GET"
        assert blocks[0][2] == "/parks"
        assert blocks[1][2] == "/trails"

    def test_post_method(self):
        text = "<!-- response: POST /query -->\n```json\n{}\n```\n"
        blocks = extract_annotated_blocks(text, "test.md")
        assert len(blocks) == 1
        assert blocks[0][1] == "POST"


class TestMakeSchemaPermissive:
    """Test schema patching for partial doc example validation."""

    def test_removes_required(self):
        schema = {
            "type": "object",
            "properties": {"a": {"type": "string"}, "b": {"type": "integer"}},
            "required": ["a", "b"],
        }
        patched = make_schema_permissive(schema)
        assert "required" not in patched

    def test_adds_additional_properties_false(self):
        schema = {
            "type": "object",
            "properties": {"a": {"type": "string"}},
        }
        patched = make_schema_permissive(schema)
        assert patched["additionalProperties"] is False

    def test_patches_defs(self):
        schema = {
            "type": "object",
            "properties": {
                "items": {
                    "type": "array",
                    "items": {"$ref": "#/$defs/Item"},
                }
            },
            "$defs": {
                "Item": {
                    "type": "object",
                    "properties": {"id": {"type": "integer"}},
                    "required": ["id"],
                }
            },
        }
        patched = make_schema_permissive(schema)
        item_def = patched["$defs"]["Item"]
        assert "required" not in item_def
        assert item_def["additionalProperties"] is False

    def test_does_not_mutate_original(self):
        schema = {
            "type": "object",
            "properties": {"a": {"type": "string"}},
            "required": ["a"],
        }
        make_schema_permissive(schema)
        assert "required" in schema


class TestBuildSchemas:
    """Test schema building from Pydantic models."""

    def test_returns_expected_endpoints(self):
        schemas = build_schemas()
        assert "GET /parks" in schemas
        assert "GET /trails" in schemas

    def test_schemas_have_no_required(self):
        schemas = build_schemas()
        for endpoint, schema in schemas.items():
            assert "required" not in schema, f"{endpoint} schema still has 'required'"

    def test_schemas_have_additional_properties_false(self):
        schemas = build_schemas()
        for endpoint, schema in schemas.items():
            assert schema.get("additionalProperties") is False, (
                f"{endpoint} schema missing additionalProperties: false"
            )

    def test_nested_defs_patched(self):
        schemas = build_schemas()
        parks_schema = schemas["GET /parks"]
        park_def = parks_schema["$defs"]["Park"]
        assert "required" not in park_def
        assert park_def["additionalProperties"] is False


class TestValidateBlock:
    """Test JSON instance validation against schemas."""

    @pytest.fixture()
    def parks_schema(self):
        return build_schemas()["GET /parks"]

    @pytest.fixture()
    def trails_schema(self):
        return build_schemas()["GET /trails"]

    def test_valid_parks_example(self, parks_schema):
        instance = {
            "park_count": 3,
            "visited_count": 3,
            "parks": [
                {
                    "park_code": "acad",
                    "park_name": "Acadia",
                }
            ],
        }
        errors = validate_block(instance, parks_schema)
        assert errors == []

    def test_valid_partial_example(self, parks_schema):
        """Empty arrays (from sanitized [...]) should pass."""
        instance = {
            "park_count": 3,
            "parks": [],
        }
        errors = validate_block(instance, parks_schema)
        assert errors == []

    def test_extra_field_detected(self, parks_schema):
        instance = {
            "park_count": 3,
            "parks": [{"park_code": "acad", "bogus_field": "oops"}],
        }
        errors = validate_block(instance, parks_schema)
        assert len(errors) == 1
        assert "bogus_field" in errors[0]

    def test_wrong_type_detected(self, parks_schema):
        instance = {
            "park_count": "not a number",
        }
        errors = validate_block(instance, parks_schema)
        assert len(errors) == 1
        assert "not a number" in errors[0]

    def test_valid_trails_with_pagination(self, trails_schema):
        instance = {
            "trail_count": 50,
            "total_miles": 342.7,
            "trails": [],
            "pagination": {
                "limit": 50,
                "offset": 0,
                "total_count": 127,
                "has_next": True,
                "has_prev": False,
            },
        }
        errors = validate_block(instance, trails_schema)
        assert errors == []

    def test_extra_field_in_nested_object(self, trails_schema):
        instance = {
            "pagination": {
                "limit": 50,
                "extra_key": True,
            },
        }
        errors = validate_block(instance, trails_schema)
        assert any("extra_key" in e for e in errors)


class TestCheckFile:
    """End-to-end test with temporary Markdown files."""

    @pytest.fixture()
    def schemas(self):
        return build_schemas()

    def test_valid_file_no_errors(self, schemas):
        content = (
            "# API Tutorial\n\n"
            "<!-- response: GET /parks -->\n"
            "```json\n"
            "{\n"
            '    "park_count": 1,\n'
            '    "visited_count": 1,\n'
            '    "parks": []\n'
            "}\n"
            "```\n"
        )
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write(content)
            tmpfile = f.name

        try:
            errors = check_file(tmpfile, schemas)
            assert errors == []
        finally:
            Path(tmpfile).unlink()

    def test_invalid_field_reports_error(self, schemas):
        content = (
            "<!-- response: GET /parks -->\n"
            "```json\n"
            "{\n"
            '    "park_count": 1,\n'
            '    "wrong_field": 1\n'
            "}\n"
            "```\n"
        )
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write(content)
            tmpfile = f.name

        try:
            errors = check_file(tmpfile, schemas)
            assert len(errors) >= 1
            assert "wrong_field" in errors[0]
        finally:
            Path(tmpfile).unlink()

    def test_unknown_endpoint_reports_error(self, schemas):
        content = "<!-- response: GET /nonexistent -->\n```json\n{}\n```\n"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write(content)
            tmpfile = f.name

        try:
            errors = check_file(tmpfile, schemas)
            assert len(errors) == 1
            assert "unknown endpoint" in errors[0]
        finally:
            Path(tmpfile).unlink()

    def test_file_without_annotations_no_errors(self, schemas):
        content = '# Just markdown\n\n```json\n{"key": "value"}\n```\n'
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write(content)
            tmpfile = f.name

        try:
            errors = check_file(tmpfile, schemas)
            assert errors == []
        finally:
            Path(tmpfile).unlink()

    def test_partial_example_with_ellipsis(self, schemas):
        content = (
            "<!-- response: GET /parks -->\n"
            "```json\n"
            "{\n"
            '    "park_count": 3,\n'
            '    "parks": [\n'
            '        {"park_code": "acad"},\n'
            "        ...\n"
            "    ]\n"
            "}\n"
            "```\n"
        )
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write(content)
            tmpfile = f.name

        try:
            errors = check_file(tmpfile, schemas)
            assert errors == []
        finally:
            Path(tmpfile).unlink()
