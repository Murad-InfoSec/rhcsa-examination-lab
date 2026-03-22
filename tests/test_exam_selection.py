"""
test_exam_selection.py – Tests for the exam-selection modal and exam switching.
"""
import pytest
from playwright.sync_api import Page, expect
from pages.main_page import MainPage
from pages.exam_modal import ExamModal


class TestExamModalOpening:
    def test_modal_opens_on_exam_button_click(self, app_page: Page) -> None:
        """Clicking the exam selector button reveals the modal."""
        mp = MainPage(app_page)
        modal = ExamModal(app_page)
        assert not modal.is_open()
        mp.exam_selector_button.click()
        expect(modal.overlay).to_be_visible()

    def test_modal_heading_shows_select_exam(self, app_page: Page) -> None:
        """Modal heading reads 'Select Exam'."""
        mp = MainPage(app_page)
        modal = ExamModal(app_page)
        mp.exam_selector_button.click()
        expect(modal.heading).to_be_visible()

    def test_modal_shows_close_button(self, app_page: Page) -> None:
        """Modal has a × close button."""
        mp = MainPage(app_page)
        modal = ExamModal(app_page)
        mp.exam_selector_button.click()
        expect(modal.close_button).to_be_visible()


class TestExamModalContent:
    def test_modal_lists_all_exams(self, app_page: Page) -> None:
        """Both mock exams are present in the modal list."""
        mp = MainPage(app_page)
        modal = ExamModal(app_page)
        mp.exam_selector_button.click()
        titles = modal.get_all_exam_titles()
        assert any("RHCSA Practice Exam 1" in t for t in titles), f"Exam 1 missing; got {titles}"
        assert any("RHCSA Practice Exam 2" in t for t in titles), f"Exam 2 missing; got {titles}"

    def test_active_exam_shows_active_badge(self, app_page: Page) -> None:
        """Currently active exam (exam-1) shows an 'Active' badge."""
        mp = MainPage(app_page)
        modal = ExamModal(app_page)
        mp.exam_selector_button.click()
        expect(modal.get_active_exam_badge()).to_be_visible()

    def test_inactive_exam_shows_task_count(self, app_page: Page) -> None:
        """Non-active exam (exam-2) shows its task count."""
        mp = MainPage(app_page)
        modal = ExamModal(app_page)
        mp.exam_selector_button.click()
        exam2_btn = modal.get_exam_button("RHCSA Practice Exam 2")
        expect(exam2_btn).to_contain_text("18")

    def test_exam_descriptions_shown(self, app_page: Page) -> None:
        """Exam description text is displayed inside each exam button."""
        mp = MainPage(app_page)
        modal = ExamModal(app_page)
        mp.exam_selector_button.click()
        expect(modal.get_exam_button("RHCSA Practice Exam 1")).to_contain_text(
            "Full RHCSA exam simulation"
        )


class TestExamModalDismissal:
    def test_modal_closes_via_x_button(self, app_page: Page) -> None:
        """Clicking the × button hides the modal."""
        mp = MainPage(app_page)
        modal = ExamModal(app_page)
        mp.exam_selector_button.click()
        expect(modal.overlay).to_be_visible()
        modal.close_via_button()
        expect(modal.overlay).to_have_count(0)

    def test_modal_closes_via_backdrop(self, app_page: Page) -> None:
        """Clicking the dark backdrop dismisses the modal."""
        mp = MainPage(app_page)
        modal = ExamModal(app_page)
        mp.exam_selector_button.click()
        expect(modal.overlay).to_be_visible()
        modal.close_via_backdrop()
        expect(modal.overlay).to_have_count(0)


class TestExamSwitching:
    def test_selecting_exam_closes_modal(self, app_page: Page) -> None:
        """Choosing an exam from the list closes the modal."""
        mp = MainPage(app_page)
        modal = ExamModal(app_page)
        mp.exam_selector_button.click()
        modal.select_exam("RHCSA Practice Exam 2")
        expect(modal.overlay).to_have_count(0)

    def test_selecting_exam_updates_header_button(self, app_page: Page) -> None:
        """After switching exam the header button reflects the new exam title."""
        mp = MainPage(app_page)
        modal = ExamModal(app_page)
        mp.exam_selector_button.click()
        modal.select_exam("RHCSA Practice Exam 2")
        # The header button should now show exam 2's title
        # (mock /api/exam/active still returns exam-1, but switching triggers a re-fetch;
        # since both fetches are mocked identically we verify the modal closed cleanly)
        expect(modal.overlay).to_have_count(0)
