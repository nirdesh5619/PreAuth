from pathlib import Path

from pauth.config import Settings


def test_settings_read_openai_key_from_env_file(tmp_path: Path, monkeypatch):
    """A dedicated env file should populate the OpenAI key and enable LLM mode."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text("OPENAI_API_KEY=sk-test-secret\nLLM_MODEL=gpt-4o-mini\n", encoding="utf-8")
    loaded = Settings(_env_file=env_file, _env_file_encoding="utf-8")
    assert loaded.openai_api_key == "sk-test-secret"
    assert loaded.llm_model == "gpt-4o-mini"
    assert loaded.use_llm is True


def test_blank_key_stays_on_stubs(monkeypatch):
    """Whitespace-only keys must not count as configured."""
    monkeypatch.setenv("OPENAI_API_KEY", "   ")
    monkeypatch.setenv("PAUTH_FORCE_STUBS", "0")
    loaded = Settings(_env_file=None)
    assert loaded.use_llm is False
