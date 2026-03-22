"""
Main Page Object for the RHCSA Examination Lab single-page application.

Encapsulates all locators and high-level interactions for the main UI.
"""
import re as _re
from playwright.sync_api import Page, Locator
from pages.base_page import BasePage


class MainPage(BasePage):
    def __init__(self, page: Page) -> None:
        super().__init__(page)

    # ------------------------------------------------------------------
    # Header
    # ------------------------------------------------------------------

    @property
    def header(self) -> Locator:
        return self.page.locator("header").first

    @property
    def app_title(self) -> Locator:
        return self.page.locator("h1").first

    @property
    def exam_selector_button(self) -> Locator:
        return self.header.locator("button").filter(has_text="RHCSA Practice")

    def get_panel_toggle(self, label: str) -> Locator:
        return self.page.locator("button[aria-pressed]").filter(has_text=label)

    def toggle_panel(self, label: str) -> None:
        self.get_panel_toggle(label).click()

    def get_panel_toggle_aria_pressed(self, label: str) -> str:
        return self.get_panel_toggle(label).get_attribute("aria-pressed") or "false"

    # ------------------------------------------------------------------
    # Task Panel
    # ------------------------------------------------------------------

    @property
    def task_registry_section(self) -> Locator:
        return self.page.locator("section").filter(has_text="Task Registry").first

    @property
    def task_registry_heading(self) -> Locator:
        return self.page.get_by_text("Task Registry")

    @property
    def task_count_badge(self) -> Locator:
        return self.task_registry_section.locator("span").filter(has_text="Total")

    def get_task_item(self, task_id: int) -> Locator:
        badge = f"{task_id:02d}" if task_id < 10 else str(task_id)
        return self.task_registry_section.locator("button").filter(has_text=badge).first

    def select_task(self, task_id: int) -> None:
        self.get_task_item(task_id).click()

    def get_node_group_headers(self) -> list[str]:
        return self.task_registry_section.locator(
            "span.font-black.tracking-widest"
        ).all_text_contents()

    # ------------------------------------------------------------------
    # Instructions Panel
    # ------------------------------------------------------------------

    @property
    def instructions_section(self) -> Locator:
        # Use case-sensitive regex so "Task Registry" (capital T) does NOT match
        return self.page.locator("section").filter(
            has_text=_re.compile(r"TASK \d+")
        ).first

    @property
    def task_id_badge(self) -> Locator:
        """Badge span reading 'TASK N' in the instructions area."""
        return self.page.locator("span.font-mono").filter(has_text=_re.compile(r"TASK \d+"))

    @property
    def task_title_heading(self) -> Locator:
        # Only one h2 exists when the exam modal is closed
        return self.page.locator("h2").first

    @property
    def instructions_content_box(self) -> Locator:
        # The rounded box wrapping the Instructions component (rounded-xl border)
        return self.instructions_section.locator("div.rounded-xl.border").first

    @property
    def start_button(self) -> Locator:
        return self.page.get_by_role("button", name="Start", exact=True)

    @property
    def stop_button(self) -> Locator:
        return self.page.get_by_role("button", name="Stop", exact=True)

    @property
    def reset_button(self) -> Locator:
        return self.page.get_by_role("button", name="Reset", exact=True)

    @property
    def verify_button(self) -> Locator:
        return self.page.get_by_role("button", name="Verify Task Completion")

    def click_start(self) -> None:
        self.start_button.click()

    def click_stop(self) -> None:
        self.stop_button.click()

    def click_reset(self) -> None:
        self.reset_button.click()

    def click_verify(self) -> None:
        self.verify_button.click()

    # ------------------------------------------------------------------
    # Terminal / Console Panel
    # ------------------------------------------------------------------

    @property
    def terminal_heading(self) -> Locator:
        return self.page.get_by_text("Live Terminal")

    @property
    def vnc_heading(self) -> Locator:
        return self.page.get_by_role("heading", name="VNC Console")

    @property
    def terminal_online_badge(self) -> Locator:
        return self.page.get_by_text("Online")

    # ------------------------------------------------------------------
    # Results Panel
    # ------------------------------------------------------------------

    @property
    def results_section(self) -> Locator:
        return self.page.locator("section").filter(has_text="Validation Results").first

    @property
    def results_heading(self) -> Locator:
        return self.page.get_by_text("Validation Results")

    @property
    def no_validation_text(self) -> Locator:
        return self.page.get_by_text("No validation performed yet.")

    @property
    def check_result_card(self) -> Locator:
        # The rounded colored status card (NOT the plain p-4 container div)
        return self.results_section.locator("div.rounded-xl").filter(has_text="Result:").first

    @property
    def check_detail_items(self) -> Locator:
        """All individual check-detail rows (rounded-lg bg-slate-800)."""
        return self.results_section.locator("div.rounded-lg.bg-slate-800")

    # ------------------------------------------------------------------
    # VM-Unreachable State
    # ------------------------------------------------------------------

    @property
    def vm_unreachable_heading(self) -> Locator:
        return self.page.get_by_text("VM Unreachable")

    @property
    def retry_connection_button(self) -> Locator:
        return self.page.get_by_role("button", name="Retry Connection")
