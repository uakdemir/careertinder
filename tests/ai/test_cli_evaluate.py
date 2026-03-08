"""Tests for CLI evaluate command."""

import sys
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from jobhunter.ai.evaluator import EvaluationRunResult
from jobhunter.cli import cli
from jobhunter.config.schema import AICostConfig, AIModelConfig, AIModelsConfig, AppConfig


@contextmanager
def _mock_evaluate_deps(run_result: EvaluationRunResult | None = None):
    """Mock all evaluate command dependencies (DB, AI client, cost config)."""
    mock_session = MagicMock()
    mock_session.__enter__ = MagicMock(return_value=mock_session)
    mock_session.__exit__ = MagicMock(return_value=False)

    # Temporarily inject a fake openai_client module if openai isn't installed
    fake_modules: dict[str, MagicMock] = {}
    for mod_name in ("openai", "jobhunter.ai.openai_client"):
        if mod_name not in sys.modules:
            fake_modules[mod_name] = MagicMock()

    with (
        patch.dict(sys.modules, fake_modules),
        patch("jobhunter.cli.load_config", return_value=AppConfig()),
        patch("jobhunter.cli.SecretsConfig") as mock_secrets_cls,
        patch("jobhunter.ai.evaluator.EvaluationService") as mock_svc_cls,
        patch("jobhunter.db.session.create_engine"),
        patch("jobhunter.db.session.get_session", return_value=mock_session),
        patch("jobhunter.db.settings.get_ai_cost_config", return_value=AICostConfig()),
    ):
        mock_secrets_cls.return_value = MagicMock(openai_api_key="test-key")
        mock_svc = MagicMock()

        async def mock_run(**kwargs):
            return run_result or EvaluationRunResult()

        mock_svc.run = mock_run
        mock_svc_cls.return_value = mock_svc
        yield


class TestCliEvaluateCommand:
    def test_evaluate_missing_api_key(self, tmp_path) -> None:
        """Evaluate should fail if OPENAI_API_KEY is not set (default provider is openai)."""
        runner = CliRunner()
        config_path = tmp_path / "config.yaml"
        config_path.write_text("{}", encoding="utf-8")

        with patch("jobhunter.cli.load_config", return_value=AppConfig()):
            with patch("jobhunter.cli.SecretsConfig") as mock_secrets:
                mock_secrets.return_value = MagicMock(openai_api_key=None)
                result = runner.invoke(cli, ["--config", str(config_path), "evaluate"])

        assert result.exit_code != 0
        assert "OPENAI_API_KEY" in result.output

    def test_evaluate_unsupported_provider(self, tmp_path) -> None:
        """Evaluate should fail if provider is not 'anthropic' or 'openai'."""
        runner = CliRunner()
        config_path = tmp_path / "config.yaml"
        config_path.write_text("{}", encoding="utf-8")

        config = AppConfig(
            ai_models=AIModelsConfig(
                tier2=AIModelConfig(provider="gemini", model="gemini-pro"),
            )
        )

        with patch("jobhunter.cli.load_config", return_value=config):
            result = runner.invoke(cli, ["--config", str(config_path), "evaluate"])

        assert result.exit_code != 0
        assert "Unsupported AI provider" in result.output

    def test_evaluate_dry_run_flag_accepted(self, tmp_path) -> None:
        """Evaluate should accept --dry-run flag and show output."""
        runner = CliRunner()
        config_path = tmp_path / "config.yaml"
        config_path.write_text("{}", encoding="utf-8")

        with _mock_evaluate_deps():
            result = runner.invoke(cli, [
                "--config", str(config_path), "evaluate", "--dry-run",
            ])

        assert result.exit_code == 0
        assert "Evaluation complete" in result.output
        assert "Tier 2:" in result.output

    def test_evaluate_tier2_only_flag(self, tmp_path) -> None:
        """Evaluate with --tier2-only should not show Tier 3 output."""
        runner = CliRunner()
        config_path = tmp_path / "config.yaml"
        config_path.write_text("{}", encoding="utf-8")

        with _mock_evaluate_deps():
            result = runner.invoke(cli, [
                "--config", str(config_path), "evaluate", "--tier2-only",
            ])

        assert result.exit_code == 0
        assert "Tier 2:" in result.output
        assert "Tier 3:" not in result.output

    def test_evaluate_shows_cost_cap_warning(self, tmp_path) -> None:
        """Evaluate should show cost cap warning when cap reached."""
        runner = CliRunner()
        config_path = tmp_path / "config.yaml"
        config_path.write_text("{}", encoding="utf-8")

        run_result = EvaluationRunResult(
            tier2_evaluated=5, tier2_passed=3, tier2_failed=2,
            total_cost_usd=2.0, cap_reached=True,
        )

        with _mock_evaluate_deps(run_result):
            result = runner.invoke(cli, [
                "--config", str(config_path), "evaluate",
            ])

        assert result.exit_code == 0
        assert "cost cap reached" in result.output.lower()
