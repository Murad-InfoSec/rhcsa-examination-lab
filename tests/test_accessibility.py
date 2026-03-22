"""
test_accessibility.py – WCAG 2.1 / WAI-ARIA accessibility tests.

Four layers of coverage:

  1. TestAxeAudit        – axe-core automated audit for critical/serious violations
  2. TestAriaAttributes  – Explicit ARIA roles, labels, and states on key widgets
  3. TestKeyboardNav     – Keyboard operability: Tab focus, Enter/Space activation
  4. TestSemanticMarkup  – Correct heading hierarchy and landmark regions

axe-playwright-python (https://pypi.org/project/axe-playwright-python/) is used
for automated WCAG scanning; it bundles axe-core so no CDN or npm is needed.
Tests that depend on axe are skipped when the package is not installed.

All tests run against a fully loaded page backed by the mock API, so they
are deterministic and do not require a real VM.
"""

from __future__ import annotations

import os
import sys
from typing import Any

import pytest
from playwright.sync_api import Page, expect

# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------
sys.path.insert(0, os.path.dirname(__file__))
from conftest import build_mock_router, BASE_URL
from pages.main_page import MainPage
from pages.exam_modal import ExamModal

# ---------------------------------------------------------------------------
# axe-playwright-python availability guard
# ---------------------------------------------------------------------------
try:
    from axe_playwright_python.sync_playwright import Axe  # type: ignore

    _AXE_AVAILABLE = True
except ImportError:
    _AXE_AVAILABLE = False

skip_no_axe = pytest.mark.skipif(
    not _AXE_AVAILABLE,
    reason="axe-playwright-python not installed — run: pip install axe-playwright-python",
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _format_violations(violations: list[dict[str, Any]]) -> str:
    """Format axe violation objects into a readable multi-line string."""
    lines = []
    for v in violations:
        impact = v.get("impact", "?").upper()
        rule_id = v.get("id", "?")
        desc = v.get("description", "")
        nodes = v.get("nodes", [])
        html_samples = "; ".join(
            n.get("html", "")[:100] for n in nodes[:3]
        )
        lines.append(f"[{impact}] {rule_id}: {desc}")
        if html_samples:
            lines.append(f"  Affected: {html_samples}")
    return "\n".join(lines)


def _run_axe(page: Page) -> dict[str, Any]:
    """
    Run axe-core against *page* and return the raw response dict.

    axe-playwright-python v0.1.x bundles axe-core; no CDN required.
    We request both violations AND passes so the results are complete.
    """
    axe = Axe()
    results = axe.run(page, options={"resultTypes": ["violations", "passes"]})
    return results.response  # raw dict: {"violations": [...], "passes": [...], ...}


# ===========================================================================
# 0. Shared fixture
# ===========================================================================

@pytest.fixture
def loaded_page(page: Page) -> Page:
    """Navigate to the app with mocked APIs and wait for full load."""
    page.route("**/api/**", build_mock_router())
    page.goto(BASE_URL)
    page.wait_for_selector("text=Task Registry", timeout=15_000)
    return page


# ===========================================================================
# 1. Automated axe-core audit
# ===========================================================================

class TestAxeAudit:
    """
    Run axe-core on every major view and assert zero critical/serious violations.
    axe checks include: ARIA, colour-contrast, keyboard access, form labels,
    heading order, landmark regions, and 60+ other WCAG 2.1 rules.
    """

    @skip_no_axe
    def test_no_critical_violations_on_main_page(self, loaded_page: Page):
        """
        axe-core must find zero 'critical' impact violations on the fully
        loaded main page. Critical violations block assistive technology users
        entirely (e.g., missing alternative text, keyboard traps).
        """
        results = _run_axe(loaded_page)
        critical = [v for v in results.get("violations", []) if v.get("impact") == "critical"]
        assert not critical, (
            f"Critical accessibility violations found:\n{_format_violations(critical)}"
        )

    @skip_no_axe
    def test_no_serious_violations_excluding_known_contrast(self, loaded_page: Page):
        """
        axe-core must find zero 'serious' violations on the main page.

        Covers keyboard traps, missing ARIA roles, and other WCAG 2.1 AA
        issues that axe rates as 'serious' impact.
        """
        results = _run_axe(loaded_page)
        serious = [
            v for v in results.get("violations", [])
            if v.get("impact") == "serious"
        ]
        assert not serious, (
            f"Serious violations found:\n"
            f"{_format_violations(serious)}"
        )

    @skip_no_axe
    def test_color_contrast(self, loaded_page: Page):
        """
        axe-core must report zero color-contrast violations.

        All text in the UI uses text-slate-300 or lighter on dark backgrounds,
        meeting the WCAG 2.1 AA minimum contrast ratio of 4.5:1.
        """
        results = _run_axe(loaded_page)
        contrast_violations = [
            v for v in results.get("violations", [])
            if v.get("id") == "color-contrast"
        ]
        assert not contrast_violations, (
            f"Color-contrast violations found:\n"
            f"{_format_violations(contrast_violations)}"
        )

    @skip_no_axe
    def test_scrollable_region_keyboard_access(self, loaded_page: Page):
        """
        All scrollable regions must be keyboard-accessible (WCAG 2.1 SC 2.1.1).

        Every overflow-y-auto container carries tabindex='0' so keyboard-only
        users can scroll the task list, instructions, and results panels.
        """
        results = _run_axe(loaded_page)
        scroll_violations = [
            v for v in results.get("violations", [])
            if v.get("id") == "scrollable-region-focusable"
        ]
        assert not scroll_violations, (
            f"scrollable-region-focusable violations found:\n"
            f"{_format_violations(scroll_violations)}"
        )

    @skip_no_axe
    def test_no_critical_violations_with_results_panel(self, loaded_page: Page):
        """
        After displaying a PASS check result the results panel introduces new
        DOM — axe must still report zero critical violations.
        """
        mp = MainPage(loaded_page)
        mp.click_start()
        loaded_page.wait_for_selector("text=running", timeout=5_000)
        mp.click_verify()
        loaded_page.wait_for_selector("text=Result:", timeout=5_000)

        results = _run_axe(loaded_page)
        critical = [v for v in results.get("violations", []) if v.get("impact") == "critical"]
        assert not critical, (
            f"Critical violations in results panel view:\n{_format_violations(critical)}"
        )

    @skip_no_axe
    def test_no_critical_violations_in_exam_modal(self, loaded_page: Page):
        """
        Opening the exam selection modal renders additional DOM — axe must
        find zero critical violations while the modal is open.
        """
        mp = MainPage(loaded_page)
        mp.exam_selector_button.click()
        loaded_page.wait_for_selector("text=Select Exam", timeout=5_000)

        results = _run_axe(loaded_page)
        critical = [v for v in results.get("violations", []) if v.get("impact") == "critical"]
        assert not critical, (
            f"Critical violations in exam modal:\n{_format_violations(critical)}"
        )

    @skip_no_axe
    def test_axe_passes_count_is_reasonable(self, loaded_page: Page):
        """
        axe-core must record at least 5 passing rules, confirming that the
        audit actually ran against real content (not an empty page).
        """
        results = _run_axe(loaded_page)
        passes = results.get("passes", [])
        assert len(passes) >= 5, (
            f"axe reported only {len(passes)} passing rules — audit may not have run"
        )


# ===========================================================================
# 2. Explicit ARIA attributes
# ===========================================================================

class TestAriaAttributes:
    """
    Verify ARIA attributes are present and correct on interactive elements.
    These tests do not require axe and run in all environments.
    """

    def test_panel_toggles_have_aria_pressed(self, loaded_page: Page):
        """
        All four panel toggle buttons carry the aria-pressed attribute.
        Screen readers use aria-pressed to announce toggle state (on/off).
        """
        toggles = loaded_page.locator("button[aria-pressed]")
        count = toggles.count()
        assert count == 4, (
            f"Expected 4 buttons with aria-pressed, found {count}. "
            "Missing aria-pressed breaks screen-reader toggle semantics."
        )

    def test_panel_toggles_aria_pressed_is_true_when_active(self, loaded_page: Page):
        """
        On initial load all panels are visible; every toggle's aria-pressed
        must be the string 'true'.
        """
        mp = MainPage(loaded_page)
        for label in ("Tasks", "Instructions", "Terminal", "Results"):
            value = mp.get_panel_toggle_aria_pressed(label)
            assert value == "true", (
                f"Panel '{label}' toggle has aria-pressed='{value}', expected 'true'"
            )

    def test_panel_toggles_aria_pressed_updates_on_click(self, loaded_page: Page):
        """
        Clicking a toggle must flip aria-pressed from 'true' to 'false' and back.
        A static aria-pressed value means the attribute is decorative only,
        which is misleading to screen readers.
        """
        mp = MainPage(loaded_page)
        assert mp.get_panel_toggle_aria_pressed("Results") == "true"
        mp.toggle_panel("Results")
        assert mp.get_panel_toggle_aria_pressed("Results") == "false", (
            "aria-pressed did not update to 'false' after hiding the Results panel"
        )
        mp.toggle_panel("Results")
        assert mp.get_panel_toggle_aria_pressed("Results") == "true", (
            "aria-pressed did not return to 'true' after re-showing the Results panel"
        )

    def test_action_buttons_have_accessible_text(self, loaded_page: Page):
        """
        Start, Stop, Reset, and Verify buttons all have non-empty accessible
        names derived from their text content. Empty names are invisible to
        screen readers.
        """
        for label in ("Start", "Stop", "Reset", "Verify Task Completion"):
            btn = loaded_page.get_by_role("button", name=label)
            assert btn.count() >= 1, f"Button with accessible name '{label}' not found"
            # Verify the text content is non-empty
            text = btn.first.text_content() or ""
            assert text.strip(), f"Button '{label}' has empty text content"

    def test_exam_selector_button_has_accessible_name(self, loaded_page: Page):
        """
        The exam selector button in the header must have a non-empty accessible
        name. Unlabelled buttons are announced as 'button' with no context.
        """
        mp = MainPage(loaded_page)
        name = mp.exam_selector_button.text_content() or ""
        assert name.strip(), (
            "Exam selector button has no accessible text content"
        )

    def test_main_heading_exists_and_is_non_empty(self, loaded_page: Page):
        """
        The page must have exactly one h1 with meaningful text.
        Multiple h1s or an empty h1 disorient screen-reader navigation.
        """
        h1_locators = loaded_page.locator("h1").all()
        assert len(h1_locators) == 1, (
            f"Expected exactly 1 h1, found {len(h1_locators)}"
        )
        h1_text = h1_locators[0].text_content() or ""
        assert h1_text.strip(), "h1 element is present but has empty text content"


# ===========================================================================
# 3. Keyboard navigation
# ===========================================================================

class TestKeyboardNavigation:
    """
    Verify that the application is operable with keyboard alone.
    Tab must reach all interactive elements; Enter/Space must activate buttons.
    """

    def test_tab_key_reaches_an_interactive_element(self, loaded_page: Page):
        """
        The first Tab keypress from the page body must move focus to an
        interactive element (button, link, or input).
        """
        loaded_page.keyboard.press("Tab")
        focused_tag = loaded_page.evaluate("() => document.activeElement.tagName")
        assert focused_tag in ("BUTTON", "A", "INPUT", "SELECT", "TEXTAREA"), (
            f"First Tab focused <{focused_tag}>, expected an interactive element"
        )

    def test_tab_cycles_through_all_toggle_buttons(self, loaded_page: Page):
        """
        Repeated Tab presses must eventually reach all four panel toggle buttons.
        If a toggle is unreachable via keyboard, it is inaccessible to keyboard-only users.
        """
        labels_found: set[str] = set()
        target_labels = {"Tasks", "Instructions", "Terminal", "Results"}

        for _ in range(30):  # max iterations to avoid infinite loop
            loaded_page.keyboard.press("Tab")
            focused = loaded_page.evaluate(
                "() => document.activeElement.textContent || ''"
            ).strip()
            for label in target_labels:
                if label in focused:
                    labels_found.add(label)
            if labels_found == target_labels:
                break

        missing = target_labels - labels_found
        assert not missing, (
            f"Could not reach toggle buttons via Tab: {missing}. "
            "These buttons may be missing from the tab order."
        )

    def test_enter_key_activates_focused_button(self, loaded_page: Page):
        """
        Pressing Enter on a focused button must trigger its action.
        Tests the Start button: focus it, press Enter, expect status change.
        """
        mp = MainPage(loaded_page)
        mp.start_button.focus()
        loaded_page.keyboard.press("Enter")
        # Start button triggers task start → status should change
        loaded_page.wait_for_selector("text=running", timeout=5_000)

    def test_space_key_activates_toggle_button(self, loaded_page: Page):
        """
        Space key on a focused toggle button must flip the panel visibility.
        WAI-ARIA button pattern requires both Enter and Space for activation.
        """
        mp = MainPage(loaded_page)
        results_toggle = mp.get_panel_toggle("Results")
        results_toggle.focus()
        assert mp.get_panel_toggle_aria_pressed("Results") == "true"
        loaded_page.keyboard.press("Space")
        assert mp.get_panel_toggle_aria_pressed("Results") == "false", (
            "Space key did not activate the Results toggle button"
        )

    def test_exam_modal_close_button_keyboard_accessible(self, loaded_page: Page):
        """
        The exam modal's × close button must be reachable and activatable
        via keyboard (Tab to focus, Enter to close).
        """
        mp = MainPage(loaded_page)
        modal = ExamModal(loaded_page)

        mp.exam_selector_button.click()
        loaded_page.wait_for_selector("text=Select Exam", timeout=5_000)

        # Focus and activate the close button via keyboard
        modal.close_button.focus()
        loaded_page.keyboard.press("Enter")
        expect(modal.overlay).to_have_count(0)


# ===========================================================================
# 4. Semantic markup
# ===========================================================================

class TestSemanticMarkup:
    """
    Verify correct heading hierarchy and landmark regions.
    Proper semantics help screen-reader users build a mental model of the page.
    """

    def test_exactly_one_h1(self, loaded_page: Page):
        """
        The page must have exactly one h1.
        Multiple h1s indicate a flat document structure unsuitable for navigation.
        """
        count = loaded_page.locator("h1").count()
        assert count == 1, f"Expected 1 h1, found {count}"

    def test_h1_contains_app_name(self, loaded_page: Page):
        """
        The h1 must include the application name 'RHCSA' so screen-reader
        users can identify the page's purpose immediately.
        """
        h1_text = loaded_page.locator("h1").first.text_content() or ""
        assert "RHCSA" in h1_text, (
            f"h1 does not contain 'RHCSA': '{h1_text}'"
        )

    def test_task_panel_uses_h3_for_section_heading(self, loaded_page: Page):
        """
        'Task Registry' is rendered as an h3 inside the task panel section.
        Correct heading nesting (h1 → h3 without skipping) aids navigation.
        """
        h3 = loaded_page.locator("h3").filter(has_text="Task Registry")
        assert h3.count() >= 1, (
            "'Task Registry' heading is not an h3 element — "
            "update the component to use <h3> for proper heading hierarchy"
        )

    def test_instructions_panel_uses_h2_for_task_title(self, loaded_page: Page):
        """
        The active task title in the instructions panel is an h2, one level
        below the page h1. Skipping heading levels creates gaps in navigation.
        """
        h2 = loaded_page.locator("h2").first
        h2_text = h2.text_content() or ""
        assert h2_text.strip(), "Instructions panel h2 is empty"

    def test_header_element_exists_as_landmark(self, loaded_page: Page):
        """
        The page has a <header> landmark element.
        Landmark regions allow screen-reader users to jump directly to the
        header without reading every element.
        """
        header_count = loaded_page.locator("header").count()
        assert header_count >= 1, (
            "No <header> landmark found — add a <header> element to enable "
            "landmark-based screen-reader navigation"
        )

    def test_main_element_exists_as_landmark(self, loaded_page: Page):
        """
        The page has a <main> landmark element wrapping the primary content.
        Screen readers rely on <main> to skip navigation and reach content fast.
        """
        main_count = loaded_page.locator("main").count()
        assert main_count >= 1, (
            "No <main> landmark found — wrap the primary content in a <main> element"
        )
