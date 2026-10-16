import ast
import hashlib
import importlib
import json
import pickle
from pathlib import Path

import pytest
from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[1]
BASELINE = json.loads(
    (ROOT / "tests/fixtures/orchestration_baseline.json").read_text(encoding="utf-8")
)


@pytest.mark.parametrize("name", BASELINE["schemas"])
def test_response_model_schema_and_public_identity(orchestrator, name):
    model = getattr(orchestrator, name)
    assert model.model_json_schema() == BASELINE["schemas"][name]
    assert model.__module__ == "client.orchestrator"
    assert pickle.loads(pickle.dumps(model)) is model
    extracted = importlib.import_module("models.orchestration")
    assert getattr(extracted, name) is model


def test_required_nullable_fields_and_status_validation(orchestrator):
    model = orchestrator.PendingCorrectionResolution
    assert model(status="FORGET", replacement_value=None).model_dump() == {
        "status": "FORGET",
        "replacement_value": None,
    }
    instance = model(status="FORGET", replacement_value=None)
    assert pickle.loads(pickle.dumps(instance)) == instance
    with pytest.raises(ValidationError) as missing:
        model(status="FORGET")
    assert missing.value.errors()[0]["type"] == "missing"
    with pytest.raises(ValidationError) as invalid:
        model(status="INVALID", replacement_value=None)
    assert invalid.value.errors()[0]["type"] == "literal_error"


def test_conflict_default_is_independent(orchestrator):
    first = orchestrator.ConflictAnalysis()
    second = orchestrator.ConflictAnalysis()
    first.conflicts.append(
        orchestrator.MemoryConflict(
            claim_ids=[1, 2],
            subject="dish",
            attribute="salt",
            conflicting_values=["more", "less"],
        )
    )
    assert second.model_dump() == {"conflicts": []}


@pytest.mark.parametrize("name", BASELINE["prompt_sha256"])
def test_classifier_prompt_is_unchanged(orchestrator, name):
    tree = ast.parse((ROOT / "client/orchestrator.py").read_text(encoding="utf-8"))
    function = next(node for node in tree.body if getattr(node, "name", None) == name)
    parse_call = next(
        node
        for node in ast.walk(function)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "to_thread"
    )
    inputs = next(item.value for item in parse_call.keywords if item.arg == "input")
    system_content = inputs.elts[0].values[1]
    prompt = eval(
        compile(ast.Expression(system_content), "<system prompt>", "eval"),
        vars(orchestrator),
    )
    assert (
        hashlib.sha256(prompt.encode()).hexdigest() == BASELINE["prompt_sha256"][name]
    )
