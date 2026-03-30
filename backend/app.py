"""
Flask + Flask-SocketIO backend for RHCSA Examination Platform.
Serves built Vite React frontend from frontend_dist/ and provides REST + Socket.IO API.
"""
import atexit
import os
import signal
import sys
import subprocess
import threading
import time

import logging
import socket

import paramiko

logging.getLogger("paramiko").setLevel(logging.CRITICAL)

from flask import Flask, jsonify, request, send_from_directory
from flask_socketio import SocketIO, emit, join_room

from vm_config import get_active_vm_config, get_vm_hostname, get_ansible_inventory, get_vnc_port, SNAPSHOT_NAME
from exam_loader import get_active_exam, list_exams, load_exam
from ansible_checker import run_ansible_check, get_checker

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
FRONTEND_DIST = os.path.join(os.path.dirname(__file__), "frontend_dist")
PROJECT_ROOT  = os.environ.get("PROJECT_ROOT") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PORT = 5000
SAVE_DIR = os.path.join(os.path.dirname(__file__), "vm_saves")

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret")
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

# Active exam and in-memory task state
_active_exam = get_active_exam()
_task_state: dict[int, dict] = {}
for t in _active_exam["tasks"]:
    _task_state[t["id"]] = {"status": "idle", "lastCheck": None}

# Terminal sessions: task_id -> (paramiko Channel, paramiko SSHClient)
# Both are stored to prevent the SSHClient from being garbage-collected,
# which would close the transport and kill the channel.
_terminal_sessions: dict[str, tuple] = {}
_terminal_lock = threading.Lock()

# VNC proxy
_vnc_proxy_process = None
_vnc_proxy_lock = threading.Lock()
VNC_WS_PORT = 6080

# VM reset lock + version counter.
# Every reset request atomically grabs the next version number.
# When it acquires the lock, it checks if it is still the latest version.
# If a newer request arrived while this one was waiting, this one skips — so
# only the last-requested reset ever runs, no matter how many are queued.
_reset_lock = threading.Lock()
_reset_version = 0
_reset_version_lock = threading.Lock()

# Connected Socket.IO client tracking (for web-UI-closed shutdown)
_connected_sids: set[str] = set()
_connected_lock = threading.Lock()
_idle_shutdown_timer: threading.Timer | None = None
_IDLE_SHUTDOWN_DELAY = 60  # seconds after last client disconnects


# ---------------------------------------------------------------------------
# Shutdown all VMs (called on process exit or when web UI is closed)
# ---------------------------------------------------------------------------
def _shutdown_all_vms() -> None:
    """Destroy every running libvirt VM domain."""
    from vm_config import SCENARIOS as _ALL
    stop_vnc_proxy()
    for _s, _info in _ALL.items():
        h = _info["hostname"]
        if _vm_is_running(h):
            print(f"[shutdown] stopping VM {h}", flush=True)
            subprocess.run(["virsh", "destroy", h], capture_output=True, timeout=10)


def _register_shutdown_hooks() -> None:
    atexit.register(_shutdown_all_vms)

    def _sig_handler(signum, frame):
        _shutdown_all_vms()
        sys.exit(0)

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            signal.signal(sig, _sig_handler)
        except (OSError, ValueError):
            pass  # can't set signals in non-main thread


# ---------------------------------------------------------------------------
# SSH / VM helpers
# ---------------------------------------------------------------------------
def _ssh_connect(cfg: dict = None) -> paramiko.SSHClient:
    """Open an SSH connection to the given VM config (or active VM if None). Caller must close."""
    if cfg is None:
        cfg = get_active_vm_config()
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        hostname=cfg["ip"],
        username=cfg["user"],
        key_filename=cfg["key_path"],
        timeout=10,
    )
    return client


def _inject_task_deps(task: dict, cfg: dict) -> tuple[bool, str]:
    """
    Rsync each deps.paths entry from the host into the VM over SSH.
    host path is relative to PROJECT_ROOT; guest path is absolute on the VM.
    No-op when the task has no deps or an empty paths list.
    """
    paths = task.get("deps", {}).get("paths", [])
    if not paths:
        return True, ""
    ssh_opts = (
        f"ssh -i {cfg['key_path']}"
        " -o StrictHostKeyChecking=no"
        " -o UserKnownHostsFile=/dev/null"
    )
    for entry in paths:
        guest_path = entry["guest"]
        # Pre-create the destination with sudo — /home is root-owned 755.
        try:
            ssh = _ssh_connect(cfg)
            _, stdout, _ = ssh.exec_command(
                f"sudo mkdir -p {guest_path} && sudo chown {cfg['user']}:{cfg['user']} {guest_path}"
            )
            stdout.channel.recv_exit_status()
            ssh.close()
        except Exception as e:
            return False, f"Failed to create guest dir {guest_path}: {e}"

        host_src  = os.path.join(PROJECT_ROOT, entry["host"]) + "/"
        guest_dst = f"{cfg['user']}@{cfg['ip']}:{guest_path}/"
        cmd = [
            "rsync", "-az",
            "-e", ssh_opts,
            host_src,
            guest_dst,
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            if result.returncode != 0:
                return False, f"rsync failed ({entry['host']} → {guest_path}): {result.stderr.strip()}"
        except Exception as e:
            return False, str(e)
    return True, ""


def ensure_vm() -> tuple[bool, str]:
    """Wait up to 120 s for the VM to be reachable over SSH (polls every 0.5 s).
    For boot-menu VMs (VNC-only), checks virsh state instead of SSH."""
    cfg = get_active_vm_config()
    if cfg["scenario"] == "boot-menu":
        return (_vm_is_running(cfg["hostname"]), "") if _vm_is_running(cfg["hostname"]) else (False, "boot-menu VM is not running")
    deadline = time.time() + 120
    last_err = "timeout waiting for VM"
    while time.time() < deadline:
        try:
            with socket.create_connection((cfg["ip"], 22), timeout=1):
                pass
        except OSError:
            time.sleep(0.5)
            continue
        try:
            ssh = _ssh_connect(cfg)
            ssh.close()
            return True, ""
        except Exception as e:
            last_err = str(e)
            time.sleep(0.5)
    return False, last_err


def stop_vm() -> tuple[bool, str]:
    """Destroy the active running VM and wait for it to reach shut-off state."""
    cfg = get_active_vm_config()
    hostname = cfg["hostname"]
    if not _vm_is_running(hostname):
        return True, ""
    result = subprocess.run(["virsh", "destroy", hostname], capture_output=True, text=True, timeout=10)
    if result.returncode != 0:
        return False, result.stderr.strip()
    if not _wait_for_shutdown(hostname):
        return False, f"VM {hostname} did not reach shut-off state within 10s"
    return True, ""


def _save_path(hostname: str) -> str:
    return os.path.join(SAVE_DIR, f"{hostname}.save")


def _wait_for_shutdown(hostname: str, timeout: int = 10) -> bool:
    """Poll until the domain reaches shut-off state. Returns True if successful."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        result = subprocess.run(
            ["virsh", "domstate", hostname], capture_output=True, text=True, timeout=5
        )
        if result.stdout.strip() == "shut off":
            return True
        time.sleep(0.5)
    return False


def _get_vol_capacity(vol_name: str) -> str:
    """Return the capacity of a libvirt pool volume as a string like '20G'."""
    result = subprocess.run(
        ["virsh", "vol-info", vol_name, "--pool", "default"],
        capture_output=True, text=True, timeout=10,
    )
    for line in result.stdout.splitlines():
        if line.startswith("Capacity:"):
            # e.g. "Capacity:       20.00 GiB"
            parts = line.split()
            size = float(parts[1])
            unit = parts[2].rstrip("iB").upper()  # GiB→G, MiB→M
            return f"{int(size)}{unit}"
    return "10G"  # safe fallback


def _recreate_overlay(scenario: str, hostname: str) -> None:
    """Drop and recreate the qcow2 overlay, giving the VM a clean disk slate."""
    snap_vol = f"{hostname}-snap.qcow2"
    back_vol = f"{scenario}-disk.qcow2"
    del_result = subprocess.run(
        ["virsh", "vol-delete", snap_vol, "--pool", "default"],
        capture_output=True, text=True, timeout=10,
    )
    if del_result.returncode != 0 and "not found" not in del_result.stderr.lower():
        raise RuntimeError(f"vol-delete {snap_vol} failed: {del_result.stderr.strip()}")
    capacity = _get_vol_capacity(back_vol)
    subprocess.run(
        ["virsh", "vol-create-as", "default", snap_vol, capacity,
         "--format", "qcow2",
         "--backing-vol", back_vol,
         "--backing-vol-format", "qcow2"],
        capture_output=True, text=True, timeout=30, check=True,
    )


def _reset_vm_for(scenario: str, hostname: str) -> tuple[bool, str]:
    """
    Fast path  (~1 s): destroy + wipe overlay + virsh restore from save file.
    Cold path (~5 s): destroy + wipe overlay + virsh start (full boot).

    Uses a version counter so that only the *latest* queued reset actually runs.
    If N resets are waiting on _reset_lock, each one on acquiring checks whether
    a newer request arrived while it was waiting — if so, it returns immediately,
    letting the newest request do the real work.
    """
    global _reset_version
    with _reset_version_lock:
        _reset_version += 1
        my_version = _reset_version

    with _reset_lock:
        with _reset_version_lock:
            current = _reset_version
        if my_version < current:
            return True, ""  # a newer reset will handle it

        save = _save_path(hostname)
        try:
            subprocess.run(["virsh", "destroy", hostname], capture_output=True, timeout=10)
            _recreate_overlay(scenario, hostname)
            if os.path.exists(save):
                result = subprocess.run(["virsh", "restore", save],
                                        capture_output=True, text=True, timeout=30)
            else:
                result = subprocess.run(["virsh", "start", hostname],
                                        capture_output=True, text=True, timeout=10)
            if result.returncode != 0:
                return False, result.stderr.strip()
            return True, ""
        except Exception as e:
            return False, str(e)


def reset_vm() -> tuple[bool, str]:
    cfg = get_active_vm_config()
    return _reset_vm_for(cfg["scenario"], cfg["hostname"])


def save_checkpoint(hostname: str = None) -> tuple[bool, str]:
    """
    Save the current running VM state as the revert checkpoint.
    The VM is saved (paused), overlay is recreated clean, then restored —
    so the VM keeps running and the checkpoint captures the pristine state.
    """
    os.makedirs(SAVE_DIR, exist_ok=True)
    if hostname is None:
        hostname = get_active_vm_config()["hostname"]
    scenario = next(
        (s for s, info in __import__("vm_config").SCENARIOS.items()
         if info["hostname"] == hostname), None
    )
    save = _save_path(hostname)
    try:
        result = subprocess.run(["virsh", "save", hostname, save],
                                capture_output=True, text=True, timeout=60)
        if result.returncode != 0:
            return False, result.stderr.strip()
        if scenario:
            try:
                _recreate_overlay(scenario, hostname)
            except Exception as e:
                # VM is paused on disk; recover by resuming the original state.
                subprocess.run(["virsh", "restore", save], capture_output=True, timeout=30)
                return False, f"overlay recreation failed (VM resumed): {e}"
        result = subprocess.run(["virsh", "restore", save],
                                capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            return False, f"restore after save failed: {result.stderr.strip()}"
        return True, ""
    except Exception as e:
        return False, str(e)


def _shutdown_vm(hostname: str) -> None:
    """Destroy a running VM domain, ignoring errors (e.g. already stopped)."""
    subprocess.run(["virsh", "destroy", hostname], capture_output=True, timeout=10)


def _vm_is_running(hostname: str) -> bool:
    """Return True if the libvirt domain is in the running state."""
    result = subprocess.run(
        ["virsh", "domstate", hostname], capture_output=True, text=True, timeout=5
    )
    return result.stdout.strip() == "running"


def _start_vm(hostname: str, scenario: str) -> tuple[bool, str]:
    """Start a stopped VM from its checkpoint save file, or cold-boot if none exists."""
    save = _save_path(hostname)
    try:
        if os.path.exists(save):
            result = subprocess.run(["virsh", "restore", save],
                                    capture_output=True, text=True, timeout=30)
        else:
            result = subprocess.run(["virsh", "start", hostname],
                                    capture_output=True, text=True, timeout=10)
        if result.returncode != 0:
            return False, result.stderr.strip()
        return True, ""
    except Exception as e:
        return False, str(e)


def switch_vm(scenario: str) -> tuple[bool, str]:
    """Switch to a different scenario VM.
    If the target VM is already stopped, just start it.
    If it is running, reset it to its checkpoint for a clean slate.
    Always shuts down the previously active VM first.
    """
    global _task_state
    stop_vnc_proxy()

    # Shut down ALL running VMs that are not the target.
    from vm_config import SCENARIOS as _ALL_SCENARIOS
    for _s, _info in _ALL_SCENARIOS.items():
        if _s != scenario and _vm_is_running(_info["hostname"]):
            _shutdown_vm(_info["hostname"])

    cfg      = get_active_vm_config(node=scenario)
    hostname = cfg["hostname"]

    if _vm_is_running(hostname):
        # VM already up — reset it to a clean state.
        ok, err = _reset_vm_for(scenario, hostname)
    else:
        # VM is down — just start it, no need to destroy/recreate overlay.
        ok, err = _start_vm(hostname, scenario)
    if not ok:
        return False, err

    os.environ["ACTIVE_SCENARIO"] = scenario
    for t in _active_exam["tasks"]:
        if t["node"] == scenario:
            _task_state[t["id"]] = {"status": "idle", "lastCheck": None}
    if scenario == "boot-menu":
        start_vnc_proxy()
    return True, ""


# ---------------------------------------------------------------------------
# VNC proxy helpers
# ---------------------------------------------------------------------------
def _vnc_proxy_port_bound() -> bool:
    """Return True if something is already listening on VNC_WS_PORT."""
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('127.0.0.1', VNC_WS_PORT)) == 0


def start_vnc_proxy() -> tuple[bool, str]:
    global _vnc_proxy_process
    with _vnc_proxy_lock:
        # If our tracked process is alive, nothing to do.
        if _vnc_proxy_process and _vnc_proxy_process.poll() is None:
            return True, ""
        # If something external is already listening, adopt it as running.
        if _vnc_proxy_port_bound():
            return True, ""
        vnc_port = get_vnc_port()
        if vnc_port is None:
            return False, "Could not determine VNC port from virsh"
        try:
            _vnc_proxy_process = subprocess.Popen([
                "websockify", str(VNC_WS_PORT), f"localhost:{vnc_port}"
            ])
            return True, ""
        except Exception as e:
            return False, str(e)


def stop_vnc_proxy() -> None:
    global _vnc_proxy_process
    with _vnc_proxy_lock:
        if _vnc_proxy_process:
            _vnc_proxy_process.terminate()
            _vnc_proxy_process = None
        # Kill any external websockify on the same port.
        subprocess.run(
            ["pkill", "-f", f"websockify.*{VNC_WS_PORT}"],
            capture_output=True
        )


# ---------------------------------------------------------------------------
# REST API
# ---------------------------------------------------------------------------
@app.route("/api/vm/status")
def vm_status():
    cfg = get_active_vm_config()
    # Quick non-blocking check — don't wait 30 s on every status poll.
    if cfg["scenario"] == "boot-menu":
        ok = _vm_is_running(cfg["hostname"])
        err = "" if ok else "boot-menu VM is not running"
    else:
        ok, err = False, "VM unreachable"
        try:
            with socket.create_connection((cfg["ip"], 22), timeout=3):
                ok, err = True, ""
        except OSError as e:
            err = str(e)
    out = {
        "available": ok,
        "scenario":  cfg["scenario"],
        "ip":        cfg["ip"],
    }
    if not ok:
        out["error"] = err
    return jsonify(out)


@app.route("/api/vm/current")
def vm_current():
    cfg = get_active_vm_config()
    has_snapshot = False
    try:
        result = subprocess.run(
            ["virsh", "snapshot-list", cfg["hostname"], "--name"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            has_snapshot = SNAPSHOT_NAME in result.stdout.splitlines()
    except Exception:
        pass
    return jsonify({
        "scenario": cfg["scenario"],
        "hostname": cfg["hostname"],
        "ip":       cfg["ip"],
        "snapshot": SNAPSHOT_NAME if has_snapshot else None,
    })


@app.route("/api/tasks")
def api_tasks():
    result = []
    for t in _active_exam["tasks"]:
        tid = t["id"]
        state = _task_state.get(tid, {"status": "idle", "lastCheck": None})
        result.append({
            "id":           t["id"],
            "node":         t["node"],
            "title":        t["title"],
            "instructions": t.get("instructions", ""),
            "status":       state["status"],
            "lastCheck":    state["lastCheck"],
        })
    return jsonify(result)


@app.route("/api/task/<int:task_id>/start", methods=["POST"])
def task_start(task_id):
    task = next((t for t in _active_exam["tasks"] if t["id"] == task_id), None)
    if task is None:
        return jsonify({"ok": False, "error": f"Task {task_id} not found"}), 404
    current_scenario = os.environ.get("ACTIVE_SCENARIO", "standard")
    if task["node"] != current_scenario:
        ok, err = switch_vm(task["node"])
        if not ok:
            return jsonify({"ok": False, "error": f"VM switch failed: {err}"}), 500
    # boot-menu is VNC-only — start the VM if not running, then start the proxy.
    if task["node"] == "boot-menu":
        hostname = get_active_vm_config()["hostname"]
        if not _vm_is_running(hostname):
            ok, err = _start_vm(hostname, "boot-menu")
            if not ok:
                return jsonify({"ok": False, "error": f"Failed to start boot-menu VM: {err}"}), 500
        start_vnc_proxy()
    else:
        hostname = get_active_vm_config(node=task["node"])["hostname"]
        if not _vm_is_running(hostname):
            ok, err = _start_vm(hostname, task["node"])
            if not ok:
                return jsonify({"ok": False, "error": f"Failed to start VM: {err}"}), 500
        ok, err = ensure_vm()
        if not ok:
            return jsonify({"ok": False, "error": err}), 500
        cfg = get_active_vm_config(node=task["node"])
        ok, err = _inject_task_deps(task, cfg)
        if not ok:
            return jsonify({"ok": False, "error": f"Dep injection failed: {err}"}), 500
    if task_id not in _task_state:
        _task_state[task_id] = {"status": "idle", "lastCheck": None}
    _task_state[task_id]["status"] = "running"
    return jsonify({"ok": True, "status": "running"})


@app.route("/api/task/<int:task_id>/stop", methods=["POST"])
def task_stop(task_id):
    _close_terminal(str(task_id))
    stop_vnc_proxy()
    ok, err = stop_vm()
    if not ok:
        return jsonify({"ok": False, "error": err}), 500
    _task_state[task_id]["status"] = "stopped"
    return jsonify({"ok": True, "status": "stopped"})


@app.route("/api/task/<int:task_id>/reset", methods=["POST"])
def task_reset(task_id):
    _close_terminal(str(task_id))
    stop_vnc_proxy()
    ok, err = reset_vm()
    if not ok:
        return jsonify({"ok": False, "error": err}), 500
    cfg = get_active_vm_config()
    if cfg["scenario"] == "boot-menu":
        start_vnc_proxy()
    else:
        # After virsh restore the VM resumes instantly — use a short 10s timeout
        # rather than the full 120s ensure_vm() to confirm SSH is up without
        # adding noticeable latency on the normal (checkpoint) path.
        deadline = time.time() + 10
        ssh_ready = False
        while time.time() < deadline:
            try:
                with socket.create_connection((cfg["ip"], 22), timeout=2):
                    ssh_ready = True
                    break
            except OSError:
                time.sleep(0.5)
        if not ssh_ready:
            return jsonify({"ok": False, "error": "VM reset ok but SSH port not ready within 10s"}), 500
    _task_state[task_id]["status"] = "running"
    return jsonify({"ok": True, "status": "running"})


@app.route("/api/task/<int:task_id>/check", methods=["POST"])
def task_check(task_id):
    task = next((t for t in _active_exam["tasks"] if t["id"] == task_id), None)
    if task is None:
        return jsonify({"status": "ERROR", "summary": f"Task {task_id} not found in active exam",
                        "timestamp": __now(), "details": []}), 404
    ok, err = ensure_vm()
    if not ok:
        return jsonify({"status": "ERROR", "summary": f"VM not reachable: {err}",
                        "timestamp": __now(), "details": []}), 200
    result = run_ansible_check(task["checker"], task["checker_vars"], get_ansible_inventory())
    result_dict = result.to_dict()
    _task_state[task_id]["lastCheck"] = result_dict
    return jsonify(result_dict)


@app.route("/api/exams")
def api_exams():
    return jsonify(list_exams())


@app.route("/api/exam/active")
def api_exam_active():
    return jsonify({
        "id":          _active_exam["id"],
        "title":       _active_exam["title"],
        "scenario":    _active_exam.get("scenario", ""),
        "task_count":  len(_active_exam["tasks"]),
    })


@app.route("/api/exam/set/<exam_id>", methods=["POST"])
def api_exam_set(exam_id):
    global _active_exam, _task_state
    try:
        exam = load_exam(exam_id)
    except FileNotFoundError as e:
        return jsonify({"ok": False, "error": str(e)}), 404
    _active_exam = exam
    _task_state = {t["id"]: {"status": "idle", "lastCheck": None} for t in exam["tasks"]}
    return jsonify({"ok": True, "exam_id": exam_id})



@app.route("/api/task/<int:task_id>/prepare", methods=["POST"])
def task_prepare(task_id):
    """Reset the VM for a task back to its clean base snapshot.
    Called automatically when the user selects a different task.
    Sets status back to idle (not running) so the user still needs to click Start.
    """
    task = next((t for t in _active_exam["tasks"] if t["id"] == task_id), None)
    if task is None:
        return jsonify({"ok": False, "error": f"Task {task_id} not found"}), 404
    _close_terminal(str(task_id))
    stop_vnc_proxy()
    current_scenario = os.environ.get("ACTIVE_SCENARIO", "standard")
    if task["node"] != current_scenario:
        ok, err = switch_vm(task["node"])
    else:
        ok, err = reset_vm()
    if not ok:
        return jsonify({"ok": False, "error": err}), 500
    if task["node"] == "boot-menu":
        start_vnc_proxy()
    if task_id not in _task_state:
        _task_state[task_id] = {"status": "idle", "lastCheck": None}
    _task_state[task_id]["status"] = "idle"
    return jsonify({"ok": True, "status": "idle"})


@app.route("/api/vm/save-checkpoint", methods=["POST"])
def api_save_checkpoint():
    hostname = request.json.get("hostname") if request.is_json else None
    ok, err = save_checkpoint(hostname)
    if not ok:
        return jsonify({"ok": False, "error": err}), 500
    return jsonify({"ok": True})


@app.route("/api/vm/checkpoint-status")
def api_checkpoint_status():
    import vm_config as _vc
    result = {}
    for scenario, info in _vc.SCENARIOS.items():
        h = info["hostname"]
        result[h] = os.path.exists(_save_path(h))
    return jsonify(result)


@app.route("/api/vnc/status")
def vnc_status():
    cfg = get_active_vm_config()
    if cfg["scenario"] != "boot-menu":
        return jsonify({"available": False})
    vnc_port = get_vnc_port()
    proxy_running = _vnc_proxy_port_bound()
    # Auto-start the proxy as soon as the VM's VNC port is ready.
    if vnc_port is not None and not proxy_running:
        proxy_running, _ = start_vnc_proxy()
        proxy_running = _vnc_proxy_port_bound()
    return jsonify({
        "available": vnc_port is not None and proxy_running,
        "ws_port":   VNC_WS_PORT,
        "vnc_port":  vnc_port,
        "scenario":  cfg["scenario"],
    })


@app.route("/api/vnc/start", methods=["POST"])
def vnc_start():
    ok, err = start_vnc_proxy()
    return jsonify({"ok": ok, "ws_port": VNC_WS_PORT, "error": err})


@app.route("/api/vnc/stop", methods=["POST"])
def vnc_stop():
    stop_vnc_proxy()
    return jsonify({"ok": True})


def __now():
    from datetime import datetime, timezone
    return datetime.now(tz=timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Static (SPA) – serve frontend_dist
# ---------------------------------------------------------------------------
@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def serve(path):
    # Serve static files from frontend_dist
    if path:
        full_path = os.path.join(FRONTEND_DIST, path)
        if os.path.isfile(full_path):
            return send_from_directory(FRONTEND_DIST, path)
        if os.path.isdir(full_path):
            idx = os.path.join(full_path, "index.html")
            if os.path.isfile(idx):
                return send_from_directory(FRONTEND_DIST, os.path.join(path, "index.html"))
    # SPA fallback: serve index.html for any non-API, non-static path
    index = os.path.join(FRONTEND_DIST, "index.html")
    if os.path.isfile(index):
        return send_from_directory(FRONTEND_DIST, "index.html")
    return "Frontend not built. Run from frontend: npm run build.", 404


# ---------------------------------------------------------------------------
# Terminal: SSH channel stream
# ---------------------------------------------------------------------------
def _close_terminal(task_id: str):
    with _terminal_lock:
        entry = _terminal_sessions.pop(task_id, None)
    if entry:
        channel, ssh = entry
        try:
            channel.close()
        except Exception:
            pass
        try:
            ssh.close()
        except Exception:
            pass


def _reader_loop_ssh(task_id: str, channel, sid: str):
    """Read output from paramiko channel and stream to client via Socket.IO."""
    try:
        channel.settimeout(0.1)
        while True:
            try:
                data = channel.recv(4096)
                if not data:
                    break
                text = data.decode("utf-8", errors="replace")
                socketio.emit("terminal:output", {"taskId": int(task_id), "data": text}, to=sid)
            except TimeoutError:
                continue  # channel.settimeout(0.1) fired — no data yet, keep reading
            except (EOFError, OSError, paramiko.SSHException):
                break  # channel / transport closed cleanly (including VM reset/shutdown)
            except Exception as e:
                if channel.closed:
                    break
                raise
    except Exception as e:
        msg = str(e)
        if msg:
            socketio.emit("terminal:error", {"taskId": int(task_id), "message": f"{type(e).__name__}: {msg}"}, to=sid)
    finally:
        socketio.emit("terminal:exit", {"taskId": int(task_id), "code": 0}, to=sid)
        # Only remove + close if this reader loop's channel is still the active one.
        # If a new terminal:connect replaced the session, leave the new session alone.
        with _terminal_lock:
            entry = _terminal_sessions.get(task_id)
            if entry is not None and entry[0] is channel:
                _terminal_sessions.pop(task_id)
            else:
                entry = None
        if entry:
            ch, ssh = entry
            try:
                ch.close()
            except Exception:
                pass
            try:
                ssh.close()
            except Exception:
                pass


@socketio.on("terminal:connect")
def on_terminal_connect(data):
    task_id = str(data.get("taskId") or "")
    if not task_id:
        emit("terminal:error", {"taskId": 0, "message": "taskId required"})
        return
    join_room(f"terminal:{task_id}")
    task = next((t for t in _active_exam["tasks"] if t["id"] == int(task_id)), None)
    if task is None:
        emit("terminal:error", {"taskId": int(task_id), "message": f"Task {task_id} not found"})
        return
    _close_terminal(task_id)
    # boot-menu is VNC-only — no SSH terminal available
    if task["node"] == "boot-menu":
        emit("terminal:error", {"taskId": int(task_id), "message": "boot-menu uses VNC console, not SSH terminal"})
        return
    try:
        vm_config = get_active_vm_config(node=task["node"])
        ssh = _ssh_connect(vm_config)
        channel = ssh.invoke_shell()
        channel.settimeout(0.1)
        with _terminal_lock:
            _terminal_sessions[task_id] = (channel, ssh)
        t = threading.Thread(target=_reader_loop_ssh, args=(task_id, channel, request.sid))
        t.daemon = True
        t.start()
    except Exception as e:
        emit("terminal:error", {"taskId": int(task_id), "message": str(e)})


@socketio.on("terminal:input")
def on_terminal_input(data):
    task_id = str(data.get("taskId") or "")
    raw = data.get("data")
    if raw is None:
        raw = ""
    if isinstance(raw, str):
        raw = raw.encode("utf-8", errors="replace")
    with _terminal_lock:
        entry = _terminal_sessions.get(task_id)
    if entry:
        channel, _ = entry
        try:
            channel.send(raw)
        except Exception:
            pass


@socketio.on("terminal:resize")
def on_terminal_resize(data):
    task_id = str(data.get("taskId") or "")
    cols = data.get("cols", 80)
    rows = data.get("rows", 24)
    with _terminal_lock:
        entry = _terminal_sessions.get(task_id)
    if entry:
        channel, _ = entry
        try:
            channel.resize_pty(width=cols, height=rows)
        except Exception:
            pass


@socketio.on("connect")
def on_connect():
    global _idle_shutdown_timer
    with _connected_lock:
        _connected_sids.add(request.sid)
        if _idle_shutdown_timer is not None:
            _idle_shutdown_timer.cancel()
            _idle_shutdown_timer = None


@socketio.on("disconnect")
def on_disconnect():
    global _idle_shutdown_timer
    with _connected_lock:
        _connected_sids.discard(request.sid)
        if _connected_sids:
            return  # other clients still connected
        # Don't schedule shutdown if the server is about to restart via /api/restart.
        if _restarting:
            return
        # Last client disconnected — schedule a VM shutdown after the grace period.
        if _idle_shutdown_timer is not None:
            _idle_shutdown_timer.cancel()
        _idle_shutdown_timer = threading.Timer(_IDLE_SHUTDOWN_DELAY, _shutdown_all_vms)
        _idle_shutdown_timer.daemon = True
        _idle_shutdown_timer.start()




# ---------------------------------------------------------------------------
# Startup: ensure the default VM is running before serving requests.
# ---------------------------------------------------------------------------
def _startup_vm_worker():
    """
    Start the standard (default) VM on app startup if it is not already running.
    Uses the save-file checkpoint for a fast restore when available, otherwise
    does a cold virsh start.  Runs in a background thread so it does not block
    the Flask/SocketIO server from accepting connections.
    """
    from vm_config import DEFAULT_SCENARIO, SCENARIOS

    scenario = os.environ.get("ACTIVE_SCENARIO", DEFAULT_SCENARIO)
    if scenario not in SCENARIOS:
        scenario = DEFAULT_SCENARIO
    info = SCENARIOS[scenario]
    hostname = info["hostname"]

    # Kill any VM that is NOT the target before starting.
    for _s, _info in SCENARIOS.items():
        if _s != scenario and _vm_is_running(_info["hostname"]):
            _shutdown_vm(_info["hostname"])
            print(f"[startup] stopped stale VM {_info['hostname']}", flush=True)

    state = subprocess.run(
        ["virsh", "domstate", hostname], capture_output=True, text=True, timeout=5
    )
    if state.stdout.strip() == "running":
        print(f"[startup] {hostname} is already running", flush=True)
    else:
        print(f"[startup] {hostname} is not running — starting…", flush=True)
        save = _save_path(hostname)
        if os.path.exists(save):
            result = subprocess.run(
                ["virsh", "restore", save], capture_output=True, text=True, timeout=30
            )
            if result.returncode == 0:
                print(f"[startup] {hostname}: restored from checkpoint", flush=True)
            else:
                print(f"[startup] {hostname}: restore failed ({result.stderr.strip()}), trying cold start…", flush=True)
                subprocess.run(["virsh", "start", hostname], capture_output=True, timeout=15)
        else:
            subprocess.run(["virsh", "start", hostname], capture_output=True, timeout=15)
            print(f"[startup] {hostname}: cold-started (no checkpoint yet)", flush=True)

    # Wait for SSH to be ready (skip for boot-menu which is VNC-only).
    if scenario != "boot-menu":
        ok, err = ensure_vm()
        if ok:
            print(f"[startup] {hostname}: SSH ready", flush=True)
        else:
            print(f"[startup] {hostname}: SSH not ready after 30s: {err}", flush=True)


_restarting = False  # set True when /api/restart is called; suppresses idle-shutdown timer


@app.route("/api/restart", methods=["POST"])
def api_restart():
    """Exit so the run.sh wrapper restarts the process. Called by the frontend on page load."""
    global _restarting
    _restarting = True

    def _do_exit():
        time.sleep(0.3)
        os._exit(0)
    threading.Thread(target=_do_exit, daemon=True).start()
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    if not os.path.isdir(FRONTEND_DIST):
        os.makedirs(FRONTEND_DIST, exist_ok=True)
    _register_shutdown_hooks()
    threading.Thread(target=_startup_vm_worker, daemon=True).start()
    socketio.run(app, host="0.0.0.0", port=PORT, debug=True, use_reloader=False, allow_unsafe_werkzeug=True)
