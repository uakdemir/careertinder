import pytest
import yaml
from pydantic import ValidationError

from jobhunter.config.loader import load_config
from jobhunter.config.schema import AppConfig, ConfigurationError


class TestConfigLoading:
    def test_valid_config_loads(self, sample_config_yaml):
        config = load_config(sample_config_yaml)
        assert isinstance(config, AppConfig)
        assert config.database.path == "data/test.db"
        assert config.filtering.salary_min_usd == 90000

    def test_missing_file_raises_error(self, tmp_path):
        with pytest.raises(ConfigurationError, match="config.yaml not found"):
            load_config(tmp_path / "nonexistent.yaml")

    def test_invalid_yaml_raises_error(self, tmp_path):
        bad_yaml = tmp_path / "config.yaml"
        bad_yaml.write_text("{{invalid yaml: [", encoding="utf-8")
        with pytest.raises(ConfigurationError, match="Failed to parse"):
            load_config(bad_yaml)

    def test_invalid_type_raises_error(self, tmp_path):
        config_path = tmp_path / "config.yaml"
        config_path.write_text(
            yaml.dump({"filtering": {"salary_min_usd": "ninety"}}),
            encoding="utf-8",
        )
        with pytest.raises(ConfigurationError, match="validation failed"):
            load_config(config_path)

    def test_unknown_keys_ignored(self, tmp_path, sample_config_dict):
        sample_config_dict["unknown_section"] = {"foo": "bar"}
        config_path = tmp_path / "config.yaml"
        config_path.write_text(yaml.dump(sample_config_dict), encoding="utf-8")
        config = load_config(config_path)
        assert isinstance(config, AppConfig)

    def test_empty_config_uses_defaults(self, tmp_path):
        config_path = tmp_path / "config.yaml"
        config_path.write_text("{}", encoding="utf-8")
        config = load_config(config_path)
        assert config.database.path == "data/jobhunter.db"
        assert config.filtering.salary_min_usd == 90000

    def test_config_is_frozen(self, sample_config_yaml):
        config = load_config(sample_config_yaml)
        with pytest.raises(ValidationError):
            config.database = None  # type: ignore[assignment]

    def test_temperature_validation(self, tmp_path):
        config_path = tmp_path / "config.yaml"
        config_path.write_text(
            yaml.dump({"ai_models": {"tier2": {"temperature": 1.5}}}),
            encoding="utf-8",
        )
        with pytest.raises(ConfigurationError, match="validation failed"):
            load_config(config_path)
