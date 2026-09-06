from openai.lib._pydantic import to_strict_json_schema

from pauth.schemas import ClinicalFacts, DocumentBundle, DocumentSections, MatchResult, Packet, PolicyChecklist, StrictModel


def _no_open_objects(node: object) -> None:
    """OpenAI rejects object schemas that allow extra keys."""
    if isinstance(node, dict):
        if node.get("type") == "object":
            assert node.get("additionalProperties") is not True
        for value in node.values():
            _no_open_objects(value)
    elif isinstance(node, list):
        for value in node:
            _no_open_objects(value)


def test_document_bundle_files_are_closed_objects():
    """`list[dict]` used to emit additionalProperties:true and 400 the document node."""
    schema = DocumentBundle.model_json_schema()
    files_items = schema["properties"]["files"]["items"]
    assert files_items.get("additionalProperties") is not True
    assert "$ref" in files_items or files_items.get("additionalProperties") is False


def test_llm_output_schemas_are_openai_strict():
    """Structured-output models must survive OpenAI's strict JSON schema rewrite."""

    class Refined(StrictModel):
        checklist: PolicyChecklist

    for model in (DocumentSections, ClinicalFacts, MatchResult, Packet, Refined):
        schema = to_strict_json_schema(model)
        assert schema.get("additionalProperties") is False
        _no_open_objects(schema)
