"""
test_performance.py – Performance & latency tests for the RHCSA Examination Lab.

SLA budgets enforced here:
  PAGE_LOAD_MS      = 2 000 ms  – full page ready (task list visible)
  API_RESPONSE_MS   =   500 ms  – any single /api/* endpoint
  TASK_SWITCH_MS    = 1 000 ms  – task click → instructions panel updated
  PANEL_TOGGLE_MS   =   200 ms  – toggle click → panel hidden/shown

The TestBenchmarks class uses pytest-benchmark for statistical measurements
of the Flask API (min / mean / stddev / rounds).

All Playwright tests use the shared API mock so they are not blocked by real VM
latency; the objective is to isolate React rendering and mock-API overhead.
"""

from __future__ import annotations

import os
import sys
import time
from typing import Callable

import pytest
import requests
from playwright.sync_api import Page

# ---------------------------------------------------------------------------
# Path helpers (reuse POM classes from tests/pages/)
# ---------------------------------------------------------------------------
sys.path.insert(0, os.path.dirname(__file__))
from conftest import build_mock_router, BASE_URL
from pages.main_page import MainPage

# ---------------------------------------------------------------------------
# SLA constants (milliseconds unless noted)
# ---------------------------------------------------------------------------
PAGE_LOAD_MS: int = 2_000
API_RESPONSE_MS: int = 500
TASK_SWITCH_MS: int = 1_000
PANEL_TOGGLE_MS: int = 200
SPINNER_GONE_MS: int = 3_000
API_TIMEOUT: int = 5  # seconds for requests library

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _flask_available() -> bool:
    """Return True if the real Flask server is responding."""
    try:
        requests.get(f"{BASE_URL}/api/vm/status", timeout=2)
        return True
    except Exception:
        return False


def _timed_page_load(page: Page) -> float:
    """
    Navigate to BASE_URL with mocked APIs and wait for the task list.
    Returns elapsed milliseconds.
    """
    page.route("**/api/**", build_mock_router())
    start = time.perf_counter()
    page.goto(BASE_URL)
    page.wait_for_selector("text=Task Registry", timeout=PAGE_LOAD_MS + 2_000)
    return (time.perf_counter() - start) * 1_000


# ===========================================================================
# 1. Page-load performance
# ===========================================================================

class TestPageLoadPerformance:
    """Measure how quickly the app becomes interactive after navigation."""

    def test_full_page_load_within_budget(self, page: Page):
        """
        Time from page.goto() to 'Task Registry' visible must stay under
        PAGE_LOAD_MS (2 000 ms). Covers HTML parse, JS evaluation, React
        mount, and all mock-API round trips.
        """
        elapsed_ms = _timed_page_load(page)
        assert elapsed_ms < PAGE_LOAD_MS, (
            f"Page load took {elapsed_ms:.0f} ms — budget is {PAGE_LOAD_MS} ms.\n"
            "Possible causes: large JS bundle, slow React render, or network stall."
        )

    def test_loading_spinner_disappears_within_budget(self, page: Page):
        """
        The Tailwind 'animate-spin' loading spinner must vanish within
        SPINNER_GONE_MS (3 000 ms) of navigation, confirming all initial
        API calls resolved.
        """
        page.route("**/api/**", build_mock_router())
        page.goto(BASE_URL)
        start = time.perf_counter()
        page.wait_for_selector(
            ".animate-spin",
            state="hidden",
            timeout=SPINNER_GONE_MS + 1_000,
        )
        elapsed_ms = (time.perf_counter() - start) * 1_000
        assert elapsed_ms < SPINNER_GONE_MS, (
            f"Loading spinner took {elapsed_ms:.0f} ms to disappear — "
            f"budget is {SPINNER_GONE_MS} ms."
        )

    def test_dom_content_loaded_within_budget(self, page: Page):
        """
        Navigation Timing API: domContentLoadedEventEnd − navigationStart
        must be under PAGE_LOAD_MS. Validates browser-reported timings,
        not just Playwright wait-selector elapsed time.
        """
        page.route("**/api/**", build_mock_router())
        page.goto(BASE_URL, wait_until="domcontentloaded")
        page.wait_for_selector("text=Task Registry", timeout=10_000)

        timing = page.evaluate(
            "() => JSON.parse(JSON.stringify(window.performance.timing))"
        )
        nav_start = timing.get("navigationStart", 0)
        dcl_end = timing.get("domContentLoadedEventEnd", 0)
        if not (nav_start and dcl_end):
            pytest.skip("Navigation Timing API returned zeros — browser may not support it")

        dom_ms = dcl_end - nav_start
        assert dom_ms < PAGE_LOAD_MS, (
            f"DOMContentLoaded took {dom_ms} ms — budget is {PAGE_LOAD_MS} ms."
        )

    def test_no_javascript_errors_on_load(self, page: Page):
        """
        Zero JavaScript console errors must occur during the full initial
        page load. Console errors indicate broken imports, failed fetches, or
        unhandled promise rejections that degrade UX silently.
        """
        js_errors: list[str] = []
        page.on(
            "console",
            lambda msg: js_errors.append(msg.text) if msg.type == "error" else None,
        )
        page.route("**/api/**", build_mock_router())
        page.goto(BASE_URL)
        page.wait_for_selector("text=Task Registry", timeout=10_000)

        # Ignore browser-injected noise (favicon 404 etc.)
        critical = [e for e in js_errors if "favicon" not in e.lower()]
        assert not critical, (
            f"Console errors during page load:\n" + "\n".join(f"  • {e}" for e in critical)
        )

    def test_page_load_is_stable_across_three_navigations(self, page: Page):
        """
        Three consecutive page loads must all complete within PAGE_LOAD_MS.
        Catches memory leaks or warm-up effects that cause progressive slowdowns.
        """
        page.route("**/api/**", build_mock_router())
        for i in range(3):
            start = time.perf_counter()
            page.goto(BASE_URL)
            page.wait_for_selector("text=Task Registry", timeout=PAGE_LOAD_MS + 2_000)
            elapsed_ms = (time.perf_counter() - start) * 1_000
            assert elapsed_ms < PAGE_LOAD_MS, (
                f"Navigation #{i + 1} took {elapsed_ms:.0f} ms — "
                f"budget is {PAGE_LOAD_MS} ms."
            )


# ===========================================================================
# 2. Flask API response-time SLA
# ===========================================================================

class TestAPIResponseTime:
    """
    Measure HTTP response times for every Flask API endpoint directly
    (no Playwright overhead). Tests are skipped when the server is offline.
    """

    @pytest.fixture(autouse=True)
    def _require_flask(self):
        """Skip the entire class if the Flask server is not running."""
        if not _flask_available():
            pytest.skip(
                f"Flask not reachable at {BASE_URL} — "
                "start the server with: python backend/app.py"
            )

    # ── helper ──────────────────────────────────────────────────────────────

    @staticmethod
    def _get_ms(path: str) -> float:
        """GET path and return elapsed milliseconds. Asserts HTTP 200."""
        url = f"{BASE_URL}{path}"
        start = time.perf_counter()
        r = requests.get(url, timeout=API_TIMEOUT)
        elapsed_ms = (time.perf_counter() - start) * 1_000
        assert r.status_code == 200, (
            f"GET {path} returned HTTP {r.status_code}: {r.text[:200]}"
        )
        return elapsed_ms

    # ── tests ────────────────────────────────────────────────────────────────

    def test_vm_status_response_time(self):
        """
        GET /api/vm/status must respond within API_RESPONSE_MS (500 ms).
        This endpoint is polled by the frontend on every page load.
        """
        ms = self._get_ms("/api/vm/status")
        assert ms < API_RESPONSE_MS, (
            f"/api/vm/status: {ms:.0f} ms — budget {API_RESPONSE_MS} ms"
        )

    def test_tasks_response_time(self):
        """
        GET /api/tasks must respond within API_RESPONSE_MS.
        Slow task serialisation blocks the initial React render.
        """
        ms = self._get_ms("/api/tasks")
        assert ms < API_RESPONSE_MS, (
            f"/api/tasks: {ms:.0f} ms — budget {API_RESPONSE_MS} ms"
        )

    def test_exams_response_time(self):
        """GET /api/exams must respond within API_RESPONSE_MS."""
        ms = self._get_ms("/api/exams")
        assert ms < API_RESPONSE_MS, (
            f"/api/exams: {ms:.0f} ms — budget {API_RESPONSE_MS} ms"
        )

    def test_active_exam_response_time(self):
        """GET /api/exam/active must respond within API_RESPONSE_MS."""
        ms = self._get_ms("/api/exam/active")
        assert ms < API_RESPONSE_MS, (
            f"/api/exam/active: {ms:.0f} ms — budget {API_RESPONSE_MS} ms"
        )

    def test_checkpoint_status_response_time(self):
        """GET /api/vm/checkpoint-status must respond within API_RESPONSE_MS."""
        ms = self._get_ms("/api/vm/checkpoint-status")
        assert ms < API_RESPONSE_MS, (
            f"/api/vm/checkpoint-status: {ms:.0f} ms — budget {API_RESPONSE_MS} ms"
        )

    def test_vnc_status_response_time(self):
        """GET /api/vnc/status must respond within API_RESPONSE_MS."""
        ms = self._get_ms("/api/vnc/status")
        assert ms < API_RESPONSE_MS, (
            f"/api/vnc/status: {ms:.0f} ms — budget {API_RESPONSE_MS} ms"
        )

    def test_five_sequential_task_requests_are_consistent(self):
        """
        Five sequential GET /api/tasks calls must all be within budget and the
        slowest must not exceed 3× the average (no pathological outlier).
        """
        times = [self._get_ms("/api/tasks") for _ in range(5)]
        avg = sum(times) / len(times)
        worst = max(times)
        over_budget = [t for t in times if t >= API_RESPONSE_MS]

        assert not over_budget, (
            f"Some /api/tasks calls exceeded budget: "
            + ", ".join(f"{t:.0f} ms" for t in over_budget)
            + f" (budget={API_RESPONSE_MS} ms)"
        )
        assert worst < avg * 3, (
            f"Inconsistent /api/tasks latency — "
            f"avg={avg:.0f} ms, worst={worst:.0f} ms (should be < 3× avg)"
        )


# ===========================================================================
# 3. UI interaction speed
# ===========================================================================

class TestUIInteractionSpeed:
    """
    Measure React's re-render latency for common user interactions.
    All tests use mocked APIs so VM latency cannot inflate timings.
    """

    @pytest.fixture(autouse=True)
    def _load_app(self, page: Page):
        """Navigate to the app and expose the MainPage POM as self.mp."""
        page.route("**/api/**", build_mock_router())
        page.goto(BASE_URL)
        page.wait_for_selector("text=Task Registry", timeout=10_000)
        self.page = page
        self.mp = MainPage(page)

    def test_task_switch_updates_instructions_within_budget(self):
        """
        Clicking task 2 must update the instructions heading within
        TASK_SWITCH_MS (1 000 ms) of the click event.
        """
        start = time.perf_counter()
        self.mp.select_task(2)
        self.page.wait_for_selector(
            "text=YUM Repositories",
            timeout=TASK_SWITCH_MS + 500,
        )
        elapsed_ms = (time.perf_counter() - start) * 1_000
        assert elapsed_ms < TASK_SWITCH_MS, (
            f"Task 2 instruction update: {elapsed_ms:.0f} ms — "
            f"budget is {TASK_SWITCH_MS} ms"
        )

    def test_three_consecutive_task_switches_all_fast(self):
        """
        Three sequential task switches must each complete within TASK_SWITCH_MS.
        Catches cumulative slowdowns from React reconciliation or leaked listeners.
        """
        switches = [
            (2, "YUM Repositories"),
            (17, "Resize Logical Volume"),
            (1, "Network Configuration"),
        ]
        for task_id, title in switches:
            start = time.perf_counter()
            self.mp.select_task(task_id)
            self.page.wait_for_selector(f"text={title}", timeout=TASK_SWITCH_MS + 500)
            elapsed_ms = (time.perf_counter() - start) * 1_000
            assert elapsed_ms < TASK_SWITCH_MS, (
                f"Switch to task {task_id} ('{title}'): {elapsed_ms:.0f} ms — "
                f"budget is {TASK_SWITCH_MS} ms"
            )

    def test_panel_toggle_hides_element_within_budget(self):
        """
        Clicking the Results toggle must make 'Validation Results' disappear
        within PANEL_TOGGLE_MS (200 ms). Tests CSS transition + React unmount.
        """
        start = time.perf_counter()
        self.mp.toggle_panel("Results")
        self.page.wait_for_selector(
            "text=Validation Results",
            state="hidden",
            timeout=PANEL_TOGGLE_MS + 200,
        )
        elapsed_ms = (time.perf_counter() - start) * 1_000
        assert elapsed_ms < PANEL_TOGGLE_MS, (
            f"Results panel hide: {elapsed_ms:.0f} ms — budget is {PANEL_TOGGLE_MS} ms"
        )

    def test_start_button_triggers_status_change_within_budget(self):
        """
        Clicking Start must update the task status badge to 'running' within
        TASK_SWITCH_MS (1 000 ms). Validates the optimistic-UI update path.
        """
        start = time.perf_counter()
        self.mp.click_start()
        self.page.wait_for_selector("text=running", timeout=TASK_SWITCH_MS + 500)
        elapsed_ms = (time.perf_counter() - start) * 1_000
        assert elapsed_ms < TASK_SWITCH_MS, (
            f"Start → RUNNING transition: {elapsed_ms:.0f} ms — "
            f"budget is {TASK_SWITCH_MS} ms"
        )

    def test_verify_result_renders_within_budget(self):
        """
        After Start → Verify, the PASS result card must appear within
        TASK_SWITCH_MS. Measures the full check-result render cycle.
        """
        self.mp.click_start()
        self.page.wait_for_selector("text=running", timeout=2_000)
        start = time.perf_counter()
        self.mp.click_verify()
        self.page.wait_for_selector("text=Result:", timeout=TASK_SWITCH_MS + 500)
        elapsed_ms = (time.perf_counter() - start) * 1_000
        assert elapsed_ms < TASK_SWITCH_MS, (
            f"Verify → result card: {elapsed_ms:.0f} ms — "
            f"budget is {TASK_SWITCH_MS} ms"
        )


# ===========================================================================
# 4. Statistical benchmarks (pytest-benchmark)
# ===========================================================================

class TestBenchmarks:
    """
    Statistical latency benchmarks using pytest-benchmark.
    Each test runs the subject function multiple times and reports
    min / mean / stddev / rounds in the pytest-benchmark summary table.

    These tests are skipped automatically when the Flask server is offline.
    Run standalone with:
        pytest tests/test_performance.py::TestBenchmarks --benchmark-only -v
    """

    @pytest.fixture(autouse=True)
    def _require_flask(self):
        """Skip all benchmark tests if the Flask server is not running."""
        if not _flask_available():
            pytest.skip(
                f"Flask not reachable at {BASE_URL} — "
                "start the server first"
            )

    def test_benchmark_get_tasks(self, benchmark):
        """
        Benchmark: GET /api/tasks repeated call latency.
        Acceptable mean: under API_RESPONSE_MS (500 ms).
        """
        def fetch():
            r = requests.get(f"{BASE_URL}/api/tasks", timeout=API_TIMEOUT)
            assert r.status_code == 200
            return r.json()

        result = benchmark.pedantic(fetch, rounds=10, iterations=1)
        assert isinstance(result, list), "Benchmark returned unexpected type"
        # pytest-benchmark reports stats; also assert explicit SLA on mean
        assert benchmark.stats["mean"] * 1_000 < API_RESPONSE_MS, (
            f"Benchmark mean {benchmark.stats['mean'] * 1_000:.0f} ms "
            f"exceeds SLA of {API_RESPONSE_MS} ms"
        )

    def test_benchmark_get_vm_status(self, benchmark):
        """
        Benchmark: GET /api/vm/status repeated call latency.
        This is the most-frequently polled endpoint on the frontend.
        """
        def fetch():
            r = requests.get(f"{BASE_URL}/api/vm/status", timeout=API_TIMEOUT)
            assert r.status_code == 200
            return r.json()

        result = benchmark.pedantic(fetch, rounds=10, iterations=1)
        assert "available" in result
        assert benchmark.stats["mean"] * 1_000 < API_RESPONSE_MS, (
            f"Benchmark mean {benchmark.stats['mean'] * 1_000:.0f} ms "
            f"exceeds SLA of {API_RESPONSE_MS} ms"
        )

    def test_benchmark_get_exams(self, benchmark):
        """
        Benchmark: GET /api/exams repeated call latency.
        Exam list is loaded once on mount; should always be fast.
        """
        def fetch():
            r = requests.get(f"{BASE_URL}/api/exams", timeout=API_TIMEOUT)
            assert r.status_code == 200
            return r.json()

        result = benchmark.pedantic(fetch, rounds=10, iterations=1)
        assert isinstance(result, list)
        assert benchmark.stats["mean"] * 1_000 < API_RESPONSE_MS, (
            f"Benchmark mean {benchmark.stats['mean'] * 1_000:.0f} ms "
            f"exceeds SLA of {API_RESPONSE_MS} ms"
        )
