"""E2E tests for page load and navigation."""

import re

from playwright.sync_api import expect


def test_page_loads(page, base_url):
    """Page loads with title and nav bar items."""
    page.goto(base_url)

    expect(page).to_have_title("SKMS AI Studio")

    nav = page.locator(".nav-links")
    expect(nav).to_be_visible()

    expect(nav.locator("[data-nav='home']")).to_be_visible()
    expect(nav.locator("[data-nav='editions']")).to_be_visible()
    expect(nav.locator("[data-nav='search']")).to_be_visible()
    expect(nav.locator("[data-nav='about']")).to_be_visible()
    expect(nav.locator("[data-nav='dashboard']")).to_be_visible()


def test_nav_search_overlay(page, base_url):
    """Click SEARCH nav link opens overlay; close button closes it."""
    page.goto(base_url)

    page.locator("[data-nav='search']").click()

    overlay = page.locator("#search-overlay")
    expect(overlay).to_have_class(re.compile(r"active"))

    page.locator("#close-search").click()
    expect(overlay).not_to_have_class(re.compile(r"active"))


def test_nav_search_overlay_escape(page, base_url):
    """Pressing Escape closes the search overlay."""
    page.goto(base_url)

    page.locator("[data-nav='search']").click()

    overlay = page.locator("#search-overlay")
    expect(overlay).to_have_class(re.compile(r"active"))

    page.keyboard.press("Escape")
    expect(overlay).not_to_have_class(re.compile(r"active"))


def test_dashboard_nav(page, base_url):
    """Click DASHBOARD nav link opens dashboard overlay."""
    page.goto(base_url)

    page.locator("[data-nav='dashboard']").click()

    overlay = page.locator("#dashboard-overlay")
    expect(overlay).to_have_class(re.compile(r"active"))
