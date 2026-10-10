from backend.settings import Settings, load_config


def test_settings_read_from_env(monkeypatch):
    monkeypatch.setenv("LLM_BASE_URL", "https://llm.test/v1")
    monkeypatch.setenv("LLM_API_KEY", "k")
    monkeypatch.setenv("NEATLOGS_API_KEY", "n")
    s = Settings(_env_file=None)
    assert (s.llm_base_url, s.llm_api_key, s.neatlogs_api_key) == ("https://llm.test/v1", "k", "n")


def test_bedrock_key_name_is_accepted(monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.setenv("BEDROCK_API_KEY", "b")
    assert Settings(_env_file=None).llm_api_key == "b"


def test_settings_default_to_empty(monkeypatch):
    for name in ("LLM_BASE_URL", "LLM_API_KEY", "BEDROCK_API_KEY", "NEATLOGS_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    s = Settings(_env_file=None)
    assert (s.llm_base_url, s.llm_api_key, s.neatlogs_api_key) == ("", "", "")


def test_load_config_reads_models_and_limits(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text('[llm.models]\nlight = "m-light"\n\n[llm]\ntimeout_seconds = 5\nmax_output_tokens = 64\n')
    config = load_config(path)
    assert config.llm.models == {"light": "m-light"}
    assert (config.llm.timeout_seconds, config.llm.max_output_tokens) == (5, 64)


def test_load_config_missing_file_gives_defaults(tmp_path):
    config = load_config(tmp_path / "absent.toml")
    assert config.llm.models == {}


def test_repo_config_parses():
    assert set(load_config().llm.models) == {"orchestrator", "coder", "light"}
