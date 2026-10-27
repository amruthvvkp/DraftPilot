"""Visual browser tour for DraftPilot with interactive on-screen demonstrations."""

import time
from pathlib import Path
from playwright.sync_api import sync_playwright

ARTIFACTS_DIR = Path("/Users/amruth.vithala/.gemini/antigravity/brain/b5742ae8-87ab-4665-9958-9c20ef62fd52")


def main() -> None:
    """Run an interactive on-screen visual inspection of DraftPilot workflows."""
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as playwright:
        # Launch headful browser so user sees every action on-screen
        browser = playwright.chromium.launch(
            headless=False,
            slow_mo=650,  # Slow down execution so interactions are visible
            args=["--start-maximized"],
        )
        context = browser.new_context(viewport={"width": 1440, "height": 900})
        page = context.new_page()

        print("[1/5] Opening Project Vault at http://localhost:9000 ...")
        page.goto("http://localhost:9000")
        page.wait_for_load_state("networkidle")
        time.sleep(1.0)
        page.screenshot(path=str(ARTIFACTS_DIR / "tour_01_vault.png"))

        print("[2/5] Opening Project Wizard and triggering AI Story Assistant ...")
        page.get_by_role("button", name="New project ＋").click()
        page.wait_for_selector("form.wizard")
        time.sleep(1.0)

        # Enter premise and spark story
        premise_input = page.get_by_label("Story premise spark")
        if premise_input.is_visible():
            premise_input.fill(
                "A disgraced astrophysicist detects rhythmic radio signals from Jupiter predicting earthquakes on Earth."
            )
            time.sleep(0.8)
            page.get_by_role("button", name="Spark story ✦").click()
            # Wait for AI assistant to populate fields
            page.wait_for_timeout(2000)

        page.screenshot(path=str(ARTIFACTS_DIR / "tour_02_wizard_sparked.png"))

        # Advance through Wizard steps
        print("Advancing through wizard steps...")
        continue_btn = page.get_by_role("button", name="Continue →")
        for _ in range(3):
            if continue_btn.is_visible():
                continue_btn.click()
                time.sleep(0.8)

        page.screenshot(path=str(ARTIFACTS_DIR / "tour_03_wizard_review.png"))

        # Create project
        create_btn = page.get_by_role("button", name="Create project ✦")
        if create_btn.is_visible():
            create_btn.click()
            page.wait_for_url("**/projects/*")
            page.wait_for_load_state("networkidle")
            time.sleep(2.0)

        print("[3/5] Inspecting Screenplay Workspace & Editor ...")
        page.wait_for_selector(".workspace-shell")
        time.sleep(1.0)
        page.screenshot(path=str(ARTIFACTS_DIR / "tour_04_workspace.png"))

        # Click an editor block and test bold formatting toolbar
        editor_blocks = page.locator("textarea.script-editor")
        if editor_blocks.count() > 0:
            editor_blocks.first.click()
            time.sleep(0.5)
            bold_btn = page.get_by_label("Bold text")
            if bold_btn.is_visible():
                bold_btn.click()
                time.sleep(0.5)

        page.screenshot(path=str(ARTIFACTS_DIR / "tour_05_editor_formatted.png"))

        # Toggle Timeline board to show timeline lanes and pacing
        timeline_toggle = page.get_by_role("button", name="Timeline board →")
        if timeline_toggle.is_visible():
            timeline_toggle.click()
            time.sleep(1.5)
            page.screenshot(path=str(ARTIFACTS_DIR / "tour_05b_timeline_board.png"))
            editor_toggle = page.get_by_role("button", name="← Editor")
            if editor_toggle.is_visible():
                editor_toggle.click()
                time.sleep(1.0)

        print("[4/5] Navigating to Provider Settings & Writer Profile ...")
        page.goto("http://localhost:9000/settings")
        page.wait_for_load_state("networkidle")
        time.sleep(1.0)

        # Update writer profile
        page.get_by_label("Writer full name").fill("Amruth Vithala")
        page.get_by_label("Writer pen name").fill("A. V. Screenwriter")
        page.get_by_label("Writer intent & bio").fill(
            "High-concept sci-fi thrillers with grounded emotional stakes."
        )
        time.sleep(0.5)
        page.get_by_role("button", name="Save writer profile").click()
        time.sleep(1.0)
        page.screenshot(path=str(ARTIFACTS_DIR / "tour_06_writer_profile.png"))

        print("[5/5] Returning to Projects Vault to verify profile badge ...")
        page.goto("http://localhost:9000/projects")
        page.wait_for_load_state("networkidle")
        time.sleep(1.5)
        page.screenshot(path=str(ARTIFACTS_DIR / "tour_07_vault_with_profile.png"))

        print("Visual browser tour complete! Closing browser.")
        time.sleep(2.0)
        browser.close()


if __name__ == "__main__":
    main()
