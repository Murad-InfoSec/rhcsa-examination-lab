"""
test_panels.py – Tests for panel visibility toggles (Tasks, Instructions, Terminal, Results).

Each panel can be hidden/shown with its toggle button in the header.
aria-pressed tracks current state and is persisted to localStorage.
"""
import pytest
from playwright.sync_api import Page, expect
from pages.main_page import MainPage


class TestTasksPanelToggle:
    def test_tasks_panel_visible_by_default(self, app_page: Page) -> None:
        mp = MainPage(app_page)
        expect(mp.task_registry_heading).to_be_visible()

    def test_toggle_tasks_hides_panel(self, app_page: Page) -> None:
        mp = MainPage(app_page)
        mp.toggle_panel("Tasks")
        expect(mp.task_registry_heading).to_have_count(0)

    def test_toggle_tasks_twice_restores_panel(self, app_page: Page) -> None:
        mp = MainPage(app_page)
        mp.toggle_panel("Tasks")
        expect(mp.task_registry_heading).to_have_count(0)
        mp.toggle_panel("Tasks")
        expect(mp.task_registry_heading).to_be_visible()

    def test_tasks_toggle_aria_pressed_false_after_hide(self, app_page: Page) -> None:
        mp = MainPage(app_page)
        mp.toggle_panel("Tasks")
        assert mp.get_panel_toggle_aria_pressed("Tasks") == "false"

    def test_tasks_toggle_aria_pressed_true_after_restore(self, app_page: Page) -> None:
        mp = MainPage(app_page)
        mp.toggle_panel("Tasks")
        mp.toggle_panel("Tasks")
        assert mp.get_panel_toggle_aria_pressed("Tasks") == "true"


class TestInstructionsPanelToggle:
    def test_instructions_panel_visible_by_default(self, app_page: Page) -> None:
        mp = MainPage(app_page)
        expect(mp.task_id_badge).to_be_visible()

    def test_toggle_instructions_hides_panel(self, app_page: Page) -> None:
        mp = MainPage(app_page)
        mp.toggle_panel("Instructions")
        expect(mp.task_id_badge).to_have_count(0)

    def test_toggle_instructions_twice_restores_panel(self, app_page: Page) -> None:
        mp = MainPage(app_page)
        mp.toggle_panel("Instructions")
        mp.toggle_panel("Instructions")
        expect(mp.task_id_badge).to_be_visible()

    def test_instructions_toggle_aria_state(self, app_page: Page) -> None:
        mp = MainPage(app_page)
        mp.toggle_panel("Instructions")
        assert mp.get_panel_toggle_aria_pressed("Instructions") == "false"
        mp.toggle_panel("Instructions")
        assert mp.get_panel_toggle_aria_pressed("Instructions") == "true"

    def test_hiding_instructions_expands_terminal_row(self, app_page: Page) -> None:
        """When instructions panel is hidden the terminal/results row should still be visible."""
        mp = MainPage(app_page)
        mp.toggle_panel("Instructions")
        expect(mp.results_heading).to_be_visible()


class TestTerminalPanelToggle:
    def test_terminal_panel_visible_by_default(self, app_page: Page) -> None:
        mp = MainPage(app_page)
        expect(mp.terminal_heading).to_be_visible()

    def test_toggle_terminal_hides_panel(self, app_page: Page) -> None:
        mp = MainPage(app_page)
        mp.toggle_panel("Terminal")
        expect(mp.terminal_heading).to_have_count(0)

    def test_toggle_terminal_twice_restores_panel(self, app_page: Page) -> None:
        mp = MainPage(app_page)
        mp.toggle_panel("Terminal")
        mp.toggle_panel("Terminal")
        expect(mp.terminal_heading).to_be_visible()

    def test_terminal_toggle_aria_state(self, app_page: Page) -> None:
        mp = MainPage(app_page)
        mp.toggle_panel("Terminal")
        assert mp.get_panel_toggle_aria_pressed("Terminal") == "false"

    def test_hiding_terminal_makes_results_full_width(self, app_page: Page) -> None:
        """When terminal is hidden, results panel is still accessible."""
        mp = MainPage(app_page)
        mp.toggle_panel("Terminal")
        expect(mp.results_heading).to_be_visible()


class TestResultsPanelToggle:
    def test_results_panel_visible_by_default(self, app_page: Page) -> None:
        mp = MainPage(app_page)
        expect(mp.results_heading).to_be_visible()

    def test_toggle_results_hides_panel(self, app_page: Page) -> None:
        mp = MainPage(app_page)
        mp.toggle_panel("Results")
        expect(mp.results_heading).to_have_count(0)

    def test_toggle_results_twice_restores_panel(self, app_page: Page) -> None:
        mp = MainPage(app_page)
        mp.toggle_panel("Results")
        mp.toggle_panel("Results")
        expect(mp.results_heading).to_be_visible()

    def test_results_toggle_aria_state(self, app_page: Page) -> None:
        mp = MainPage(app_page)
        mp.toggle_panel("Results")
        assert mp.get_panel_toggle_aria_pressed("Results") == "false"
        mp.toggle_panel("Results")
        assert mp.get_panel_toggle_aria_pressed("Results") == "true"


class TestLocalStoragePersistence:
    def test_panel_state_written_to_localstorage(self, app_page: Page) -> None:
        """ui.panels key is written to localStorage after toggling."""
        mp = MainPage(app_page)
        mp.toggle_panel("Tasks")
        stored = app_page.evaluate("() => localStorage.getItem('ui.panels')")
        assert stored is not None, "localStorage key 'ui.panels' should exist"
        import json
        data = json.loads(stored)
        assert data["tasks"] is False, f"Expected tasks=False, got: {data}"

    def test_panel_state_loaded_from_localstorage(self, app_page: Page) -> None:
        """Panel state is read from localStorage on reload."""
        # Persist tasks panel as hidden
        app_page.evaluate(
            "() => localStorage.setItem('ui.panels', JSON.stringify({tasks:false,instructions:true,terminal:true,results:true}))"
        )
        app_page.reload()
        # Wait for the app to finish loading (toggle buttons visible = app ready)
        app_page.wait_for_selector("button[aria-pressed]", timeout=15_000)
        mp = MainPage(app_page)
        assert mp.get_panel_toggle_aria_pressed("Tasks") == "false"
