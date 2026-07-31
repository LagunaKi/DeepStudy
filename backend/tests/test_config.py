from backend.config import Settings


def test_secure_gemini_defaults() -> None:
    settings = Settings(_env_file=None)

    assert settings.GEMINI_API_KEY == ""
    assert settings.LLM_MODEL == "gemini-3-flash-preview"
    assert settings.LLM_CODER_MODEL == "gemini-3-flash-preview"
    assert settings.GEMINI_THINKING_LEVEL == "medium"


def test_environment_can_override_model(monkeypatch) -> None:
    monkeypatch.setenv("LLM_MODEL", "gemini-flash-latest")
    settings = Settings(_env_file=None)

    assert settings.LLM_MODEL == "gemini-flash-latest"
