from backend.agent.activity_classifier import _parse_activity


def test_parse_activity_accepts_supported_values() -> None:
    assert _parse_activity("Explain") == "explain"
    assert _parse_activity("(derive)") == "derive"
    assert _parse_activity("practice。") == "practice"
    assert _parse_activity("[recall]") == "recall"


def test_parse_activity_rejects_unknown_values() -> None:
    assert _parse_activity("") is None
    assert _parse_activity("chat") is None
    assert _parse_activity("explanation") is None
