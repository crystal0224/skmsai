#!/usr/bin/env python3
"""Live frontend verification for the deployed SKMS AI Studio."""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable

from playwright.sync_api import sync_playwright

FRONTEND_URL = "https://skmsai.netlify.app"
API_BASE_URL = "https://skmsai-api.onrender.com"
DEFAULT_TIMEOUT = 45


@dataclass
class CheckResult:
    tab: str
    check: str
    status: str
    source: str
    detail: str


def _request_json(
    path: str,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    timeout: int = DEFAULT_TIMEOUT,
    base_url: str = API_BASE_URL,
) -> dict[str, Any]:
    url = path if path.startswith("http") else f"{base_url}{path}"
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")

    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8")
        return json.loads(raw) if raw else {}


def _request_text(
    url: str,
    *,
    timeout: int = DEFAULT_TIMEOUT,
) -> str:
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8")


def _first_section(sections: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not sections:
        return None
    node = sections[0]
    children = node.get("children") or []
    return _first_section(children) or node


def _iter_sections(sections: list[dict[str, Any]]) -> list[dict[str, Any]]:
    flattened: list[dict[str, Any]] = []
    for node in sections:
        flattened.append(node)
        children = node.get("children") or []
        flattened.extend(_iter_sections(children))
    return flattened


def _detail_from_exception(exc: Exception) -> str:
    if isinstance(exc, urllib.error.HTTPError):
        body = exc.read().decode("utf-8", errors="ignore")
        return f"HTTP {exc.code}: {body[:240]}"
    return str(exc)


def _run_check(
    results: list[CheckResult],
    *,
    tab: str,
    check: str,
    source: str,
    fn: Callable[[], str],
) -> None:
    started = time.time()
    print(f"Running {tab} | {check} [{source}]...", flush=True)
    try:
        detail = fn()
        elapsed = time.time() - started
        results.append(
            CheckResult(
                tab=tab,
                check=check,
                status="PASS",
                source=source,
                detail=f"{detail} ({elapsed:.1f}s)",
            )
        )
    except Exception as exc:  # pragma: no cover - diagnostic flow
        elapsed = time.time() - started
        results.append(
            CheckResult(
                tab=tab,
                check=check,
                status="FAIL",
                source=source,
                detail=f"{_detail_from_exception(exc)} ({elapsed:.1f}s)",
            )
        )


def run_api_checks(results: list[CheckResult]) -> dict[str, Any]:
    context: dict[str, Any] = {}

    def frontend_root() -> str:
        html = _request_text(FRONTEND_URL)
        if "SKMS AI Studio" not in html:
            raise AssertionError("frontend HTML does not contain expected title")
        return "frontend root HTML loaded"

    def health() -> str:
        data = _request_json("/api/health")
        if data.get("status") != "ok":
            raise AssertionError(f"unexpected health status: {data}")
        context["health"] = data
        return "health status is ok"

    def editions() -> str:
        data = _request_json("/api/editions")
        editions_data = data.get("editions") or []
        if len(editions_data) != 12:
            raise AssertionError(f"expected 12 editions, got {len(editions_data)}")
        first = editions_data[0]
        context["edition_id"] = first["edition_id"]
        context["edition_total"] = len(editions_data)
        return f"loaded {len(editions_data)} editions; first={first['edition_id']}"

    def toc() -> str:
        edition_id = context["edition_id"]
        data = _request_json(f"/api/toc/{urllib.parse.quote(edition_id)}")
        sections = data.get("sections") or []
        if not sections:
            raise AssertionError(f"no TOC sections returned for {edition_id}")
        context["toc_sections"] = sections
        leaf = _first_section(sections)
        if not leaf:
            raise AssertionError("could not find a TOC node to inspect")
        context["section_line"] = leaf["line"]
        context["section_title"] = leaf["title"]
        return f"loaded TOC for {edition_id}; sample section={leaf['title']}@L{leaf['line']}"

    def section_text() -> str:
        edition_id = context["edition_id"]
        sections = _iter_sections(context.get("toc_sections") or [])
        for node in sections[:12]:
            params = urllib.parse.urlencode(
                {
                    "edition_id": edition_id,
                    "line": str(node["line"]),
                    "title": node["title"],
                }
            )
            data = _request_json(f"/api/section-text?{params}")
            text = (data.get("text") or "").strip()
            if text:
                return f"loaded raw text for {node['title']} ({len(text)} chars)"
        raise AssertionError("section text response was empty for sampled TOC nodes")

    def search() -> str:
        payload = {
            "query": "SUPEX 추구",
            "mode": "hybrid",
            "top_k": 5,
            "include_evidence_check": True,
            "include_comparison": False,
        }
        data = _request_json("/api/v2/search", method="POST", payload=payload)
        hits = data.get("hits") or []
        if not hits:
            raise AssertionError("search returned no hits for SUPEX 추구")
        first = hits[0]
        return (
            f"search returned {len(hits)} hits; "
            f"top={first.get('edition_id')} / {first.get('quote_type')}"
        )

    def dashboard_metrics() -> str:
        data = _request_json("/api/dashboard/metrics")
        if "total_requests" not in data:
            raise AssertionError("dashboard metrics missing total_requests")
        return (
            f"total_requests={data['total_requests']}, "
            f"success_rate={1 - float(data.get('error_rate', 0)):.2%}"
        )

    def dashboard_stats() -> str:
        data = _request_json("/api/dashboard/stats", timeout=10)
        endpoint_stats = data.get("endpoints") or []
        if not endpoint_stats:
            raise AssertionError("dashboard stats returned no endpoint rows")
        return f"stats returned {len(endpoint_stats)} endpoint rows"

    def quality_summary() -> str:
        data = _request_json("/api/quality/summary", timeout=10)
        if "summary" not in data and "totals" not in data:
            raise AssertionError("quality summary missing expected keys")
        return "quality summary responded"

    def quality_coverage() -> str:
        data = _request_json("/api/quality/coverage", timeout=10)
        if "coverage" not in data and "by_edition" not in data:
            raise AssertionError("quality coverage missing expected keys")
        return "quality coverage responded"

    def content_types() -> str:
        data = _request_json("/api/content/types")
        types_data = data.get("types") or []
        if len(types_data) < 1:
            raise AssertionError("content types endpoint returned no types")
        context["content_types"] = [t["type"] for t in types_data]
        return f"content types returned {len(types_data)} types: {', '.join(context['content_types'])}"

    def content_plan() -> str:
        payload = {
            "content_type": "lecture",
            "topic": "SUPEX 추구의 실천 방안",
            "options": {
                "duration_min": 20,
                "language": "ko",
                "target_audience": "manager",
            },
        }
        data = _request_json("/api/content/plan", method="POST", payload=payload)
        plan = data.get("plan") or {}
        items = (
            plan.get("sections")
            or plan.get("slides")
            or plan.get("cards")
            or plan.get("items")
            or []
        )
        if not plan.get("title"):
            raise AssertionError("content plan missing title")
        return f"plan created: {plan['title']} ({len(items)} items)"

    checks = [
        ("HOME", "frontend root", "http", frontend_root),
        ("DASHBOARD", "health API", "api", health),
        ("EDITIONS", "editions API", "api", editions),
        ("EDITIONS", "TOC API", "api", toc),
        ("EDITIONS", "section text API", "api", section_text),
        ("SEARCH", "search API", "api", search),
        ("DASHBOARD", "dashboard metrics API", "api", dashboard_metrics),
        ("DASHBOARD", "dashboard stats API", "api", dashboard_stats),
        ("DASHBOARD", "quality summary API", "api", quality_summary),
        ("DASHBOARD", "quality coverage API", "api", quality_coverage),
        ("START STUDIO", "content types API", "api", content_types),
        ("START STUDIO", "content plan API", "api", content_plan),
    ]

    for tab, check, source, fn in checks:
        _run_check(results, tab=tab, check=check, source=source, fn=fn)

    return context


def run_ui_checks(results: list[CheckResult]) -> None:
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        context = browser.new_context(viewport={"width": 1440, "height": 1200})
        context.add_init_script(
            "window.localStorage.setItem('skms_tour_completed', 'true');"
        )
        page = context.new_page()
        page_errors: list[str] = []

        def track_page_error(exc: Any) -> None:
            page_errors.append(str(exc))

        page.on("pageerror", track_page_error)

        def dismiss_tour_if_present() -> None:
            skip_btn = page.locator("#tour-skip")
            if skip_btn.count() and skip_btn.is_visible():
                skip_btn.click()
                page.wait_for_timeout(300)

        def goto_home() -> None:
            page.goto(FRONTEND_URL, wait_until="domcontentloaded", timeout=45_000)
            page.wait_for_timeout(1500)
            dismiss_tour_if_present()

        def home_nav() -> str:
            goto_home()
            title = page.title()
            if title != "SKMS AI Studio":
                raise AssertionError(f"unexpected page title: {title}")
            nav = page.locator(".nav-links a")
            if nav.count() < 6:
                raise AssertionError(f"expected 6 nav links, got {nav.count()}")
            return "title and 6 nav links rendered"

        def showcase_nav() -> str:
            goto_home()
            page.locator("[data-nav='showcase']").click()
            page.wait_for_timeout(500)
            showcase = page.locator("#showcase-section")
            if "hidden" in (showcase.get_attribute("class") or ""):
                raise AssertionError("showcase section is still hidden after nav click")
            return "showcase tab reveals the gallery section"

        def editions_overlay() -> str:
            goto_home()
            page.locator("[data-nav='editions']").click()
            page.locator("#editions-overlay.active").wait_for(timeout=10_000)
            items = page.locator("#edition-list .edition-item")
            items.first.wait_for(timeout=20_000)
            count = items.count()
            if count < 1:
                raise AssertionError("edition list did not render")
            return f"overlay opened and rendered {count} editions"

        def editions_toc() -> str:
            goto_home()
            page.locator("[data-nav='editions']").click()
            page.locator("#edition-list .edition-item").first.wait_for(timeout=20_000)
            page.locator("#edition-list .edition-item").first.click()
            page.locator("#toc-tree").wait_for(timeout=10_000)
            page.wait_for_timeout(2500)
            nodes = page.locator("#toc-tree .toc-node")
            if nodes.count() < 1:
                error_text = page.locator("#toc-tree .result-error").text_content() or ""
                raise AssertionError(f"TOC nodes missing: {error_text}")
            page.locator("#toc-tree .toc-title").first.click()
            page.locator("#section-text-panel").wait_for(state="visible", timeout=10_000)
            body_text = (page.locator("#section-text-body").text_content() or "").strip()
            if not body_text or "로드 실패" in body_text:
                raise AssertionError(f"section text panel did not load cleanly: {body_text[:120]}")
            return "edition selection loaded TOC and raw section text"

        def search_flow() -> str:
            goto_home()
            page.locator("[data-nav='search']").click()
            page.locator("#search-overlay.active").wait_for(timeout=10_000)
            page.locator("#search-query").fill("SUPEX 추구")
            page.locator("#search-submit-btn").click()
            page.locator("#search-submit-btn").wait_for(state="attached", timeout=15_000)
            page.wait_for_function(
                """() => {
                    const btn = document.querySelector('#search-submit-btn');
                    const results = document.querySelector('#search-results');
                    if (!btn || !results) return false;
                    const html = results.innerHTML;
                    return !btn.disabled && (
                        html.includes('search-result-item') ||
                        html.includes('search-result-count') ||
                        html.includes('result-error') ||
                        html.includes('empty-state')
                    );
                }""",
                timeout=20_000,
            )
            html = page.locator("#search-results").inner_html()
            if "result-error" in html:
                raise AssertionError("search UI rendered a backend error")
            if "search-result-item" not in html and "search-result-count" not in html:
                raise AssertionError("search UI did not render search results")
            return "search overlay returned visible result items"

        def dashboard_flow() -> str:
            goto_home()
            page.locator("[data-nav='dashboard']").click()
            page.locator("#dashboard-overlay.active").wait_for(timeout=10_000)
            page.wait_for_function(
                """() => {
                    const metric = document.querySelector('#metric-total-requests');
                    const status = document.querySelector('#status-search');
                    return Boolean(metric && status &&
                        metric.textContent.trim() !== '--' &&
                        status.textContent.trim() !== '--');
                }""",
                timeout=20_000,
            )
            metric_value = (page.locator("#metric-total-requests").text_content() or "").strip()
            status_value = (page.locator("#status-search").text_content() or "").strip()
            return f"dashboard loaded status={status_value}, total_requests={metric_value}"

        def start_studio_nav() -> str:
            goto_home()
            page.locator("#nav-studio").click()
            page.wait_for_timeout(1000)
            section = page.locator("#content-studio-section")
            box = section.bounding_box()
            if not box:
                raise AssertionError("content studio section bounding box unavailable")
            if box["y"] > 1100:
                raise AssertionError(f"content studio section did not scroll into view: y={box['y']}")
            return f"start studio nav scrolled to section at y={box['y']:.0f}"

        def studio_plan_flow() -> str:
            goto_home()
            page.locator("#content-studio-section").scroll_into_view_if_needed()
            page.locator(".card-btn[data-type='lecture']").click()
            page.locator("#studio-modal-overlay.active").wait_for(timeout=10_000)
            page.locator("#studio-topic").fill("SUPEX 추구의 실천 방안")
            page.locator("#studio-plan-btn").click()
            page.locator("#studio-step-plan").wait_for(timeout=15_000)
            page.wait_for_function(
                """() => {
                    const container = document.querySelector('#studio-plan-content');
                    if (!container) return false;
                    const html = container.innerHTML;
                    return html.includes('plan-item-card') || html.includes('result-error');
                }""",
                timeout=40_000,
            )
            html = page.locator("#studio-plan-content").inner_html()
            if "result-error" in html:
                raise AssertionError("studio plan preview returned an error")
            item_count = page.locator("#plan-items-list .plan-item-card").count()
            if item_count < 1:
                raise AssertionError("studio plan rendered no editable items")
            return f"lecture plan preview rendered {item_count} editable items"

        def podcast_modal() -> str:
            goto_home()
            page.locator("#content-studio-section").scroll_into_view_if_needed()
            before_error_count = len(page_errors)
            page.locator(".podcast-open-btn").click()
            page.locator("#podcast-modal-overlay.active").wait_for(timeout=10_000)
            if len(page_errors) > before_error_count:
                raise AssertionError(page_errors[-1])
            topics = page.locator("#podcast-topics")
            if not topics.is_visible():
                raise AssertionError("podcast topic input is not visible")
            return "podcast modal opened without frontend exceptions"

        checks = [
            ("HOME", "landing render", "ui", home_nav),
            ("SHOWCASE", "nav to showcase", "ui", showcase_nav),
            ("EDITIONS", "overlay opens", "ui", editions_overlay),
            ("EDITIONS", "TOC and section text", "ui", editions_toc),
            ("SEARCH", "search overlay query", "ui", search_flow),
            ("DASHBOARD", "dashboard overlay loads", "ui", dashboard_flow),
            ("START STUDIO", "nav scroll to studio", "ui", start_studio_nav),
            ("START STUDIO", "lecture plan preview", "ui", studio_plan_flow),
            ("START STUDIO", "podcast modal open", "ui", podcast_modal),
        ]

        for tab, check, source, fn in checks:
            _run_check(results, tab=tab, check=check, source=source, fn=fn)

        context.close()
        browser.close()


def print_report(results: list[CheckResult]) -> int:
    pass_count = sum(1 for r in results if r.status == "PASS")
    fail_count = sum(1 for r in results if r.status == "FAIL")

    print(f"Live frontend verification: {pass_count} PASS / {fail_count} FAIL")
    for item in results:
        print(
            f"[{item.status}] {item.tab} | {item.check} | {item.source} | {item.detail}"
        )

    return 1 if fail_count else 0


def main() -> int:
    results: list[CheckResult] = []
    run_api_checks(results)
    run_ui_checks(results)
    return print_report(results)


if __name__ == "__main__":
    sys.exit(main())
