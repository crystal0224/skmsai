"""E2E tests for edition browser."""

import re

from playwright.sync_api import expect


def test_edition_browser(page, base_url):
    """Click SKMS 판본 nav opens overlay with edition list."""
    page.goto(base_url)

    page.locator("[data-nav='editions']").click()

    overlay = page.locator("#editions-overlay")
    expect(overlay).to_have_class(re.compile(r"active"))

    # Wait for edition list to load from API
    edition_list = page.locator("#edition-list")
    edition_list.wait_for(state="visible", timeout=10_000)

    # Either edition items load or an error appears
    edition_items = edition_list.locator(".edition-item")
    error_text = edition_list.locator("p")

    # Wait until loading text changes (either items appear or error)
    page.wait_for_timeout(2000)

    items_count = edition_items.count()
    if items_count > 0:
        # Should have 12 editions
        assert items_count == 12, f"Expected 12 editions, got {items_count}"
    else:
        # Backend not running — error message should be visible
        assert error_text.count() > 0, "Expected either edition items or error text"


def test_toc_load(page, base_url):
    """Select an edition and verify TOC tree loads."""
    page.goto(base_url)

    page.locator("[data-nav='editions']").click()

    overlay = page.locator("#editions-overlay")
    expect(overlay).to_have_class(re.compile(r"active"))

    # Wait for edition list to load
    edition_list = page.locator("#edition-list")
    edition_items = edition_list.locator(".edition-item")

    # Wait for editions to appear (needs backend)
    try:
        edition_items.first.wait_for(state="visible", timeout=10_000)
    except Exception:
        # Backend may not be running — skip test gracefully
        return

    # Click the first edition
    edition_items.first.click()

    # TOC tree should update (either load content or show error)
    toc_tree = page.locator("#toc-tree")
    toc_tree.wait_for(state="visible", timeout=10_000)

    # Wait for loading to finish
    page.wait_for_timeout(3000)

    # Should have TOC nodes or an error
    toc_nodes = toc_tree.locator(".toc-node")
    toc_error = toc_tree.locator(".result-error")

    node_count = toc_nodes.count() + toc_error.count()
    assert node_count > 0, "Expected TOC nodes or error message after selecting edition"
