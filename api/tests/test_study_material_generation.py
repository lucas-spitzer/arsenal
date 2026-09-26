from __future__ import annotations

from typing import Any

import pytest

from app.mathesys.study_material.catalog import get_template, get_theme
from app.mathesys.study_material.diagram import DiagramError, parse_diagram_spec, render_diagram_svg
from app.mathesys.study_material.generation import (
    LayoutComponent,
    auto_aspect_ratio,
    generate_diagram_component,
    generate_text_component,
    plan_layout,
    text_word_budget,
)
from app.mathesys.study_material.layout import normalize_section_layout
from app.mathesys.study_material.prompts import ComponentPromptContext, SiblingSummary
from app.services.llm.base import LLMCompletionResult
from app.services.study_materials import StudyMaterialRuleError, ensure_editable, validate_placement


class ScriptedCompleter:
    def __init__(self, content: dict[str, Any]) -> None:
        self.content = content
        self.prompts: list[str] = []

    def complete_json(self, *, system_prompt: str, user_prompt: str, model: str | None = None) -> LLMCompletionResult:
        del system_prompt, model
        self.prompts.append(user_prompt)
        return LLMCompletionResult(
            content=self.content,
            model="test-model",
            provider="openai",
            token_usage={"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
        )


def _ctx(**overrides: Any) -> ComponentPromptContext:
    template = get_template("branded-sheet")
    values: dict[str, Any] = {
        "title": "Land Navigation",
        "theme": get_theme("usmc"),
        "template": template,
        "section": template.section("body"),
        "instructions": "Explain terrain association.",
    }
    values.update(overrides)
    return ComponentPromptContext(**values)


def test_diagram_parse_drops_dangling_edges_and_extra_emphasis() -> None:
    spec = parse_diagram_spec(
        {
            "layout": "spiral",
            "nodes": [
                {"id": "a", "label": "Plan", "emphasis": True},
                {"id": "b", "label": "Move", "emphasis": True},
                {"id": "c", "label": ""},
            ],
            "connections": [{"from": "a", "to": "b"}, {"from": "a", "to": "zzz"}, {"from": "b", "to": "b"}],
        },
    )
    assert spec.layout == "flow"
    assert [node.id for node in spec.nodes] == ["a", "b"]
    assert [node.emphasis for node in spec.nodes] == [True, False]
    assert [(edge.source, edge.target) for edge in spec.edges] == [("a", "b")]


def test_diagram_needs_two_nodes() -> None:
    with pytest.raises(DiagramError):
        parse_diagram_spec({"nodes": [{"id": "a", "label": "Only"}]})


@pytest.mark.parametrize("layout", ["flow", "hierarchy", "cycle"])
def test_diagram_renders_every_layout_with_theme_colors(layout: str) -> None:
    spec = parse_diagram_spec(
        {
            "layout": layout,
            "nodes": [{"id": str(i), "label": f"Step {i}", "emphasis": i == 0} for i in range(4)],
            "connections": [{"from": str(i), "to": str((i + 1) % 4)} for i in range(4)],
        },
    )
    rendered = render_diagram_svg(spec, get_theme("usmc").diagram)
    assert rendered.svg.startswith("<svg")
    assert rendered.svg.count("<rect") >= 4
    assert "#940000" in rendered.svg
    assert rendered.width > 0 and rendered.height > 0


def test_generate_diagram_component_returns_svg_and_spec() -> None:
    completer = ScriptedCompleter(
        {
            "caption": "Terrain features",
            "layout": "hierarchy",
            "nodes": [{"id": "t", "label": "Terrain"}, {"id": "h", "label": "Hill"}, {"id": "v", "label": "Valley"}],
            "connections": [{"from": "t", "to": "h"}, {"from": "t", "to": "v"}],
        },
    )
    generated = generate_diagram_component(_ctx(), completer)
    assert generated.output["svg"].startswith("<svg")
    assert generated.output["caption"] == "Terrain features"
    assert len(generated.output["spec"]["nodes"]) == 3
    assert "High-contrast technical diagram" in completer.prompts[0]


def test_generate_text_component_sanitizes_and_counts_words() -> None:
    completer = ScriptedCompleter({"html": "<h2>Terrain</h2><p style='x'>Read the ground first.</p>", "summary": "Terrain basics"})
    ctx = _ctx(
        word_budget=90,
        siblings=[SiblingSummary("d1", "diagram", "Terrain features diagram")],
    )
    generated = generate_text_component(ctx, completer)
    assert generated.output["html"] == "<h2>Terrain</h2><p>Read the ground first.</p>"
    assert generated.output["word_count"] == 5
    prompt = completer.prompts[0]
    assert "about 90 words" in prompt
    assert "Terrain features diagram" in prompt


def test_word_budget_shrinks_when_visuals_share_the_section() -> None:
    template = get_template("branded-sheet")
    body = template.section("body")
    alone = text_word_budget(template, body, visual_count=0, text_count=1)
    shared = text_word_budget(template, body, visual_count=1, text_count=1)
    assert alone > shared > 0


def test_auto_aspect_ratio_follows_section_shape() -> None:
    template = get_template("branded-sheet")
    assert auto_aspect_ratio(template, template.section("body"), sibling_count=1) in {"16:9", "3:2", "4:3"}
    cards = get_template("index-card-cutout")
    assert auto_aspect_ratio(cards, cards.section("card_1"), sibling_count=0) in {"3:2", "4:3", "16:9"}


def test_layout_normalization_keeps_components_in_their_section() -> None:
    layout = normalize_section_layout(
        {"arrangement": "grid", "order": ["x-from-elsewhere", "t1"], "sizes": {"d1": 500, "d2": 90}, "emphasis": "nope"},
        ["d1", "d2", "t1"],
        {"d1", "d2"},
        section_aspect=1.0,
    )
    assert sorted(layout.order) == ["d1", "d2", "t1"]
    assert layout.order[0] == "t1"
    assert layout.emphasis is None
    assert layout.arrangement == "grid"


def test_layout_caps_visual_share_when_text_is_present() -> None:
    layout = normalize_section_layout(
        {"arrangement": "stack", "sizes": {"d1": 80, "d2": 80}},
        ["d1", "d2", "t1"],
        {"d1", "d2"},
        section_aspect=1.0,
    )
    assert layout.sizes["d1"] + layout.sizes["d2"] <= 70


def test_plan_layout_ignores_model_sections_and_ids_outside_the_template() -> None:
    template = get_template("branded-sheet-split")
    completer = ScriptedCompleter(
        {
            "sections": [
                {"section_id": "body_left", "arrangement": "stack", "order": ["t1", "d9", "d1"], "sizes": {"d1": 40}},
                {"section_id": "invented", "order": ["t2"]},
            ],
        },
    )
    plan = plan_layout(
        title="Offense vs Defense",
        theme=get_theme("usmc"),
        template=template,
        components_by_section={
            "body_left": [LayoutComponent("d1", "diagram", "x", aspect=1.5), LayoutComponent("t1", "text", "y", words=80)],
            "body_right": [LayoutComponent("t2", "text", "z", words=60)],
        },
        section_notes={},
        completer=completer,
    )
    assert set(plan.sections) == {"body_left", "body_right"}
    assert plan.sections["body_left"].order == ["t1", "d1"]
    assert plan.sections["body_right"].order == ["t2"]


def test_placement_rules() -> None:
    template = get_template("branded-sheet")
    with pytest.raises(StudyMaterialRuleError, match="locked"):
        validate_placement(template, section_id="title", component_type="text", section_component_count=0)
    with pytest.raises(StudyMaterialRuleError, match="at most 6"):
        validate_placement(template, section_id="body", component_type="text", section_component_count=6)
    validate_placement(template, section_id="body", component_type="image", section_component_count=0)


def test_finalized_material_is_not_editable() -> None:
    with pytest.raises(StudyMaterialRuleError, match="finalized"):
        ensure_editable({"status": "finalized"})
    with pytest.raises(StudyMaterialRuleError, match="current run"):
        ensure_editable({"status": "generating"})
    ensure_editable({"status": "draft"})
