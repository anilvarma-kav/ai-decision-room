"""Exercise the actual UI and capture unmodified browser screenshots.

Run the app first, then: uv run python scripts/check_ui.py --output docs/screenshots
"""

import argparse
import json
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

parser = argparse.ArgumentParser()
parser.add_argument("--base-url", default="http://127.0.0.1:7860")
parser.add_argument("--output", default="test-results/screenshots")
args = parser.parse_args()
output = Path(args.output)
output.mkdir(parents=True, exist_ok=True)

with sync_playwright() as p:
    browser = p.chromium.launch()
    context = browser.new_context(viewport={"width": 1440, "height": 1040}, device_scale_factor=1)
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(args.base_url, wait_until="networkidle")
    expect(page.locator("#question")).to_have_value(
        "Should we build or buy AI search for our SaaS product?"
    )
    assert page.locator("#question").get_attribute("readonly") is not None
    page.screenshot(path=str(output / "01-workspace.png"), full_page=True)

    page.get_by_role("button", name="Open the decision room").click()
    expect(page.locator("#results")).to_be_visible(timeout=15000)
    expect(page.locator("#result-provenance")).to_contain_text("CURATED DEMO")
    expect(page.locator("#result-title")).to_have_text("Buy the capability. Own the experience.")
    expect(page.locator(".recommendation")).to_contain_text("provider-neutral")
    page.screenshot(path=str(output / "02-decision-memo.png"), full_page=True)

    page.get_by_role("tab", name="The deliberation").click()
    expect(page.locator(".opinion-card")).to_have_count(3)
    page.screenshot(path=str(output / "03-deliberation.png"), full_page=True)
    page.get_by_role("tab", name="Activity & usage").click()
    page.locator(".tool-item").first.locator("summary").click()
    expect(page.locator(".tool-data").first).to_contain_text('"total": 25600')
    page.screenshot(path=str(output / "04-tool-activity.png"), full_page=True)

    with page.expect_download() as download:
        page.get_by_role("button", name="Download full JSON audit record").click()
    saved = json.loads(Path(download.value.path()).read_text())
    assert saved["mode"] == "demo" and saved["calls"] == []
    assert len(saved["opinions"]) == 3
    with page.expect_download() as download:
        page.get_by_role("button", name="↓ Memo", exact=True).click()
    assert "Unresolved disagreements" in Path(download.value.path()).read_text()

    page.get_by_role("tab", name="Decision overview").click()
    page.set_viewport_size({"width": 390, "height": 844})
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), (
        "Mobile overflow"
    )
    page.screenshot(path=str(output / "05-mobile.png"), full_page=True)
    page.set_viewport_size({"width": 1440, "height": 1040})
    page.get_by_role("button", name="+ New decision", exact=True).click()
    page.get_by_role("button", name="Cloud vs. local").click()
    page.get_by_role("button", name="Open the decision room").click()
    expect(page.locator("#result-title")).to_have_text(
        "Start managed. Measure the workload.", timeout=15000
    )
    page.get_by_role("button", name="+ New decision", exact=True).click()
    page.get_by_role("button", name="Automate support").click()
    page.get_by_role("button", name="Open the decision room").click()
    expect(page.locator("#result-title")).to_have_text(
        "Assist first. Automate with evidence.", timeout=15000
    )
    page.reload(wait_until="networkidle")
    page.locator(".history-item").first.click()
    expect(page.locator("#result-title")).to_have_text("Assist first. Automate with evidence.")

    page.get_by_role("button", name="+ New decision", exact=True).click()
    page.get_by_role("button", name="Open the decision room").click()
    page.get_by_role("button", name="Stop run").click()
    expect(page.locator("#notice")).to_contain_text("Run stopped")
    expect(page.locator("#run-button")).to_be_enabled()
    page.get_by_role("button", name="How it works").click()
    expect(page.get_by_role("dialog")).to_be_visible()
    page.get_by_role("button", name="Close dialog").click()
    assert not errors, errors
    browser.close()
print(
    "UI verified: three scenarios, memo, critique, tool results, both exports, history, stop, dialog, mobile layout."
)
print(f"Screenshots: {output}")
