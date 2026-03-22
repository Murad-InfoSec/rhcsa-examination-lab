"""
test_scoring.py – Tests for task-verification / scoring display.

Flow: Start the task → click Verify Task Completion → assert the results panel.
Two fixtures are used:
  - app_page          → /check API returns PASS
  - app_page_check_fail → /check API returns FAIL
"""
import pytest
from playwright.sync_api import Page, expect
from pages.main_page import MainPage


def _start_and_verify(page: Page) -> MainPage:
    """Helper: bring the active task to RUNNING state then click Verify."""
    mp = MainPage(page)
    mp.click_start()
    expect(mp.verify_button).to_be_enabled(timeout=5_000)
    mp.click_verify()
    return mp


# ---------------------------------------------------------------------------
# PASS result
# ---------------------------------------------------------------------------

class TestCheckResultPass:
    def test_result_card_appears_after_verify(self, app_page: Page) -> None:
        mp = _start_and_verify(app_page)
        expect(mp.check_result_card).to_be_visible()

    def test_pass_result_status_text(self, app_page: Page) -> None:
        """Result card shows 'Result: PASS'."""
        mp = _start_and_verify(app_page)
        expect(mp.check_result_card).to_contain_text("PASS")

    def test_pass_result_summary_text(self, app_page: Page) -> None:
        """Summary message from the mock PASS response is displayed."""
        mp = _start_and_verify(app_page)
        expect(mp.results_section).to_contain_text("All 3 checks passed")

    def test_pass_result_card_has_green_styling(self, app_page: Page) -> None:
        """PASS card carries Tailwind green classes."""
        mp = _start_and_verify(app_page)
        card_classes = mp.check_result_card.get_attribute("class") or ""
        assert "green" in card_classes, f"Expected green classes, got: {card_classes}"

    def test_pass_result_timestamp_shown(self, app_page: Page) -> None:
        """Timestamp value is rendered on the result card."""
        mp = _start_and_verify(app_page)
        # Timestamp is rendered via toLocaleTimeString(); just check the card has a time-like string
        card_text = mp.check_result_card.text_content() or ""
        assert any(c.isdigit() for c in card_text), "Expected a timestamp with digits"

    def test_pass_all_detail_items_shown(self, app_page: Page) -> None:
        """Three check-detail rows are visible."""
        mp = _start_and_verify(app_page)
        expect(mp.check_detail_items).to_have_count(3)

    def test_pass_detail_names_shown(self, app_page: Page) -> None:
        """Each detail item's name is rendered."""
        mp = _start_and_verify(app_page)
        expect(mp.results_section).to_contain_text("IP address configured")
        expect(mp.results_section).to_contain_text("Default gateway set")
        expect(mp.results_section).to_contain_text("Hostname correct")

    def test_pass_detail_messages_shown(self, app_page: Page) -> None:
        """Detail row messages from the mock response are visible."""
        mp = _start_and_verify(app_page)
        expect(mp.results_section).to_contain_text("172.25.250.11/24 found on eth0")

    def test_pass_all_detail_icons_are_green(self, app_page: Page) -> None:
        """All detail icons carry green styling for a full-PASS result."""
        mp = _start_and_verify(app_page)
        for item in mp.check_detail_items.all():
            icon_div = item.locator("div").first
            classes = icon_div.get_attribute("class") or ""
            assert "green" in classes, f"Expected green icon, got: {classes}"

    def test_no_validation_text_hidden_after_check(self, app_page: Page) -> None:
        """'No validation performed yet.' disappears once a check has run."""
        mp = _start_and_verify(app_page)
        expect(mp.no_validation_text).to_have_count(0)

    def test_pass_dot_indicator_appears_in_task_list(self, app_page: Page) -> None:
        """After a PASS check, a colored dot appears next to the task in the list."""
        mp = _start_and_verify(app_page)
        task1 = mp.get_task_item(1)
        # Green dot: bg-green-500 rounded-full
        dot = task1.locator(".bg-green-500.rounded-full")
        expect(dot).to_be_visible()


# ---------------------------------------------------------------------------
# FAIL result
# ---------------------------------------------------------------------------

class TestCheckResultFail:
    def test_fail_result_status_text(self, app_page_check_fail: Page) -> None:
        """Result card shows 'Result: FAIL'."""
        mp = _start_and_verify(app_page_check_fail)
        expect(mp.check_result_card).to_contain_text("FAIL")

    def test_fail_result_summary_text(self, app_page_check_fail: Page) -> None:
        mp = _start_and_verify(app_page_check_fail)
        expect(mp.results_section).to_contain_text("1 of 3 checks failed")

    def test_fail_result_card_has_red_styling(self, app_page_check_fail: Page) -> None:
        """FAIL card carries Tailwind red classes."""
        mp = _start_and_verify(app_page_check_fail)
        card_classes = mp.check_result_card.get_attribute("class") or ""
        assert "red" in card_classes, f"Expected red classes, got: {card_classes}"

    def test_fail_failing_detail_has_red_icon(self, app_page_check_fail: Page) -> None:
        """The detail row that failed has a red icon."""
        mp = _start_and_verify(app_page_check_fail)
        # Second detail row (index 1) is the failing one
        failing_item = mp.check_detail_items.nth(1)
        icon_div = failing_item.locator("div").first
        classes = icon_div.get_attribute("class") or ""
        assert "red" in classes, f"Expected red icon for failing detail, got: {classes}"

    def test_fail_passing_details_have_green_icons(self, app_page_check_fail: Page) -> None:
        """The two passing detail rows have green icons."""
        mp = _start_and_verify(app_page_check_fail)
        for idx in (0, 2):
            item = mp.check_detail_items.nth(idx)
            icon_div = item.locator("div").first
            classes = icon_div.get_attribute("class") or ""
            assert "green" in classes, f"Item {idx}: expected green icon, got: {classes}"

    def test_fail_failure_message_shown(self, app_page_check_fail: Page) -> None:
        """Failure message text from mock is displayed."""
        mp = _start_and_verify(app_page_check_fail)
        expect(mp.results_section).to_contain_text("Expected 172.25.250.254, got 192.168.1.1")

    def test_fail_dot_indicator_is_red_in_task_list(self, app_page_check_fail: Page) -> None:
        """After a FAIL check, a red dot appears next to the task in the list."""
        mp = _start_and_verify(app_page_check_fail)
        task1 = mp.get_task_item(1)
        dot = task1.locator(".bg-red-500.rounded-full")
        expect(dot).to_be_visible()
