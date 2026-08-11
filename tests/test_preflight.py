from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from scripts import preflight  # noqa: E402


def run_preflight(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "preflight.py"), *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )


def test_repository_passes_preflight_without_api() -> None:
    result = run_preflight("--skip-api")

    assert result.returncode == 0, result.stdout + result.stderr
    assert "SẴN SÀNG" in result.stdout
    assert "[FAILED]" not in result.stdout


def test_json_output_lists_every_check() -> None:
    result = run_preflight("--skip-api", "--json")

    payload = json.loads(result.stdout)
    assert payload["ready_to_submit"] is True
    assert payload["blocking"] == 0
    names = {check["name"] for check in payload["checks"]}
    assert {"Python version", "Dependencies", "File .env", "Vệ sinh secret"} <= names


def test_env_check_reports_missing_keys() -> None:
    check = preflight.check_env_file({"APP_ENV": "dev"}, REPO_ROOT / ".env")

    assert check.ok is False
    assert "APP_NAME" in check.detail


def test_parse_env_file_skips_comments_and_blanks(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("# comment\n\nAPP_ENV=dev\nLOG_PATH = data/logs.jsonl\n", encoding="utf-8")

    values = preflight.parse_env_file(env_file)

    assert values == {"APP_ENV": "dev", "LOG_PATH": "data/logs.jsonl"}


def test_missing_langfuse_key_is_a_warning_not_a_blocker() -> None:
    check = preflight.check_langfuse({"LANGFUSE_HOST": "https://cloud.langfuse.com"})

    assert check.ok is False
    assert check.required is False
    assert check.label == "[WARN]"


@pytest.mark.parametrize("flag", ["--require-api", ""])
def test_api_check_failure_severity_follows_flag(flag: str) -> None:
    check = preflight.check_api("http://127.0.0.1:9", required=bool(flag))

    assert check.ok is False
    assert check.required is bool(flag)
