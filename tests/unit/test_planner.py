import pytest
from src.orchestrator.agents.planner import _parse_plan


class TestParsePlan:
    def test_extract_array(self) -> None:
        text = "Here is the plan:\n[{\"id\": \"t1\", \"description\": \"test\", \"deps\": []}]\nDone."
        result = _parse_plan(text)
        assert result == [{"id": "t1", "description": "test", "deps": []}]

    def test_extract_object(self) -> None:
        text = "Result: {\"tasks\": [{\"id\": \"t1\", \"description\": \"test\", \"deps\": []}]}"
        result = _parse_plan(text)
        assert result == [{"id": "t1", "description": "test", "deps": []}]

    def test_no_json_found(self) -> None:
        text = "No JSON here"
        result = _parse_plan(text)
        assert result is None

    def test_extract_nested_brackets(self) -> None:
        text = "Plan: [{\"id\": \"t1\", \"description\": \"a [test] task\", \"deps\": []}]"
        result = _parse_plan(text)
        assert result == [{"id": "t1", "description": "a [test] task", "deps": []}]

    def test_empty_text(self) -> None:
        assert _parse_plan("") is None
        assert _parse_plan(None) is None  # type: ignore
