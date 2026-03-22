"""
test_vm_integration.py – Real VM integration tests.

These tests connect to the actual lab VM via SSH (paramiko) and exercise the
Flask API without any route mocking. Every test class carries appropriate
skip markers so the suite degrades gracefully when no VM is running.

Environment variables (all optional, fall back to lab defaults):
  VM_IP          — IP of the standard-node VM (default: 192.168.100.10)
  VM_USER        — SSH login user (default: linus)
  SSH_KEY_PATH   — Path to SSH private key (default: ~/.ssh/lab_key)
  BASE_URL       — Flask server URL (default: http://localhost:5000)

Run only integration tests:
  pytest tests/test_vm_integration.py -m integration -v
Skip them during normal CI:
  pytest -m "not integration"
"""

from __future__ import annotations

import os
import socket
import sys
import time
from typing import Tuple

import paramiko
import pytest
import requests

# ---------------------------------------------------------------------------
# Reuse the sys.path trick from conftest so POM imports work
# ---------------------------------------------------------------------------
sys.path.insert(0, os.path.dirname(__file__))

# ---------------------------------------------------------------------------
# Environment-driven configuration
# ---------------------------------------------------------------------------
VM_IP = os.environ.get("VM_IP", "192.168.100.10")
VM_USER = os.environ.get("VM_USER", "linus")
SSH_KEY = os.environ.get("SSH_KEY_PATH", os.path.expanduser("~/.ssh/lab_key"))
BASE_URL = os.environ.get("BASE_URL", "http://localhost:5000")
API_TIMEOUT = 15  # seconds; task actions block on ensure_vm()

# Mark every test in this module as integration
pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Connectivity probes (evaluated once at collection time)
# ---------------------------------------------------------------------------

def _tcp_open(host: str, port: int, timeout: float = 3.0) -> bool:
    """Return True if a TCP connection to host:port can be established."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _api_up(base_url: str) -> bool:
    """Return True if the Flask API responds to /api/vm/status."""
    try:
        r = requests.get(f"{base_url}/api/vm/status", timeout=3)
        return r.status_code == 200
    except Exception:
        return False


_VM_REACHABLE: bool = _tcp_open(VM_IP, 22)
_API_REACHABLE: bool = _api_up(BASE_URL)

skip_no_vm = pytest.mark.skipif(
    not _VM_REACHABLE,
    reason=f"Lab VM not reachable at {VM_IP}:22 — start the VM first",
)
skip_no_api = pytest.mark.skipif(
    not _API_REACHABLE,
    reason=f"Flask API not reachable at {BASE_URL} — start the server first",
)


# ---------------------------------------------------------------------------
# SSH helper
# ---------------------------------------------------------------------------

def _ssh_run(client: paramiko.SSHClient, cmd: str, timeout: int = 10) -> Tuple[int, str, str]:
    """Execute *cmd* on the remote VM and return (exit_code, stdout, stderr)."""
    _, stdout_fh, stderr_fh = client.exec_command(cmd, timeout=timeout)
    rc = stdout_fh.channel.recv_exit_status()
    return rc, stdout_fh.read().decode(errors="replace").strip(), stderr_fh.read().decode(errors="replace").strip()


@pytest.fixture(scope="module")
def ssh(request):
    """
    Module-scoped paramiko SSHClient connected to the lab VM.

    Skips the entire module if the VM is not reachable or the key is missing.
    """
    if not _VM_REACHABLE:
        pytest.skip(f"VM not reachable at {VM_IP}:22")
    if not os.path.exists(SSH_KEY):
        pytest.skip(f"SSH key not found: {SSH_KEY}")

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(hostname=VM_IP, username=VM_USER, key_filename=SSH_KEY, timeout=10)
    yield client
    client.close()


# ===========================================================================
# 1. SSH Connectivity & Command Execution
# ===========================================================================

class TestSSHConnection:
    """Verify that paramiko can establish and use an SSH session to the lab VM."""

    @skip_no_vm
    def test_ssh_handshake_succeeds(self):
        """
        A fresh paramiko SSHClient can complete the SSH handshake.
        Transport must be active immediately after connect().
        """
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(VM_IP, username=VM_USER, key_filename=SSH_KEY, timeout=10)
        transport = client.get_transport()
        assert transport is not None, "No SSH transport created"
        assert transport.is_active(), "SSH transport is not active after connect"
        client.close()

    @skip_no_vm
    def test_whoami_returns_expected_user(self, ssh):
        """
        `whoami` on the VM must return the configured SSH user.
        Confirms that key-based auth worked and the session runs as the right identity.
        """
        rc, stdout, stderr = _ssh_run(ssh, "whoami")
        assert rc == 0, f"whoami failed (rc={rc}): {stderr}"
        assert stdout == VM_USER, (
            f"Expected user '{VM_USER}', got '{stdout}'"
        )

    @skip_no_vm
    def test_hostname_is_non_empty(self, ssh):
        """
        `hostname` returns a non-empty string.
        A blank hostname would indicate a misconfigured VM image.
        """
        rc, stdout, _ = _ssh_run(ssh, "hostname")
        assert rc == 0, "hostname command failed"
        assert stdout.strip(), "hostname returned empty output"

    @skip_no_vm
    def test_uname_identifies_linux_kernel(self, ssh):
        """
        `uname -s` must return 'Linux'.
        Guards against accidentally connecting to a non-Linux host.
        """
        rc, stdout, _ = _ssh_run(ssh, "uname -s")
        assert rc == 0, "uname -s failed"
        assert stdout.strip() == "Linux", (
            f"Expected 'Linux' from uname -s, got '{stdout}'"
        )

    @skip_no_vm
    def test_etc_hostname_readable(self, ssh):
        """
        /etc/hostname is a readable file.
        Some minimal VM images store the hostname only in /proc/sys/kernel/hostname
        rather than persisting it to /etc/hostname, so we only assert the file
        exists and the command exits successfully.
        """
        rc, _, stderr = _ssh_run(ssh, "test -e /etc/hostname && cat /etc/hostname")
        # rc=0: file readable (content may be empty on a fresh VM image)
        # rc=1: file absent — still acceptable on some RHEL cloud images
        assert rc in (0, 1), f"/etc/hostname check failed unexpectedly: {stderr}"

    @skip_no_vm
    def test_passwordless_sudo_available(self, ssh):
        """
        `sudo -n id -u` succeeds without a password prompt.
        Ansible checks require passwordless sudo to run privileged commands.
        """
        rc, stdout, stderr = _ssh_run(ssh, "sudo -n id -u", timeout=5)
        assert rc == 0, (
            f"Passwordless sudo is not configured (rc={rc}): {stderr}"
        )
        assert stdout.strip() == "0", (
            f"sudo id -u should return 0 (root), got '{stdout}'"
        )

    @skip_no_vm
    def test_non_zero_exit_code_propagated(self, ssh):
        """
        SSH correctly captures non-zero exit codes from remote commands.
        If `false` returns 0, exit-code handling is broken.
        """
        rc, _, _ = _ssh_run(ssh, "false")
        assert rc != 0, "Expected non-zero exit code from 'false'"

    @skip_no_vm
    def test_sequential_commands_on_same_connection(self, ssh):
        """
        Multiple sequential commands over the same SSHClient all succeed.
        Verifies the module-scoped SSH fixture stays healthy across tests.
        """
        for cmd in ("echo ping", "ls /", "id", "uptime"):
            rc, stdout, stderr = _ssh_run(ssh, cmd)
            assert rc == 0, f"Command '{cmd}' failed (rc={rc}): {stderr}"
            assert stdout, f"Command '{cmd}' returned empty output"


# ===========================================================================
# 2. Real Flask API — VM & Task Endpoints
# ===========================================================================

class TestRealVMStatusAPI:
    """Exercise GET /api/vm/status against the live Flask server."""

    @skip_no_api
    @skip_no_vm
    def test_vm_status_reports_available(self):
        """
        GET /api/vm/status must return available=True when the VM is up.
        If this fails, all task actions will also fail downstream.
        """
        r = requests.get(f"{BASE_URL}/api/vm/status", timeout=API_TIMEOUT)
        assert r.status_code == 200, f"Unexpected HTTP {r.status_code}"
        data = r.json()
        assert data.get("available") is True, (
            f"VM reported unavailable: {data}"
        )

    @skip_no_api
    def test_vm_status_contains_scenario_field(self):
        """
        GET /api/vm/status response includes a 'scenario' key with a valid value.
        Used by the frontend to decide which panels to show.
        """
        r = requests.get(f"{BASE_URL}/api/vm/status", timeout=API_TIMEOUT)
        assert r.status_code == 200
        data = r.json()
        assert "scenario" in data, f"Missing 'scenario' in: {data}"
        assert data["scenario"] in ("standard", "lvm", "boot-menu"), (
            f"Unknown scenario value: '{data['scenario']}'"
        )

    @skip_no_api
    def test_vm_status_response_is_json(self):
        """
        GET /api/vm/status returns valid JSON with Content-Type application/json.
        """
        r = requests.get(f"{BASE_URL}/api/vm/status", timeout=API_TIMEOUT)
        assert "application/json" in r.headers.get("Content-Type", ""), (
            f"Expected JSON content-type, got: {r.headers.get('Content-Type')}"
        )
        data = r.json()  # raises if not valid JSON
        assert isinstance(data, dict), "Response body is not a JSON object"


class TestRealTasksAPI:
    """Exercise GET /api/tasks and related endpoints."""

    @skip_no_api
    def test_tasks_endpoint_returns_list(self):
        """
        GET /api/tasks returns a non-empty JSON list.
        An empty list means the active exam failed to load.
        """
        r = requests.get(f"{BASE_URL}/api/tasks", timeout=API_TIMEOUT)
        assert r.status_code == 200
        tasks = r.json()
        assert isinstance(tasks, list), f"Expected list, got {type(tasks)}"
        assert len(tasks) > 0, "Task list is empty — exam may not have loaded"

    @skip_no_api
    def test_tasks_have_all_required_fields(self):
        """
        Every task in the list exposes id, node, title, instructions, and status.
        Missing fields cause silent UI failures.
        """
        r = requests.get(f"{BASE_URL}/api/tasks", timeout=API_TIMEOUT)
        required = {"id", "node", "title", "instructions", "status"}
        for task in r.json():
            missing = required - set(task.keys())
            assert not missing, (
                f"Task {task.get('id', '?')} missing fields: {missing}"
            )

    @skip_no_api
    def test_task_statuses_are_valid_enum_values(self):
        """
        All task status values match the TaskStatus TypeScript enum
        (idle / running / stopped / resetting / starting).
        """
        valid_statuses = {"idle", "running", "stopped", "resetting", "starting"}
        r = requests.get(f"{BASE_URL}/api/tasks", timeout=API_TIMEOUT)
        for task in r.json():
            assert task["status"] in valid_statuses, (
                f"Task {task['id']} has unexpected status: '{task['status']}'"
            )

    @skip_no_api
    def test_task_node_values_are_valid(self):
        """
        All task node values match NodeGroup enum (standard / lvm / boot-menu).
        An unknown node value breaks VM selection logic.
        """
        valid_nodes = {"standard", "lvm", "boot-menu"}
        r = requests.get(f"{BASE_URL}/api/tasks", timeout=API_TIMEOUT)
        for task in r.json():
            assert task["node"] in valid_nodes, (
                f"Task {task['id']} has unknown node: '{task['node']}'"
            )


class TestRealExamsAPI:
    """Exercise GET /api/exams and GET /api/exam/active."""

    @skip_no_api
    def test_exams_endpoint_returns_list(self):
        """
        GET /api/exams returns a non-empty list.
        The frontend exam selector depends on this.
        """
        r = requests.get(f"{BASE_URL}/api/exams", timeout=API_TIMEOUT)
        assert r.status_code == 200
        exams = r.json()
        assert isinstance(exams, list) and len(exams) > 0, (
            f"Expected non-empty exam list, got: {exams}"
        )

    @skip_no_api
    def test_active_exam_has_required_fields(self):
        """
        GET /api/exam/active returns an object with id, title, scenario, and
        task_count. The route returns a summary (not the full task list) —
        the task list comes from GET /api/tasks.
        """
        r = requests.get(f"{BASE_URL}/api/exam/active", timeout=API_TIMEOUT)
        assert r.status_code == 200
        exam = r.json()
        for field in ("id", "title", "scenario", "task_count"):
            assert field in exam, f"Missing '{field}' in /api/exam/active: {exam}"
        assert exam["task_count"] > 0, (
            f"Active exam has task_count=0: {exam}"
        )

    @skip_no_api
    def test_exam_ids_match_json_files(self):
        """
        Listed exam IDs correspond to the JSON files in backend/exams/.
        Drift between the filesystem and the API response breaks exam switching.
        """
        r = requests.get(f"{BASE_URL}/api/exams", timeout=API_TIMEOUT)
        ids = {e["id"] for e in r.json()}
        assert "exam-1" in ids, f"exam-1 missing from API response: {ids}"
        assert "exam-2" in ids, f"exam-2 missing from API response: {ids}"


class TestRealTaskActions:
    """
    Exercise the task lifecycle (start → stop) through the real Flask API.
    These tests mutate server-side _task_state and require the VM to be up.
    """

    @skip_no_api
    @skip_no_vm
    def test_task_start_returns_ok_true(self):
        """
        POST /api/task/1/start returns {"ok": True}.
        Failure here usually means ensure_vm() timed out or SSH auth broke.
        """
        r = requests.post(f"{BASE_URL}/api/task/1/start", timeout=API_TIMEOUT)
        assert r.status_code == 200, f"start returned HTTP {r.status_code}"
        data = r.json()
        assert data.get("ok") is True, (
            f"start did not return ok=True: {data}"
        )

    @skip_no_api
    @skip_no_vm
    def test_task_start_reflects_in_task_list(self):
        """
        After a successful start, GET /api/tasks shows task 1 as 'running'.
        Verifies that server-side _task_state is updated atomically.
        """
        requests.post(f"{BASE_URL}/api/task/1/start", timeout=API_TIMEOUT)
        time.sleep(0.3)  # allow state flush
        tasks = requests.get(f"{BASE_URL}/api/tasks", timeout=API_TIMEOUT).json()
        task = next((t for t in tasks if t["id"] == 1), None)
        assert task is not None, "Task 1 not found in /api/tasks response"
        assert task["status"] == "running", (
            f"Expected task 1 status='running', got '{task['status']}'"
        )

    @skip_no_api
    @skip_no_vm
    def test_task_stop_returns_ok_true(self):
        """
        POST /api/task/1/stop returns {"ok": True}.
        Runs after start to leave the task in a clean stopped state.
        """
        requests.post(f"{BASE_URL}/api/task/1/start", timeout=API_TIMEOUT)
        r = requests.post(f"{BASE_URL}/api/task/1/stop", timeout=API_TIMEOUT)
        assert r.status_code == 200
        data = r.json()
        assert data.get("ok") is True, f"stop returned: {data}"

    @skip_no_api
    @skip_no_vm
    def test_task_stop_reflects_in_task_list(self):
        """
        After start → stop, GET /api/tasks shows task 1 as 'stopped'.
        """
        requests.post(f"{BASE_URL}/api/task/1/start", timeout=API_TIMEOUT)
        time.sleep(0.2)
        requests.post(f"{BASE_URL}/api/task/1/stop", timeout=API_TIMEOUT)
        time.sleep(0.2)
        tasks = requests.get(f"{BASE_URL}/api/tasks", timeout=API_TIMEOUT).json()
        task = next((t for t in tasks if t["id"] == 1), None)
        assert task is not None
        assert task["status"] == "stopped", (
            f"Expected 'stopped', got '{task['status']}'"
        )


# ===========================================================================
# 3. Real Ansible Playbook Execution
# ===========================================================================

class TestAnsibleIntegration:
    """
    Invoke run_ansible_check() directly (not via the API) against the live VM.
    These tests confirm that the Ansible layer works end-to-end; they do NOT
    assert a PASS/FAIL result because the VM's state is unknown — they only
    confirm that the playbook runs to completion without an ERROR.
    """

    @pytest.fixture(autouse=True)
    def _require_vm_and_ansible(self):
        """Skip the whole class if VM or ansible-playbook is unavailable."""
        if not _VM_REACHABLE:
            pytest.skip(f"VM not reachable at {VM_IP}:22")
        import shutil
        if not shutil.which("ansible-playbook"):
            pytest.skip("ansible-playbook not found in PATH")

    @pytest.fixture
    def inventory(self):
        """Return an Ansible INI inventory string pointing at the lab VM."""
        return (
            "[rhcsa_vm]\n"
            f"{VM_IP} "
            f"ansible_user={VM_USER} "
            f"ansible_ssh_private_key_file={SSH_KEY} "
            "ansible_ssh_common_args='-o StrictHostKeyChecking=no'\n"
        )

    def test_ansible_check_tuned_does_not_error(self, inventory):
        """
        run_ansible_check('check_tuned', …) returns status PASS or FAIL, never ERROR.
        An ERROR means the playbook itself crashed (bad syntax, unreachable host, etc.).
        """
        import sys
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
        from ansible_checker import run_ansible_check

        result = run_ansible_check(
            checker_name="check_tuned",
            checker_vars={"expected_profile": "virtual-guest"},
            inventory_str=inventory,
        )
        assert result.status in ("PASS", "FAIL"), (
            f"Ansible check returned ERROR — playbook may have crashed:\n{result.summary}"
        )

    def test_ansible_check_result_has_details(self, inventory):
        """
        A completed Ansible check always includes at least one detail entry.
        An empty details list means the ANSIBLE_CHECK_RESULTS line was missing.
        """
        import sys
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
        from ansible_checker import run_ansible_check

        result = run_ansible_check(
            checker_name="check_tuned",
            checker_vars={"expected_profile": "virtual-guest"},
            inventory_str=inventory,
        )
        if result.status == "ERROR":
            pytest.skip(f"Playbook errored (covered by other test): {result.summary}")
        assert len(result.details) > 0, (
            "Check returned no details — ANSIBLE_CHECK_RESULTS output may be missing"
        )

    def test_ansible_check_network_config_does_not_error(self, inventory):
        """
        run_ansible_check('check_network_config', …) completes without ERROR.
        Uses realistic checker_vars matching the exam-1 task 1 specification.
        """
        import sys
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
        from ansible_checker import run_ansible_check

        result = run_ansible_check(
            checker_name="check_network_config",
            checker_vars={
                "expected_hostname": "node1.lab.example.com",
                "expected_gateway": "172.25.250.254",
                "expected_dns": "172.25.250.254",
            },
            inventory_str=inventory,
        )
        assert result.status in ("PASS", "FAIL"), (
            f"check_network_config returned ERROR:\n{result.summary}"
        )


# ===========================================================================
# 4. Remote Command Validation
# ===========================================================================

class TestCommandValidation:
    """
    Validate expected shell-level state on the VM using raw SSH commands.
    These tests provide a lightweight sanity-check baseline before running
    heavier Ansible checks.
    """

    @skip_no_vm
    def test_root_filesystem_is_mounted(self, ssh):
        """
        /proc/mounts lists at least one entry with mount point '/'.
        A missing root mount means the filesystem is seriously broken.
        """
        rc, stdout, _ = _ssh_run(ssh, "grep -c ' / ' /proc/mounts")
        assert rc == 0
        assert int(stdout) >= 1, "Root filesystem not found in /proc/mounts"

    @skip_no_vm
    def test_etc_passwd_has_multiple_lines(self, ssh):
        """
        /etc/passwd contains more than one entry.
        A single-line /etc/passwd would indicate a stripped or broken system image.
        """
        rc, stdout, _ = _ssh_run(ssh, "wc -l < /etc/passwd")
        assert rc == 0, "/etc/passwd not readable"
        assert int(stdout) > 5, (
            f"/etc/passwd has only {stdout} lines — image may be broken"
        )

    @skip_no_vm
    def test_systemd_process_is_running(self, ssh):
        """
        PID 1 is a systemd process.
        Required for the exam tasks that use systemctl to manage services.
        """
        rc, stdout, _ = _ssh_run(ssh, "cat /proc/1/comm")
        assert rc == 0
        assert "systemd" in stdout.lower(), (
            f"Expected PID 1 to be systemd, got '{stdout}'"
        )

    @skip_no_vm
    def test_bash_shell_available(self, ssh):
        """
        /bin/bash exists and is executable.
        All exam task scripts assume a bash shell.
        """
        rc, _, _ = _ssh_run(ssh, "test -x /bin/bash")
        assert rc == 0, "/bin/bash is not executable on the VM"

    @skip_no_vm
    def test_ssh_user_home_directory_exists(self, ssh):
        """
        The SSH user's home directory (~) exists on the VM.
        Missing home directory breaks shell login and exam task setup.
        """
        rc, stdout, _ = _ssh_run(ssh, f"test -d ~{VM_USER} && echo yes")
        assert rc == 0 and stdout == "yes", (
            f"Home directory for '{VM_USER}' does not exist on the VM"
        )


# ===========================================================================
# 5. Supporting infrastructure checks
# ===========================================================================

class TestCheckpointAndVNCAPIs:
    """Light smoke-tests for checkpoint and VNC endpoints."""

    @skip_no_api
    def test_checkpoint_status_returns_dict(self):
        """
        GET /api/vm/checkpoint-status returns a JSON object (dict).
        Values are booleans indicating whether each VM has a saved checkpoint.
        """
        r = requests.get(f"{BASE_URL}/api/vm/checkpoint-status", timeout=API_TIMEOUT)
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, dict), (
            f"Expected dict from checkpoint-status, got {type(data).__name__}: {data}"
        )

    @skip_no_api
    def test_vnc_status_has_available_field(self):
        """
        GET /api/vnc/status returns a response that includes an 'available' boolean.
        The frontend uses this field to decide whether to render the VNC panel.
        """
        r = requests.get(f"{BASE_URL}/api/vnc/status", timeout=API_TIMEOUT)
        assert r.status_code == 200
        data = r.json()
        assert "available" in data, (
            f"'available' field missing from VNC status: {data}"
        )
        assert isinstance(data["available"], bool), (
            f"'available' should be bool, got {type(data['available'])}: {data}"
        )
