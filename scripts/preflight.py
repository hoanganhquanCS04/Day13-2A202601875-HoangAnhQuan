"""Preflight check trước khi nộp bài — Người 1 (Setup & Integration Lead).

Gom các bước kiểm tra rời rạc trong SETUP.md / SUBMISSION.md thành một lệnh:
môi trường, cấu hình, file bắt buộc, vệ sinh secret và trạng thái API.

    python scripts/preflight.py            # bỏ qua API nếu chưa chạy uvicorn
    python scripts/preflight.py --require-api
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.cli import configure_utf8_stdio

MIN_PYTHON = (3, 11)
BASE_URL = "http://127.0.0.1:8000"
REQUIRED_MODULES = (
    "fastapi",
    "uvicorn",
    "pydantic",
    "structlog",
    "dotenv",
    "httpx",
    "langfuse",
    "yaml",
    "pytest",
)
REQUIRED_ENV_KEYS = ("APP_ENV", "APP_NAME", "LOG_LEVEL", "LOG_PATH")
LANGFUSE_ENV_KEYS = ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "LANGFUSE_HOST")
REQUIRED_PATHS = (
    "app/main.py",
    "config/dashboard.yaml",
    "config/slo.yaml",
    "config/alert_rules.yaml",
    "config/challenge.json",
    "config/logging_schema.json",
    "data/sample_queries.jsonl",
    "scripts/load_test.py",
    "scripts/validate_logs.py",
    "scripts/validate_dashboard.py",
    "submission/REPORT.md",
)
SECRET_FILES = (".env", ".venv")


@dataclass
class Check:
    """Một hạng mục kiểm tra; ``required=False`` chỉ cảnh báo, không chặn nộp bài."""

    name: str
    ok: bool
    detail: str
    required: bool = True

    @property
    def label(self) -> str:
        if self.ok:
            return "[PASSED]"
        return "[FAILED]" if self.required else "[WARN]"


def check_python() -> Check:
    version = ".".join(str(part) for part in sys.version_info[:3])
    ok = sys.version_info >= MIN_PYTHON
    minimum = ".".join(str(part) for part in MIN_PYTHON)
    return Check("Python version", ok, f"đang dùng {version}, yêu cầu >= {minimum}")


def check_dependencies() -> Check:
    missing = [name for name in REQUIRED_MODULES if importlib.util.find_spec(name) is None]
    if missing:
        return Check(
            "Dependencies",
            False,
            f"thiếu {', '.join(missing)} — chạy pip install -r requirements.txt",
        )
    return Check("Dependencies", True, f"{len(REQUIRED_MODULES)} package bắt buộc đã cài")


def parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        values[key.strip()] = value.strip()
    return values


def check_env_file(env_values: dict[str, str], env_path: Path) -> Check:
    if not env_values:
        return Check("File .env", False, f"chưa có {env_path.name} — copy từ .env.example")
    missing = [key for key in REQUIRED_ENV_KEYS if not env_values.get(key)]
    if missing:
        return Check("File .env", False, f"thiếu giá trị cho {', '.join(missing)}")
    return Check("File .env", True, f"app env = {env_values['APP_ENV']}, log = {env_values['LOG_PATH']}")


def check_langfuse(env_values: dict[str, str]) -> Check:
    """Cảnh báo mềm: thiếu key thì app vẫn chạy nhưng không có evidence trace."""
    missing = [key for key in LANGFUSE_ENV_KEYS if not env_values.get(key)]
    if missing:
        return Check(
            "Langfuse config",
            False,
            f"thiếu {', '.join(missing)} — app chạy prompt local, chưa có trace evidence",
            required=False,
        )
    prompt = env_values.get("LANGFUSE_PROMPT_NAME", "day13-chat")
    label = env_values.get("LANGFUSE_PROMPT_LABEL", "production")
    return Check("Langfuse config", True, f"host {env_values['LANGFUSE_HOST']}, prompt {prompt}@{label}")


def check_required_paths() -> Check:
    missing = [path for path in REQUIRED_PATHS if not (REPO_ROOT / path).exists()]
    if missing:
        return Check("File bắt buộc", False, f"thiếu {', '.join(missing)}")
    return Check("File bắt buộc", True, f"{len(REQUIRED_PATHS)} file/thư mục đầy đủ")


def git_tracked_files() -> list[str] | None:
    try:
        result = subprocess.run(
            ["git", "ls-files"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
    except FileNotFoundError:
        return None
    if result.returncode != 0:
        return None
    return result.stdout.splitlines()


def check_secret_hygiene() -> Check:
    tracked = git_tracked_files()
    if tracked is None:
        return Check("Vệ sinh secret", False, "không chạy được git ls-files", required=False)
    leaked = sorted(
        {
            entry
            for entry in SECRET_FILES
            for path in tracked
            if path == entry or path.startswith(f"{entry}/")
        }
    )
    if leaked:
        return Check("Vệ sinh secret", False, f"Git đang track {', '.join(leaked)} — gỡ trước khi nộp")
    return Check("Vệ sinh secret", True, ".env và .venv không nằm trong Git index")


def check_logs(env_values: dict[str, str]) -> Check:
    log_path = REPO_ROOT / env_values.get("LOG_PATH", "data/logs.jsonl")
    if not log_path.exists():
        return Check("Log file", False, f"chưa có {log_path.name} — chạy API rồi load_test.py")
    lines = [line for line in log_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not lines:
        return Check("Log file", False, f"{log_path.name} rỗng — chạy scripts/load_test.py")
    return Check("Log file", True, f"{len(lines)} dòng trong {log_path.name}")


def check_api(base_url: str, required: bool) -> Check:
    import httpx

    try:
        response = httpx.get(f"{base_url}/health", timeout=5.0)
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:  # noqa: BLE001 - báo nguyên nhân cho người chạy lab
        return Check(
            "API /health",
            False,
            f"không gọi được {base_url}/health ({type(exc).__name__}) — chạy uvicorn app.main:app",
            required=required,
        )
    tracing = "bật" if payload.get("tracing_enabled") else "tắt"
    incidents = [name for name, on in (payload.get("incidents") or {}).items() if on]
    incident_note = f", incident đang bật: {', '.join(incidents)}" if incidents else ", không incident nào bật"
    return Check("API /health", bool(payload.get("ok")), f"ok, tracing {tracing}{incident_note}")


def run_checks(base_url: str, require_api: bool, skip_api: bool) -> list[Check]:
    env_path = REPO_ROOT / ".env"
    env_values = parse_env_file(env_path)
    # Cho phép biến môi trường thật (CI, --env-file) ghi đè giá trị đọc từ file.
    for key in (*REQUIRED_ENV_KEYS, *LANGFUSE_ENV_KEYS, "LANGFUSE_PROMPT_NAME", "LANGFUSE_PROMPT_LABEL"):
        if os.getenv(key):
            env_values[key] = os.environ[key]

    checks = [
        check_python(),
        check_dependencies(),
        check_env_file(env_values, env_path),
        check_langfuse(env_values),
        check_required_paths(),
        check_secret_hygiene(),
        check_logs(env_values),
    ]
    if not skip_api:
        checks.append(check_api(base_url, required=require_api))
    return checks


def main() -> int:
    configure_utf8_stdio()
    parser = argparse.ArgumentParser(description="Preflight check môi trường và bài nộp Day 13")
    parser.add_argument("--base-url", default=BASE_URL, help="Base URL của API đang chạy")
    parser.add_argument(
        "--require-api",
        action="store_true",
        help="Coi việc không gọi được /health là lỗi chặn (mặc định chỉ cảnh báo)",
    )
    parser.add_argument("--skip-api", action="store_true", help="Bỏ qua hoàn toàn bước gọi /health")
    parser.add_argument("--json", action="store_true", help="In kết quả dạng JSON để lưu evidence")
    args = parser.parse_args()

    checks = run_checks(args.base_url, args.require_api, args.skip_api)
    blocking = [check for check in checks if check.required and not check.ok]
    warnings = [check for check in checks if not check.required and not check.ok]

    if args.json:
        print(
            json.dumps(
                {
                    "ready_to_submit": not blocking,
                    "blocking": len(blocking),
                    "warnings": len(warnings),
                    "checks": [
                        {
                            "name": check.name,
                            "ok": check.ok,
                            "required": check.required,
                            "detail": check.detail,
                        }
                        for check in checks
                    ],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1 if blocking else 0

    print("--- Preflight Day 13 (Setup & Integration) ---")
    for check in checks:
        print(f"{check.label} {check.name}: {check.detail}")

    print()
    if blocking:
        print(f"CHƯA SẴN SÀNG: {len(blocking)} hạng mục bắt buộc chưa đạt.")
        return 1
    if warnings:
        print(f"SẴN SÀNG (còn {len(warnings)} cảnh báo không chặn nộp bài).")
        return 0
    print("SẴN SÀNG: toàn bộ hạng mục đã đạt.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
