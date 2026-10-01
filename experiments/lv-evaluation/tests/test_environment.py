from lv_eval.environment import load_environment


def test_local_credentials_only_and_existing_environment_wins(tmp_path, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("UNRELATED_SETTING", raising=False)
    (tmp_path / ".env").write_text("GEMINI_API_KEY=offline-${LITERAL}\nUNRELATED_SETTING=ignored\n")
    load_environment(tmp_path)
    import os
    assert os.environ["GEMINI_API_KEY"] == "offline-${LITERAL}"
    assert "UNRELATED_SETTING" not in os.environ
    monkeypatch.setenv("GEMINI_API_KEY", "existing")
    load_environment(tmp_path)
    assert os.environ["GEMINI_API_KEY"] == "existing"
