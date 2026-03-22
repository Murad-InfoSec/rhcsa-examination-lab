"""Base Page Object with shared helpers."""
from playwright.sync_api import Page, Locator


class BasePage:
    def __init__(self, page: Page) -> None:
        self.page = page

    def get_by_text(self, text: str) -> Locator:
        return self.page.get_by_text(text)

    def is_visible(self, selector: str) -> bool:
        return self.page.locator(selector).is_visible()
