"""E2E tests for Content Studio UI interactions."""

import re

from playwright.sync_api import expect


def test_studio_modal_opens(page, base_url):
    """Click a content type card button to open modal with options form."""
    page.goto(base_url)

    # Scroll to content studio section
    page.locator("#content-studio-section").scroll_into_view_if_needed()

    # Click the first card button (lecture / PPTX)
    card_btn = page.locator(".card-btn[data-type='lecture']")
    expect(card_btn).to_be_visible()
    card_btn.click()

    # Modal should be active
    modal_overlay = page.locator("#studio-modal-overlay")
    expect(modal_overlay).to_have_class(re.compile(r"active"))

    # Modal title should mention the content type
    modal_title = page.locator("#studio-modal-title")
    expect(modal_title).to_contain_text("프레젠테이션")

    # Topic textarea should be visible
    topic_input = page.locator("#studio-topic")
    expect(topic_input).to_be_visible()

    # Type-specific options for lecture should be visible
    lecture_opts = page.locator(".type-options[data-for='lecture']")
    expect(lecture_opts).not_to_have_class(re.compile(r"hidden"))


def test_studio_modal_closes(page, base_url):
    """Close button closes the studio modal."""
    page.goto(base_url)

    page.locator("#content-studio-section").scroll_into_view_if_needed()
    page.locator(".card-btn[data-type='lecture']").click()

    modal_overlay = page.locator("#studio-modal-overlay")
    expect(modal_overlay).to_have_class(re.compile(r"active"))

    page.locator("#close-studio-modal").click()
    expect(modal_overlay).not_to_have_class(re.compile(r"active"))


def test_studio_different_types(page, base_url):
    """Each content type card opens modal with correct type-specific options."""
    page.goto(base_url)
    page.locator("#content-studio-section").scroll_into_view_if_needed()

    type_checks = {
        "card_news": ("카드뉴스", "card_news"),
        "workshop": ("워크숍", "workshop"),
        "quiz": ("퀴즈", "quiz"),
    }

    for content_type, (expected_title_part, data_for) in type_checks.items():
        card_btn = page.locator(f".card-btn[data-type='{content_type}']")
        card_btn.scroll_into_view_if_needed()
        card_btn.click()

        modal_overlay = page.locator("#studio-modal-overlay")
        expect(modal_overlay).to_have_class(re.compile(r"active"))

        modal_title = page.locator("#studio-modal-title")
        expect(modal_title).to_contain_text(expected_title_part)

        type_opts = page.locator(f".type-options[data-for='{data_for}']")
        expect(type_opts).not_to_have_class(re.compile(r"hidden"))

        page.locator("#close-studio-modal").click()
        expect(modal_overlay).not_to_have_class(re.compile(r"active"))


def test_studio_plan_preview(page, base_url):
    """Fill topic form and click plan preview button."""
    page.goto(base_url)

    page.locator("#content-studio-section").scroll_into_view_if_needed()
    page.locator(".card-btn[data-type='lecture']").click()

    modal_overlay = page.locator("#studio-modal-overlay")
    expect(modal_overlay).to_have_class(re.compile(r"active"))

    # Fill in topic
    topic_input = page.locator("#studio-topic")
    topic_input.fill("SUPEX 추구의 현대적 의미")

    # Click plan preview button
    plan_btn = page.locator("#studio-plan-btn")
    expect(plan_btn).to_be_visible()
    plan_btn.click()

    # Plan step should become visible
    plan_step = page.locator("#studio-step-plan")
    expect(plan_step).not_to_have_class(re.compile(r"hidden"), timeout=5000)

    # Plan content area should show (loading or result)
    plan_content = page.locator("#studio-plan-content")
    expect(plan_content).to_be_visible(timeout=5000)
