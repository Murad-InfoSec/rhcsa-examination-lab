"""
VM configuration for the RHCSA Examination Platform.
Reads ACTIVE_SCENARIO and SSH_KEY_PATH from environment to determine
which libvirt VM to target for SSH, Ansible, and VNC operations.
"""
import os
import subprocess
from typing import Optional

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
SSH_USER = "linus"

SCENARIOS = {
    "standard":  {"ip": "192.168.100.10", "hostname": "standard-001"},
    "lvm":       {"ip": "192.168.100.12", "hostname": "lvm-001"},
    "boot-menu": {"ip": "192.168.100.11", "hostname": "boot-menu-001"},
}

DEFAULT_SCENARIO = "standard"
DEFAULT_KEY_PATH  = os.path.expanduser("~/.ssh/lab_key")
SNAPSHOT_NAME     = "initial"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def get_active_vm_config(node: str = None) -> dict:
    """
    Return full config for the active scenario.
    If node is provided it is used directly as the scenario key,
    allowing app.py to pass task['node'] without touching env vars.
    """
    if node and node in SCENARIOS:
        scenario = node
    else:
        scenario = os.environ.get("ACTIVE_SCENARIO", DEFAULT_SCENARIO)
        if scenario not in SCENARIOS:
            scenario = DEFAULT_SCENARIO
    key_path = os.environ.get("SSH_KEY_PATH", DEFAULT_KEY_PATH)
    info = SCENARIOS[scenario]
    return {
        "scenario": scenario,
        "ip":       info["ip"],
        "hostname": info["hostname"],
        "user":     SSH_USER,
        "key_path": key_path,
    }


def get_vm_hostname() -> str:
    """Return the libvirt domain name for the active scenario."""
    return get_active_vm_config()["hostname"]


def get_ansible_inventory() -> str:
    """Return an Ansible INI inventory string targeting the active VM."""
    cfg = get_active_vm_config()
    return (
        "[rhcsa_vm]\n"
        f"{cfg['ip']} "
        f"ansible_user={cfg['user']} "
        f"ansible_ssh_private_key_file={cfg['key_path']} "
        f"ansible_ssh_common_args='-o StrictHostKeyChecking=no'\n"
    )


def get_vnc_port() -> Optional[int]:
    """
    Run `virsh vncdisplay <hostname>` and return the TCP port number.
    Display ":1" maps to port 5900+1 = 5901. Returns None on failure.
    """
    hostname = get_vm_hostname()
    try:
        result = subprocess.run(
            ["virsh", "vncdisplay", hostname],
            capture_output=True,
            text=True,
            timeout=5,
        )
        display = result.stdout.strip()  # e.g. ":1" or "127.0.0.1:0"
        if result.returncode == 0 and ":" in display:
            return 5900 + int(display.rsplit(":", 1)[-1])
    except Exception:
        pass
    return None
