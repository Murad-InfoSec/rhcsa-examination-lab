"""
conftest.py – Playwright fixtures and API mock router for RHCSA Examination Lab E2E tests.

All API calls are intercepted via Playwright route mocking so tests run without
real VMs, Ansible, or SSH connectivity.
"""
import re
import sys
import os
import json

import pytest
from playwright.sync_api import Page, Route

# Allow `from pages.xxx import ...` in test files
sys.path.insert(0, os.path.dirname(__file__))

BASE_URL = os.environ.get("BASE_URL", "http://localhost:5000")

# ---------------------------------------------------------------------------
# Canonical mock data
# ---------------------------------------------------------------------------

MOCK_TASKS = [
    {
        "id": 1,
        "node": "standard",
        "title": "Network Configuration",
        "instructions": (
            "Configure the network interface on node1 with the following static settings:\n\n"
            "- IP address: 172.25.250.11/24\n"
            "- Default gateway: 172.25.250.254\n"
            "- DNS server: 172.25.250.254\n"
            "- Hostname: node1.lab.example.com"
        ),
        "status": "idle",
        "lastCheck": None,
    },
    {
        "id": 2,
        "node": "standard",
        "title": "YUM Repositories",
        "instructions": (
            "Configure two YUM/DNF repositories on node1:\n\n"
            "- Repository name: BaseOS\n"
            "  URL: http://content/rhel9.0/x86_64/dvd/BaseOS\n"
            "- Repository name: AppStream\n"
            "  URL: http://content/rhel9.0/x86_64/dvd/AppStream"
        ),
        "status": "idle",
        "lastCheck": None,
    },
    {
        "id": 15,
        "node": "boot-menu",
        "title": "Root Password Reset",
        "instructions": (
            "Reset the root password on node2 using the VNC console:\n\n"
            "1. Open the VNC console and reboot the VM\n"
            "2. At the GRUB menu, press 'e' to edit the boot entry\n"
            "3. Append rd.break to the linux line and press Ctrl+X"
        ),
        "status": "idle",
        "lastCheck": None,
    },
    {
        "id": 17,
        "node": "lvm",
        "title": "Resize Logical Volume",
        "instructions": (
            "Resize the logical volume vo to between 225 MiB and 275 MiB:\n\n"
            "1. Find the LV: lvs\n"
            "2. Resize to 250 MiB: lvresize -L 250M /dev/<vg>/vo\n"
            "3. Resize the filesystem: resize2fs /dev/<vg>/vo"
        ),
        "status": "idle",
        "lastCheck": None,
    },
]

MOCK_EXAMS = [
    {
        "id": "exam-1",
        "title": "RHCSA Practice Exam 1",
        "description": "Full RHCSA exam simulation - variant 1",
        "scenario": "standard+lvm+boot-menu",
        "task_count": 20,
    },
    {
        "id": "exam-2",
        "title": "RHCSA Practice Exam 2",
        "description": "Full RHCSA exam simulation - variant 2",
        "scenario": "standard+lvm+boot-menu",
        "task_count": 18,
    },
]

MOCK_ACTIVE_EXAM = {
    "id": "exam-1",
    "title": "RHCSA Practice Exam 1",
    "description": "Full RHCSA exam simulation - variant 1",
    "scenario": "standard+lvm+boot-menu",
    "task_count": 20,
    "tasks": MOCK_TASKS,
}

MOCK_CHECK_PASS = {
    "status": "PASS",
    "summary": "All 3 checks passed successfully.",
    "timestamp": "2026-03-15T10:00:00.000Z",
    "details": [
        {"name": "IP address configured", "passed": True, "message": "172.25.250.11/24 found on eth0"},
        {"name": "Default gateway set", "passed": True, "message": "Gateway 172.25.250.254 configured"},
        {"name": "Hostname correct", "passed": True, "message": "node1.lab.example.com verified"},
    ],
}

MOCK_CHECK_FAIL = {
    "status": "FAIL",
    "summary": "1 of 3 checks failed.",
    "timestamp": "2026-03-15T10:05:00.000Z",
    "details": [
        {"name": "IP address configured", "passed": True, "message": "172.25.250.11/24 found on eth0"},
        {
            "name": "Default gateway set",
            "passed": False,
            "message": "Expected 172.25.250.254, got 192.168.1.1",
        },
        {"name": "Hostname correct", "passed": True, "message": "node1.lab.example.com verified"},
    ],
}

# ---------------------------------------------------------------------------
# Route mock factory
# ---------------------------------------------------------------------------

def build_mock_router(
    check_result: dict | None = None,
    vm_available: bool = True,
    tasks: list | None = None,
    active_exam: dict | None = None,
    exams: list | None = None,
):
    """Return a Playwright route handler function with configurable API responses."""
    if check_result is None:
        check_result = MOCK_CHECK_PASS
    if tasks is None:
        tasks = MOCK_TASKS
    if active_exam is None:
        active_exam = MOCK_ACTIVE_EXAM
    if exams is None:
        exams = MOCK_EXAMS

    def handle(route: Route) -> None:
        url = route.request.url
        method = route.request.method

        # Extract path after host:port
        m = re.search(r"localhost:\d+(/[^?#]*)", url)
        path = m.group(1) if m else url

        # --- VM ---
        if re.fullmatch(r"/api/vm/status", path):
            body = (
                {"available": True, "scenario": "standard", "ip": "192.168.100.10"}
                if vm_available
                else {"available": False, "error": "VM unreachable"}
            )
            route.fulfill(status=200, content_type="application/json", body=json.dumps(body))

        elif re.fullmatch(r"/api/vm/checkpoint-status", path):
            route.fulfill(status=200, content_type="application/json", body=json.dumps({}))

        elif re.fullmatch(r"/api/vm/save-checkpoint", path) and method == "POST":
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps({"ok": True, "hostname": "standard-001"}),
            )

        elif re.fullmatch(r"/api/vm/current", path):
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps({"scenario": "standard", "ip": "192.168.100.10", "hostname": "standard-001"}),
            )

        # --- VNC ---
        elif re.fullmatch(r"/api/vnc/status", path):
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps({"available": False, "ws_port": 6080, "vnc_port": 5900, "scenario": "boot-menu"}),
            )

        elif re.fullmatch(r"/api/vnc/(start|stop)", path) and method == "POST":
            route.fulfill(status=200, content_type="application/json", body=json.dumps({"ok": True}))

        # --- Tasks ---
        elif re.fullmatch(r"/api/tasks", path):
            route.fulfill(status=200, content_type="application/json", body=json.dumps(tasks))

        elif re.fullmatch(r"/api/task/\d+/(start|stop|reset|prepare)", path) and method == "POST":
            route.fulfill(status=200, content_type="application/json", body=json.dumps({"ok": True}))

        elif re.fullmatch(r"/api/task/\d+/check", path) and method == "POST":
            route.fulfill(status=200, content_type="application/json", body=json.dumps(check_result))

        # --- Exams ---
        elif re.fullmatch(r"/api/exams", path):
            route.fulfill(status=200, content_type="application/json", body=json.dumps(exams))

        elif re.fullmatch(r"/api/exam/active", path):
            route.fulfill(status=200, content_type="application/json", body=json.dumps(active_exam))

        elif re.match(r"/api/exam/set/", path) and method == "POST":
            route.fulfill(status=200, content_type="application/json", body=json.dumps({"ok": True}))

        else:
            route.continue_()

    return handle


# ---------------------------------------------------------------------------
# Internal helper
# ---------------------------------------------------------------------------

def _navigate(page: Page, router_kwargs: dict, wait_for: str = "text=Task Registry") -> Page:
    """Install mock routes, navigate to the app, and wait until it is ready."""
    page.route("**/api/**", build_mock_router(**router_kwargs))
    page.goto(BASE_URL)
    page.wait_for_selector(wait_for, timeout=15_000)
    return page


# ---------------------------------------------------------------------------
# Public fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def app_page(page: Page) -> Page:
    """Standard app page: VM available, PASS check result."""
    return _navigate(page, {})


@pytest.fixture
def app_page_vm_down(page: Page) -> Page:
    """App page with VM reported as unavailable."""
    return _navigate(page, {"vm_available": False}, wait_for="text=VM Unreachable")


@pytest.fixture
def app_page_check_fail(page: Page) -> Page:
    """App page where the /check API returns a FAIL result."""
    return _navigate(page, {"check_result": MOCK_CHECK_FAIL})
