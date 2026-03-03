"""E2E tests for search functionality."""

import re

from playwright.sync_api import expect


def test_search_flow(page, base_url):
    """Open search, type a query, submit, and verify the UI responds."""
    page.goto(base_url)

    page.locator("[data-nav='search']").click()

    overlay = page.locator("#search-overlay")
    expect(overlay).to_have_class(re.compile(r"active"))

    search_input = page.locator("#search-query")
    search_input.fill("인간중심")

    page.locator("#search-submit-btn").click()

    # After clicking submit, the results area should show loading, then either
    # real results or an error. Wait for the submit button to re-enable
    # (indicates the request cycle completed).
    submit_btn = page.locator("#search-submit-btn")
    expect(submit_btn).to_be_enabled(timeout=15_000)

    results = page.locator("#search-results")
    results.wait_for(state="visible", timeout=5_000)

    # The results area should contain something other than the initial placeholder.
    # It could be search-result-item (success), result-error (backend error),
    # search-result-count (success header), or empty-state with "결과가 없습니다".
    inner_html = results.inner_html()
    assert (
        "search-result-item" in inner_html
        or "result-error" in inner_html
        or "search-result-count" in inner_html
        or "결과가 없습니다" in inner_html
        or "연결할 수 없습니다" in inner_html
        or "검색 실패" in inner_html
    ), f"Unexpected search results content: {inner_html[:200]}"


def test_search_edition_filter(page, base_url):
    """Edition filter dropdown is present and can be changed."""
    page.goto(base_url)

    page.locator("[data-nav='search']").click()

    overlay = page.locator("#search-overlay")
    expect(overlay).to_have_class(re.compile(r"active"))

    edition_filter = page.locator("#search-edition-filter")
    expect(edition_filter).to_be_visible()

    # Default value should be empty (all editions)
    expect(edition_filter).to_have_value("")

    # The filter should have at least the default option
    options = edition_filter.locator("option")
    assert options.count() >= 1
