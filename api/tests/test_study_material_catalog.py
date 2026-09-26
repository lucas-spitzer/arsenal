from __future__ import annotations

import pytest

from app.mathesys.study_material.catalog import (
    CatalogError,
    asset_path,
    get_template,
    get_theme,
    load_templates,
    load_themes,
    resolve_options,
)
from app.mathesys.study_material.layout import normalize_section_layout
from app.mathesys.study_material.render import RenderComponent, RenderInput, render_document
from app.mathesys.study_material.sanitize import sanitize_fragment

USMC_DISCLAIMER = "Unofficial knowledge for educational use; not endorsed by the USMC or DoD."


def test_catalog_ships_three_templates_and_two_themes() -> None:
    assert set(load_templates()) == {"branded-sheet", "branded-sheet-split", "index-card-cutout"}
    assert set(load_themes()) == {"usmc", "field-manual"}


def test_template_geometry_matches_sketches() -> None:
    sheet = get_template("branded-sheet")
    assert [(s.id, s.box.h) for s in sheet.sections] == [
        ("title", 10),
        ("logo_band", 5),
        ("body", 80),
        ("footer", 5),
    ]
    split = get_template("branded-sheet-split")
    assert [(s.id, s.box.w) for s in split.flexible_sections] == [("body_left", 50), ("body_right", 50)]
    cards = get_template("index-card-cutout")
    assert len(cards.flexible_sections) == 8
    assert all((s.box.w, s.box.h) == (50, 25) for s in cards.flexible_sections)
    assert cards.disclaimer == "per_section"


def test_usmc_theme_has_official_palette_logos_and_disclaimer() -> None:
    theme = get_theme("usmc")
    assert theme.disclaimer == USMC_DISCLAIMER
    assert theme.colors["heading"] == "#940000"
    assert theme.colors["accent_dark"] == "#660000"
    assert {logo.id for logo in theme.light_logos} == {"ega", "marines-wordmark"}
    for logo in theme.logos:
        assert asset_path(logo.file).is_file()


def test_logo_lock_is_the_users_choice() -> None:
    theme = get_theme("usmc")
    sheet = get_template("branded-sheet")
    assert resolve_options(theme, sheet, {})["logo_locked"] is False
    locked = resolve_options(theme, sheet, {"logo_locked": True})
    assert locked == {"logo_locked": True, "logo_id": "ega", "footer_text": ""}
    with pytest.raises(CatalogError, match="light backgrounds"):
        resolve_options(theme, sheet, {"logo_locked": True, "logo_id": "ega-white"})


def test_logo_lock_ignored_without_logo_section_or_logos() -> None:
    assert resolve_options(get_theme("usmc"), get_template("index-card-cutout"), {"logo_locked": True})["logo_locked"] is False
    assert resolve_options(get_theme("field-manual"), get_template("branded-sheet"), {"logo_locked": True})["logo_locked"] is False


def test_footer_text_word_limit() -> None:
    theme = get_theme("usmc")
    sheet = get_template("branded-sheet")
    with pytest.raises(CatalogError, match="20 words"):
        resolve_options(theme, sheet, {"footer_text": " ".join(["word"] * 21)})
    with pytest.raises(CatalogError, match="no footer"):
        resolve_options(theme, get_template("index-card-cutout"), {"footer_text": "hi"})


def test_asset_path_rejects_traversal() -> None:
    with pytest.raises(CatalogError):
        asset_path("../themes/usmc.json")


def _render(template_id: str, options: dict, components: list[RenderComponent], theme_id: str = "usmc") -> str:
    theme = get_theme(theme_id)
    template = get_template(template_id)
    return render_document(
        RenderInput("Land Navigation", template, theme, resolve_options(theme, template, options), components, {}),
    )


def test_footer_always_carries_disclaimer_and_logo_only_when_locked() -> None:
    unlocked = _render("branded-sheet", {"footer_text": "Week 3"}, [])
    assert USMC_DISCLAIMER in unlocked
    assert "Week 3" in unlocked
    assert 'class="sm-logo-panel"' not in unlocked
    locked = _render("branded-sheet", {"logo_locked": True}, [])
    assert 'class="sm-logo-panel"' in locked
    assert "data:image/png;base64," in locked
    assert "@page { size: 8.5in 11in; margin: 0; }" in locked


def test_index_cards_repeat_disclaimer_and_draw_cut_lines() -> None:
    html = _render("index-card-cutout", {}, [])
    assert html.count('class="sm-card-disclaimer"') == 8
    assert 'class="sm-cutlines"' in html


def test_theme_without_disclaimer_renders_none() -> None:
    html = _render("branded-sheet", {}, [], theme_id="field-manual")
    assert 'class="sm-disclaimer"' not in html


def test_components_render_in_layout_order() -> None:
    theme = get_theme("usmc")
    template = get_template("branded-sheet")
    layout = normalize_section_layout({"order": ["t1", "d1"]}, ["d1", "t1"], {"d1"}, section_aspect=1)
    html = render_document(
        RenderInput(
            "Title",
            template,
            theme,
            {},
            [
                RenderComponent("d1", "body", "diagram", svg="<svg></svg>"),
                RenderComponent("t1", "body", "text", html="<p>Hi</p>"),
            ],
            {"body": layout},
        ),
    )
    assert html.index('data-component="t1"') < html.index('data-component="d1"')


def test_sanitize_keeps_structure_and_strips_style_scripts_images() -> None:
    cleaned = sanitize_fragment(
        '<h1>Rules</h1><p style="color:red" onclick="x()">Treat every weapon as loaded.</p>'
        '<ol class="steps rogue"><li>Begin</li></ol><script>alert(1)</script>'
        '<img src="http://evil.example/x.png" /><svg><path d="M0"/></svg><td colspan="x">a</td>'
    )
    assert cleaned.startswith("<h2>Rules</h2>")
    assert "style" not in cleaned and "onclick" not in cleaned
    assert "script" not in cleaned and "img" not in cleaned and "svg" not in cleaned
    assert '<ol class="steps">' in cleaned
    assert "colspan" not in cleaned
