"""Page Object for the Exam Selection Modal."""
from playwright.sync_api import Page, Locator
from pages.base_page import BasePage


class ExamModal(BasePage):
    """Encapsulates the floating exam-selection modal."""

    def __init__(self, page: Page) -> None:
        super().__init__(page)

    @property
    def overlay(self) -> Locator:
        """The full-screen backdrop div."""
        return self.page.locator(".fixed.inset-0")

    @property
    def container(self) -> Locator:
        """The inner card that stops click-propagation."""
        return self.overlay.locator(".bg-slate-900.border.border-slate-700.rounded-xl")

    @property
    def heading(self) -> Locator:
        return self.container.get_by_text("Select Exam", exact=True)

    @property
    def close_button(self) -> Locator:
        return self.container.locator("button").filter(has_text="×")

    def get_exam_button(self, exam_title: str) -> Locator:
        """Return the exam list item button matching the given title."""
        return self.container.locator("button").filter(has_text=exam_title).first

    def get_all_exam_titles(self) -> list[str]:
        """Return the title text from each exam option button."""
        titles = []
        for btn in self.container.locator("button:not(:has-text('×'))").all():
            # Each exam button contains a <span> with the title
            span = btn.locator("span.font-semibold").first
            text = span.text_content()
            if text:
                titles.append(text.strip())
        return titles

    def is_open(self) -> bool:
        return self.overlay.is_visible()

    def close_via_button(self) -> None:
        self.close_button.click()

    def close_via_backdrop(self) -> None:
        """Click the backdrop (outside the card) to dismiss the modal."""
        box = self.container.bounding_box()
        if box:
            # Click far to the left of the card, still within the overlay
            self.overlay.click(position={"x": 5, "y": 5})

    def select_exam(self, exam_title: str) -> None:
        self.get_exam_button(exam_title).click()

    def get_active_exam_badge(self) -> Locator:
        """Return the 'Active' badge span inside the exam list."""
        return self.container.locator("span").filter(has_text="Active").first
