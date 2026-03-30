"""
Ansible-based checker for the RHCSA Examination Platform.
Runs per-task ansible-playbook checks and parses structured results.
"""
import json
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, List, Optional


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------
@dataclass
class CheckResult:
    status: str  # "PASS" | "FAIL" | "ERROR"
    summary: str
    timestamp: str
    details: List[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "status":    self.status,
            "summary":   self.summary,
            "timestamp": self.timestamp,
            "details":   self.details,
        }


def _now() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Core runner
# ---------------------------------------------------------------------------
PLAYBOOK_DIR = os.path.join(os.path.dirname(__file__), "ansible", "checks")

# Locate ansible-playbook in the same bin/ as the running Python interpreter.
# We invoke it as [sys.executable, script_path] to bypass the shebang entirely —
# this avoids [Errno 2] failures when the shebang path is stale (different
# machine, different username, or Python version change).
_PYTHON_BIN = os.path.dirname(os.path.abspath(sys.executable))
_VENV_ANSIBLE = os.path.join(_PYTHON_BIN, "ansible-playbook")


def _build_ansible_cmd(extra_args: list) -> list:
    """Return the command list for ansible-playbook, bypassing the shebang."""
    if os.path.isfile(_VENV_ANSIBLE):
        # Run via the current interpreter — shebang is irrelevant.
        return [sys.executable, _VENV_ANSIBLE] + extra_args
    # Fallback: hope ansible-playbook is on PATH.
    return ["ansible-playbook"] + extra_args


def run_ansible_check(
    checker_name: str,
    checker_vars: dict,
    inventory_str: str,
) -> CheckResult:
    """
    Write a temporary inventory, run the named ansible-playbook check,
    parse the ANSIBLE_CHECK_RESULTS line from stdout, and return a CheckResult.
    """
    playbook_path = os.path.join(PLAYBOOK_DIR, f"{checker_name}.yml")
    tmp = None
    try:
        # 1. Write inventory to a temp file
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".ini", delete=False, encoding="utf-8"
        )
        tmp.write(inventory_str)
        tmp.flush()
        tmp.close()

        # 2. Build command
        cmd = _build_ansible_cmd([
            "-i", tmp.name,
            "--extra-vars", json.dumps(checker_vars),
            playbook_path,
        ])

        # 3. Run
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
        )

        combined_output = result.stdout + result.stderr

        # 4 & 5. Parse ANSIBLE_CHECK_RESULTS line
        details = _parse_results(result.stdout)

        if details is None:
            return CheckResult(
                status="ERROR",
                summary="No ANSIBLE_CHECK_RESULTS found in playbook output.",
                timestamp=_now(),
                details=[{"name": "raw_output", "passed": False, "message": combined_output[-2000:]}],
            )

        # 6. Derive overall status
        all_passed = all(d.get("passed", False) for d in details)
        status = "PASS" if all_passed else "FAIL"
        passed_count = sum(1 for d in details if d.get("passed", False))
        summary = f"{passed_count}/{len(details)} checks passed."

        return CheckResult(
            status=status,
            summary=summary,
            timestamp=_now(),
            details=details,
        )

    except subprocess.TimeoutExpired:
        return CheckResult(
            status="ERROR",
            summary="Ansible playbook timed out after 60 seconds.",
            timestamp=_now(),
        )
    except Exception as e:
        return CheckResult(
            status="ERROR",
            summary=f"Unexpected error: {e}",
            timestamp=_now(),
        )
    finally:
        # 7. Always clean up temp file
        if tmp is not None:
            try:
                os.unlink(tmp.name)
            except OSError:
                pass


def _parse_results(stdout: str) -> Optional[list]:
    """
    Scan stdout for a line containing 'ANSIBLE_CHECK_RESULTS='.
    Ansible wraps the msg value in quotes, so the raw suffix may end with '"'.
    Strip that trailing quote before parsing.
    Returns the parsed JSON list, or None if not found / parse fails.
    """
    for line in stdout.splitlines():
        if "ANSIBLE_CHECK_RESULTS=" in line:
            _, _, raw = line.partition("ANSIBLE_CHECK_RESULTS=")
            raw = raw.strip().rstrip('"').replace('\\"', '"')
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                return None
    return None


# ---------------------------------------------------------------------------
# Checker factory
# ---------------------------------------------------------------------------
def get_checker(checker_name: str) -> Callable:
    """
    Return a callable that runs the named ansible check.
    Signature: fn(checker_vars: dict, inventory: str) -> CheckResult
    """
    return lambda checker_vars, inventory: run_ansible_check(
        checker_name, checker_vars, inventory
    )
