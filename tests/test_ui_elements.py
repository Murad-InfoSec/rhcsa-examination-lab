"""
test_ui_elements.py – Verify all static UI elements render correctly on load.
Covers: header, panel toggles, task registry, instructions panel, terminal panel,
results panel, and the VM-unreachable error state.
"""
import pytest
from playwright.sync_api import Page, expect
from pages.main_page import MainPage


# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------

class TestHeader:
    def test_app_title_text(self, app_page: Page) -> None:
        """Main heading shows 'RHCSA Examination Lab'."""
        mp = MainPage(app_page)
        expect(mp.app_title).to_contain_text("RHCSA")
        expect(mp.app_title).to_contain_text("Examination Lab")

    def test_red_hat_icon_present(self, app_page: Page) -> None:
        """SVG icon is rendered inside the header."""
        mp = MainPage(app_page)
        expect(mp.header.locator("svg").first).to_be_visible()

    def test_exam_selector_button_shows_active_exam(self, app_page: Page) -> None:
        """Exam button in header displays the currently active exam title."""
        mp = MainPage(app_page)
        expect(mp.exam_selector_button).to_be_visible()
        expect(mp.exam_selector_button).to_contain_text("RHCSA Practice Exam 1")

    def test_all_panel_toggle_buttons_present(self, app_page: Page) -> None:
        """All four panel toggle buttons (Tasks, Instructions, Terminal, Results) exist."""
        mp = MainPage(app_page)
        for label in ("Tasks", "Instructions", "Terminal", "Results"):
            expect(mp.get_panel_toggle(label)).to_be_visible(), f"{label} toggle missing"

    def test_panel_toggle_buttons_are_pressed_by_default(self, app_page: Page) -> None:
        """All panels are visible by default (aria-pressed=true)."""
        mp = MainPage(app_page)
        for label in ("Tasks", "Instructions", "Terminal", "Results"):
            assert mp.get_panel_toggle_aria_pressed(label) == "true", (
                f"Panel '{label}' should be active on initial load"
            )

    def test_panel_toggle_buttons_have_icons(self, app_page: Page) -> None:
        """Each toggle button contains an SVG icon."""
        mp = MainPage(app_page)
        for label in ("Tasks", "Instructions", "Terminal", "Results"):
            btn = mp.get_panel_toggle(label)
            expect(btn.locator("svg")).to_be_visible()


# ---------------------------------------------------------------------------
# Task Panel
# ---------------------------------------------------------------------------

class TestTaskPanel:
    def test_task_registry_heading_visible(self, app_page: Page) -> None:
        mp = MainPage(app_page)
        expect(mp.task_registry_heading).to_be_visible()

    def test_task_count_badge_shows_total(self, app_page: Page) -> None:
        """Badge shows '4 Total' matching the 4 mock tasks."""
        mp = MainPage(app_page)
        expect(mp.task_count_badge).to_contain_text("4")
        expect(mp.task_count_badge).to_contain_text("Total")

    def test_node_group_headers_present(self, app_page: Page) -> None:
        """Node group labels (standard, lvm, boot-menu) render in the task panel."""
        mp = MainPage(app_page)
        headers = mp.get_node_group_headers()
        groups = [h.strip().lower() for h in headers if h.strip()]
        assert "standard" in groups
        assert "lvm" in groups
        assert "boot-menu" in groups

    def test_task_items_display_id_badge(self, app_page: Page) -> None:
        """Task 1 item shows badge '01' and task 17 item shows '17'."""
        mp = MainPage(app_page)
        expect(mp.get_task_item(1)).to_contain_text("01")
        expect(mp.get_task_item(17)).to_contain_text("17")

    def test_task_items_display_titles(self, app_page: Page) -> None:
        """Task items display their titles."""
        mp = MainPage(app_page)
        expect(mp.get_task_item(1)).to_contain_text("Network Configuration")
        expect(mp.get_task_item(2)).to_contain_text("YUM Repositories")
        expect(mp.get_task_item(15)).to_contain_text("Root Password Reset")
        expect(mp.get_task_item(17)).to_contain_text("Resize Logical Volume")

    def test_first_task_is_active_by_default(self, app_page: Page) -> None:
        """Task 1 is pre-selected on load (highlighted with red accent)."""
        mp = MainPage(app_page)
        # Active task item has a red-background badge
        task1_btn = mp.get_task_item(1)
        active_badge = task1_btn.locator(".bg-red-600")
        expect(active_badge).to_be_visible()

    def test_initial_task_status_is_idle(self, app_page: Page) -> None:
        """All tasks start in IDLE status (DOM text is lowercase; CSS renders it uppercase)."""
        mp = MainPage(app_page)
        for task_id in (1, 2, 17):
            item = mp.get_task_item(task_id)
            expect(item).to_contain_text("idle")


# ---------------------------------------------------------------------------
# Instructions Panel
# ---------------------------------------------------------------------------

class TestInstructionsPanel:
    def test_task_id_badge_shows_task_1(self, app_page: Page) -> None:
        """Active task ID badge shows 'TASK 1'."""
        mp = MainPage(app_page)
        expect(mp.task_id_badge).to_contain_text("TASK")
        expect(mp.task_id_badge).to_contain_text("1")

    def test_task_title_heading_shown(self, app_page: Page) -> None:
        """Instructions panel h2 shows the active task title."""
        mp = MainPage(app_page)
        expect(mp.task_title_heading).to_contain_text("Network Configuration")

    def test_instructions_content_rendered(self, app_page: Page) -> None:
        """Task instructions text is visible in the instructions box."""
        mp = MainPage(app_page)
        expect(mp.instructions_content_box).to_contain_text("172.25.250.11")

    def test_start_button_present_and_enabled(self, app_page: Page) -> None:
        mp = MainPage(app_page)
        expect(mp.start_button).to_be_visible()
        expect(mp.start_button).to_be_enabled()

    def test_stop_button_present_and_disabled(self, app_page: Page) -> None:
        """Stop is disabled when task is IDLE."""
        mp = MainPage(app_page)
        expect(mp.stop_button).to_be_visible()
        expect(mp.stop_button).to_be_disabled()

    def test_reset_button_present_and_enabled(self, app_page: Page) -> None:
        mp = MainPage(app_page)
        expect(mp.reset_button).to_be_visible()
        expect(mp.reset_button).to_be_enabled()

    def test_verify_button_present_and_disabled(self, app_page: Page) -> None:
        """Verify Task Completion button is disabled when task is not RUNNING."""
        mp = MainPage(app_page)
        expect(mp.verify_button).to_be_visible()
        expect(mp.verify_button).to_be_disabled()

    def test_instruction_bullet_points_rendered(self, app_page: Page) -> None:
        """Bullet list items from the markdown-like instructions are shown."""
        mp = MainPage(app_page)
        expect(mp.instructions_content_box).to_contain_text("IP address")
        expect(mp.instructions_content_box).to_contain_text("Default gateway")


# ---------------------------------------------------------------------------
# Terminal Panel
# ---------------------------------------------------------------------------

class TestTerminalPanel:
    def test_terminal_heading_visible(self, app_page: Page) -> None:
        mp = MainPage(app_page)
        expect(mp.terminal_heading).to_be_visible()

    def test_terminal_heading_not_vnc_for_standard_task(self, app_page: Page) -> None:
        """For a standard (non-boot-menu) task the heading reads 'Live Terminal'."""
        mp = MainPage(app_page)
        expect(mp.terminal_heading).to_have_text("Live Terminal")

    def test_online_badge_absent_when_idle(self, app_page: Page) -> None:
        """The green 'Online' indicator is hidden when task is not RUNNING."""
        mp = MainPage(app_page)
        expect(mp.terminal_online_badge).to_have_count(0)


# ---------------------------------------------------------------------------
# Results Panel
# ---------------------------------------------------------------------------

class TestResultsPanel:
    def test_validation_results_heading_visible(self, app_page: Page) -> None:
        mp = MainPage(app_page)
        expect(mp.results_heading).to_be_visible()

    def test_no_validation_placeholder_shown(self, app_page: Page) -> None:
        """Before any check the panel shows 'No validation performed yet.'"""
        mp = MainPage(app_page)
        expect(mp.no_validation_text).to_be_visible()

    def test_check_result_card_not_present_initially(self, app_page: Page) -> None:
        mp = MainPage(app_page)
        expect(mp.check_result_card).to_have_count(0)


# ---------------------------------------------------------------------------
# VM Unreachable State
# ---------------------------------------------------------------------------

class TestVMUnreachable:
    def test_vm_unreachable_heading_shown(self, app_page_vm_down: Page) -> None:
        mp = MainPage(app_page_vm_down)
        expect(mp.vm_unreachable_heading).to_be_visible()

    def test_retry_connection_button_shown(self, app_page_vm_down: Page) -> None:
        mp = MainPage(app_page_vm_down)
        expect(mp.retry_connection_button).to_be_visible()
        expect(mp.retry_connection_button).to_be_enabled()

    def test_task_registry_hidden_when_vm_down(self, app_page_vm_down: Page) -> None:
        """Main content is replaced by the error card when VM is unreachable."""
        mp = MainPage(app_page_vm_down)
        expect(mp.task_registry_heading).to_have_count(0)
