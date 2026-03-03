"""E2E tests for dashboard overlay."""

import re

from playwright.sync_api import expect


def test_dashboard_loads(page, base_url):
    """Open dashboard and verify service status cards are visible."""
    page.goto(base_url)

    page.locator("[data-nav='dashboard']").click()

    overlay = page.locator("#dashboard-overlay")
    expect(overlay).to_have_class(re.compile(r"active"))

    # Service status grid should be visible
    status_grid = page.locator("#dashboard-status-grid")
    expect(status_grid).to_be_visible()

    # Should have 4 status cards (Search, Generation, TOC, Content Studio)
    status_cards = status_grid.locator(".status-card")
    expect(status_cards).to_have_count(4)

    # Labels should be visible
    expect(status_grid.locator("text=Search")).to_be_visible()
    expect(status_grid.locator("text=Generation")).to_be_visible()
    expect(status_grid.locator("text=TOC")).to_be_visible()
    expect(status_grid.locator("text=Content Studio")).to_be_visible()


def test_dashboard_metrics(page, base_url):
    """Metrics section shows metric cards with values."""
    page.goto(base_url)

    page.locator("[data-nav='dashboard']").click()

    overlay = page.locator("#dashboard-overlay")
    expect(overlay).to_have_class(re.compile(r"active"))

    # Metrics grid should be visible
    metrics_grid = page.locator("#dashboard-metrics-grid")
    expect(metrics_grid).to_be_visible()

    # Should have 4 metric cards
    metric_cards = metrics_grid.locator(".metric-card")
    expect(metric_cards).to_have_count(4)

    # Metric labels should be present
    expect(metrics_grid.locator("text=Total Requests")).to_be_visible()
    expect(metrics_grid.locator("text=Success Rate")).to_be_visible()
    expect(metrics_grid.locator("text=p95 Latency")).to_be_visible()
    expect(metrics_grid.locator("text=Uptime")).to_be_visible()


def test_dashboard_close(page, base_url):
    """Dashboard closes via close button."""
    page.goto(base_url)

    page.locator("[data-nav='dashboard']").click()

    overlay = page.locator("#dashboard-overlay")
    expect(overlay).to_have_class(re.compile(r"active"))

    page.locator("#close-dashboard").click()
    expect(overlay).not_to_have_class(re.compile(r"active"))
