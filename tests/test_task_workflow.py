"""
test_task_workflow.py – Tests for task selection and Start/Stop/Reset/Check flows.

Note: StatusBadge renders DOM text in lowercase (idle/running/stopped/…) while
CSS text-transform:uppercase makes it appear uppercase visually.
"""
import pytest
from playwright.sync_api import Page, expect
from pages.main_page import MainPage


class TestTaskSelection:
    def test_selecting_task_updates_id_badge(self, app_page: Page) -> None:
        """Clicking task 2 changes the instructions badge from TASK 1 to TASK 2."""
        mp = MainPage(app_page)
        expect(mp.task_id_badge).to_contain_text("1")
        mp.select_task(2)
        expect(mp.task_id_badge).to_contain_text("2")

    def test_selecting_task_updates_title(self, app_page: Page) -> None:
        """Clicking task 2 updates the instructions panel title."""
        mp = MainPage(app_page)
        mp.select_task(2)
        expect(mp.task_title_heading).to_contain_text("YUM Repositories")

    def test_selecting_task_updates_instructions(self, app_page: Page) -> None:
        """Clicking task 2 shows task 2's instructions text."""
        mp = MainPage(app_page)
        mp.select_task(2)
        expect(mp.instructions_content_box).to_contain_text("BaseOS")

    def test_selecting_task_highlights_it(self, app_page: Page) -> None:
        """After clicking task 2, its item gains the red active badge."""
        mp = MainPage(app_page)
        mp.select_task(2)
        task2_btn = mp.get_task_item(2)
        active_badge = task2_btn.locator(".bg-red-600")
        expect(active_badge).to_be_visible()

    def test_selecting_boot_menu_task_changes_terminal_label(self, app_page: Page) -> None:
        """Selecting a boot-menu node task changes the terminal header to 'VNC Console'."""
        mp = MainPage(app_page)
        mp.select_task(15)
        expect(mp.vnc_heading).to_be_visible()

    def test_selecting_standard_task_shows_live_terminal(self, app_page: Page) -> None:
        """Selecting a standard node task shows 'Live Terminal' heading."""
        mp = MainPage(app_page)
        # Navigate away then back to a standard task
        mp.select_task(17)
        mp.select_task(1)
        expect(mp.terminal_heading).to_be_visible()
        expect(mp.terminal_heading).to_have_text("Live Terminal")


class TestStartStopWorkflow:
    def test_start_sets_task_to_running(self, app_page: Page) -> None:
        """Clicking Start transitions status badge to 'running'."""
        mp = MainPage(app_page)
        mp.click_start()
        expect(mp.get_task_item(1)).to_contain_text("running")

    def test_start_disables_start_button(self, app_page: Page) -> None:
        """After starting, the Start button becomes disabled."""
        mp = MainPage(app_page)
        mp.click_start()
        expect(mp.start_button).to_be_disabled()

    def test_start_enables_stop_button(self, app_page: Page) -> None:
        """After starting, the Stop button becomes enabled."""
        mp = MainPage(app_page)
        mp.click_start()
        expect(mp.stop_button).to_be_enabled()

    def test_start_enables_verify_button(self, app_page: Page) -> None:
        """After starting, the Verify Task Completion button becomes enabled."""
        mp = MainPage(app_page)
        mp.click_start()
        expect(mp.verify_button).to_be_enabled()

    def test_start_shows_online_indicator(self, app_page: Page) -> None:
        """Running task shows the green 'Online' badge in the terminal panel."""
        mp = MainPage(app_page)
        mp.click_start()
        expect(mp.terminal_online_badge).to_be_visible()

    def test_stop_sets_task_to_stopped(self, app_page: Page) -> None:
        """Starting then Stopping transitions status badge to 'stopped'."""
        mp = MainPage(app_page)
        mp.click_start()
        expect(mp.stop_button).to_be_enabled()
        mp.click_stop()
        expect(mp.get_task_item(1)).to_contain_text("stopped")

    def test_stop_re_enables_start_button(self, app_page: Page) -> None:
        """After stopping, Start is enabled again."""
        mp = MainPage(app_page)
        mp.click_start()
        expect(mp.stop_button).to_be_enabled()
        mp.click_stop()
        expect(mp.start_button).to_be_enabled()

    def test_stop_disables_verify_button(self, app_page: Page) -> None:
        """After stopping, the Verify button is disabled."""
        mp = MainPage(app_page)
        mp.click_start()
        mp.click_stop()
        expect(mp.verify_button).to_be_disabled()


class TestResetWorkflow:
    def test_reset_button_always_enabled_when_idle(self, app_page: Page) -> None:
        mp = MainPage(app_page)
        expect(mp.reset_button).to_be_enabled()

    def test_reset_button_always_enabled_when_running(self, app_page: Page) -> None:
        mp = MainPage(app_page)
        mp.click_start()
        expect(mp.reset_button).to_be_enabled()

    def test_reset_transitions_to_running(self, app_page: Page) -> None:
        """Clicking Reset brings the task to RUNNING (mock API returns ok=true)."""
        mp = MainPage(app_page)
        mp.click_reset()
        expect(mp.get_task_item(1)).to_contain_text("running")
