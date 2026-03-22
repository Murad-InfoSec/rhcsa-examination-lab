"""
test_cross_browser.py – Critical user-flow tests across Chromium, Firefox, and WebKit.

Each test class is parametrized over the three Playwright browser engines.
Tests that depend on a specific browser's behaviour are noted in their docstrings.

A custom ``cross_page`` fixture:
  • launches each browser in headless mode,
  • installs the same API mock used by the unit test suite, and
  • navigates to BASE_URL before yielding the Page.

Browsers that are not installed on the current platform are skipped gracefully
(the fixture catches the BrowserType.launch() exception).

Run only cross-browser tests:
  pytest tests/test_cross_browser.py -v

Run a single browser:
  pytest tests/test_cross_browser.py -k chromium -v
"""

from __future__ import annotations

import os
import sys

import pytest
from playwright.sync_api import Page, Playwright, expect

# ---------------------------------------------------------------------------
# Path helpers so POM imports work
# ---------------------------------------------------------------------------
sys.path.insert(0, os.path.dirname(__file__))
from conftest import build_mock_router, BASE_URL, MOCK_CHECK_PASS, MOCK_CHECK_FAIL
from pages.main_page import MainPage
from pages.exam_modal import ExamModal

# ---------------------------------------------------------------------------
# Browser list – parametrize every test in this file over all three engines
# ---------------------------------------------------------------------------
BROWSERS = ["chromium", "firefox", "webkit"]


# ===========================================================================
# Shared fixture
# ===========================================================================

@pytest.fixture(params=BROWSERS, ids=BROWSERS)
def cross_page(request, playwright: Playwright) -> Page:
    """
    Yield a fully loaded Page for each browser in BROWSERS.

    The fixture:
      1. Launches the browser engine headlessly.
      2. Installs the shared API mock router.
      3. Navigates to the app and waits for the task list.
      4. Yields the Page to the test.
      5. Cleans up context and browser after the test.

    Individual browser skip happens here so individual tests are reported
    as SKIPPED rather than ERROR when a browser binary is missing.
    """
    browser_name: str = request.param
    try:
        browser_type = getattr(playwright, browser_name)
        browser = browser_type.launch(headless=True)
    except Exception as exc:
        pytest.skip(
            f"{browser_name} not available on this platform: {exc}"
        )

    context = browser.new_context()
    page = context.new_page()

    # Install the same API mock used by all existing tests
    page.route("**/api/**", build_mock_router())

    try:
        page.goto(BASE_URL, timeout=30_000)
        page.wait_for_selector("text=Task Registry", timeout=20_000)
    except Exception as exc:
        context.close()
        browser.close()
        pytest.fail(
            f"[{browser_name}] App did not load at {BASE_URL}: {exc}\n"
            "Ensure the Flask server is running: python backend/app.py"
        )

    yield page

    context.close()
    browser.close()


@pytest.fixture(params=BROWSERS, ids=BROWSERS)
def cross_page_fail(request, playwright: Playwright) -> Page:
    """
    Same as cross_page but the /check API returns a FAIL result.
    Used by scoring tests that need to verify red-path display.
    """
    browser_name: str = request.param
    try:
        browser_type = getattr(playwright, browser_name)
        browser = browser_type.launch(headless=True)
    except Exception as exc:
        pytest.skip(f"{browser_name} not available: {exc}")

    context = browser.new_context()
    page = context.new_page()
    page.route("**/api/**", build_mock_router(check_result=MOCK_CHECK_FAIL))

    try:
        page.goto(BASE_URL, timeout=30_000)
        page.wait_for_selector("text=Task Registry", timeout=20_000)
    except Exception as exc:
        context.close()
        browser.close()
        pytest.fail(f"[{browser_name}] App did not load: {exc}")

    yield page

    context.close()
    browser.close()


# ===========================================================================
# 1. Page load across browsers
# ===========================================================================

class TestCrossBrowserPageLoad:
    """Verify that the application renders its full initial state in every browser."""

    def test_app_title_visible(self, cross_page: Page):
        """
        The h1 must contain 'RHCSA Examination Lab' in every browser.
        Confirms that React hydrates correctly and fonts/styles load.
        """
        expect(cross_page.locator("h1").first).to_contain_text("RHCSA")
        expect(cross_page.locator("h1").first).to_contain_text("Examination Lab")

    def test_task_registry_renders(self, cross_page: Page):
        """
        'Task Registry' heading must be visible after load.
        Validates that the React SPA bootstraps and renders the task panel.
        """
        expect(cross_page.get_by_text("Task Registry")).to_be_visible()

    def test_all_four_panel_toggles_present(self, cross_page: Page):
        """
        All four aria-pressed toggle buttons must exist in every browser.
        Browser-specific CSS or JS evaluation differences could hide them.
        """
        for label in ("Tasks", "Instructions", "Terminal", "Results"):
            btn = cross_page.locator("button[aria-pressed]").filter(has_text=label)
            expect(btn).to_be_visible()

    def test_exam_selector_shows_active_exam(self, cross_page: Page):
        """
        The exam selector button in the header shows the active exam title.
        Cross-browser font rendering should not affect text visibility.
        """
        mp = MainPage(cross_page)
        expect(mp.exam_selector_button).to_be_visible()
        expect(mp.exam_selector_button).to_contain_text("RHCSA Practice")

    def test_first_task_is_pre_selected(self, cross_page: Page):
        """
        Task 1 must be active by default (red background badge visible).
        Tests that localStorage parsing and initial useState work cross-browser.
        """
        mp = MainPage(cross_page)
        task1 = mp.get_task_item(1)
        expect(task1.locator(".bg-red-600")).to_be_visible()

    def test_no_loading_spinner_visible_after_load(self, cross_page: Page):
        """
        The animate-spin spinner must be gone after the app has loaded.
        A stuck spinner means Promise.all([…API calls…]) did not resolve.
        """
        expect(cross_page.locator(".animate-spin")).to_have_count(0)


# ===========================================================================
# 2. Task selection workflow
# ===========================================================================

class TestCrossBrowserTaskWorkflow:
    """Verify task selection and the Start/Stop status-change cycle in every browser."""

    def test_selecting_task_2_updates_instructions(self, cross_page: Page):
        """
        Clicking task 2 must update the instructions panel title to
        'YUM Repositories'. Tests React state update and DOM patching.
        """
        mp = MainPage(cross_page)
        mp.select_task(2)
        expect(mp.task_title_heading).to_contain_text("YUM Repositories")

    def test_selecting_task_updates_id_badge(self, cross_page: Page):
        """
        After clicking task 2, the TASK badge must show '2'.
        Tests that the activeTaskId state variable updates correctly.
        """
        mp = MainPage(cross_page)
        mp.select_task(2)
        expect(mp.task_id_badge).to_contain_text("2")

    def test_start_button_changes_status_to_running(self, cross_page: Page):
        """
        Clicking Start on task 1 must change its status badge text to 'running'.
        Validates the optimistic UI update path works identically across browsers.
        """
        mp = MainPage(cross_page)
        mp.click_start()
        expect(mp.get_task_item(1)).to_contain_text("running")

    def test_stop_button_enabled_after_start(self, cross_page: Page):
        """
        After Start, the Stop button must be enabled.
        Tests that disabled attribute manipulation works in every engine.
        """
        mp = MainPage(cross_page)
        mp.click_start()
        expect(mp.stop_button).to_be_enabled()

    def test_stop_button_changes_status_to_stopped(self, cross_page: Page):
        """
        Start → Stop must transition status to 'stopped' in every browser.
        """
        mp = MainPage(cross_page)
        mp.click_start()
        expect(mp.stop_button).to_be_enabled()
        mp.click_stop()
        expect(mp.get_task_item(1)).to_contain_text("stopped")

    def test_verify_button_enabled_only_when_running(self, cross_page: Page):
        """
        Verify Task Completion is disabled initially and enabled after Start.
        Tests the disabled attribute toggle across browser engines.
        """
        mp = MainPage(cross_page)
        expect(mp.verify_button).to_be_disabled()
        mp.click_start()
        expect(mp.verify_button).to_be_enabled()


# ===========================================================================
# 3. Scoring display
# ===========================================================================

class TestCrossBrowserScoring:
    """Verify that check results (PASS and FAIL) display correctly in every browser."""

    def _start_and_verify(self, page: Page) -> MainPage:
        """Helper: bring task to RUNNING, click Verify, return MainPage."""
        mp = MainPage(page)
        mp.click_start()
        expect(mp.verify_button).to_be_enabled(timeout=5_000)
        mp.click_verify()
        return mp

    def test_pass_result_card_visible(self, cross_page: Page):
        """
        After Verify with a PASS result the check result card must appear.
        Tests that Tailwind conditional class application works cross-browser.
        """
        mp = self._start_and_verify(cross_page)
        expect(mp.check_result_card).to_be_visible()
        expect(mp.check_result_card).to_contain_text("PASS")

    def test_pass_result_shows_correct_summary(self, cross_page: Page):
        """
        The PASS summary text from the mock response must be visible.
        """
        mp = self._start_and_verify(cross_page)
        expect(mp.results_section).to_contain_text("All 3 checks passed")

    def test_pass_result_shows_all_detail_rows(self, cross_page: Page):
        """
        All three check-detail rows must render in every browser.
        Tests that list rendering (Array.map) works consistently.
        """
        mp = self._start_and_verify(cross_page)
        expect(mp.check_detail_items).to_have_count(3)

    def test_pass_result_has_green_card_styling(self, cross_page: Page):
        """
        PASS result card carries green Tailwind colour classes.
        CSS variable and class resolution must work in all browser engines.
        """
        mp = self._start_and_verify(cross_page)
        classes = mp.check_result_card.get_attribute("class") or ""
        assert "green" in classes, (
            f"PASS card missing green styling. Classes found: '{classes}'"
        )

    def test_fail_result_card_visible(self, cross_page_fail: Page):
        """
        FAIL result card must appear in every browser.
        """
        mp = self._start_and_verify(cross_page_fail)
        expect(mp.check_result_card).to_be_visible()
        expect(mp.check_result_card).to_contain_text("FAIL")

    def test_fail_result_has_red_card_styling(self, cross_page_fail: Page):
        """
        FAIL result card carries red Tailwind colour classes in every browser.
        """
        mp = self._start_and_verify(cross_page_fail)
        classes = mp.check_result_card.get_attribute("class") or ""
        assert "red" in classes, (
            f"FAIL card missing red styling. Classes found: '{classes}'"
        )

    def test_no_validation_placeholder_before_check(self, cross_page: Page):
        """
        'No validation performed yet.' placeholder must be visible before any
        check is run. Tests that the conditional render guard works cross-browser.
        """
        mp = MainPage(cross_page)
        expect(mp.no_validation_text).to_be_visible()


# ===========================================================================
# 4. Panel toggles
# ===========================================================================

class TestCrossBrowserPanels:
    """Verify that the panel visibility toggle system works in every browser engine."""

    def test_toggle_tasks_panel_hides_it(self, cross_page: Page):
        """
        Clicking the Tasks toggle must hide 'Task Registry' in every browser.
        Tests that React state update + conditional render work cross-browser.
        """
        mp = MainPage(cross_page)
        mp.toggle_panel("Tasks")
        expect(mp.task_registry_heading).to_have_count(0)

    def test_toggle_tasks_panel_aria_pressed_updates(self, cross_page: Page):
        """
        aria-pressed must switch from 'true' to 'false' after toggling
        in every browser. WebKit and Firefox handle attribute updates differently.
        """
        mp = MainPage(cross_page)
        assert mp.get_panel_toggle_aria_pressed("Tasks") == "true"
        mp.toggle_panel("Tasks")
        assert mp.get_panel_toggle_aria_pressed("Tasks") == "false"

    def test_toggle_results_panel_hides_it(self, cross_page: Page):
        """
        Clicking the Results toggle must hide 'Validation Results' in every browser.
        """
        mp = MainPage(cross_page)
        mp.toggle_panel("Results")
        expect(mp.results_heading).to_have_count(0)

    def test_toggle_panel_restores_on_second_click(self, cross_page: Page):
        """
        Two clicks on the same toggle must restore the original state.
        Tests idempotency of the toggle logic across browser engines.
        """
        mp = MainPage(cross_page)
        mp.toggle_panel("Instructions")
        expect(mp.task_id_badge).to_have_count(0)
        mp.toggle_panel("Instructions")
        expect(mp.task_id_badge).to_be_visible()


# ===========================================================================
# 5. Exam modal
# ===========================================================================

class TestCrossBrowserExamModal:
    """Verify that the exam selection modal opens and closes correctly in all browsers."""

    def test_modal_opens_on_button_click(self, cross_page: Page):
        """
        Clicking the exam selector button must open the modal in every browser.
        Tests that onClick and conditional rendering work cross-browser.
        """
        mp = MainPage(cross_page)
        modal = ExamModal(cross_page)
        mp.exam_selector_button.click()
        expect(modal.overlay).to_be_visible()
        expect(modal.heading).to_be_visible()

    def test_modal_close_button_works(self, cross_page: Page):
        """
        The × close button must dismiss the modal in every browser.
        Tests that stopPropagation and state update work cross-browser.
        """
        mp = MainPage(cross_page)
        modal = ExamModal(cross_page)
        mp.exam_selector_button.click()
        expect(modal.overlay).to_be_visible()
        modal.close_via_button()
        expect(modal.overlay).to_have_count(0)

    def test_both_exams_listed_in_modal(self, cross_page: Page):
        """
        Both exam options must appear in the modal list in every browser.
        """
        mp = MainPage(cross_page)
        modal = ExamModal(cross_page)
        mp.exam_selector_button.click()
        expect(modal.get_exam_button("RHCSA Practice Exam 1")).to_be_visible()
        expect(modal.get_exam_button("RHCSA Practice Exam 2")).to_be_visible()
