"""Render a Study Material page to a self-describing HTML document.

One renderer serves the draft preview and the final PDF. Template geometry is
absolute (inches and percent of the safe area) so print output matches the
preview; the theme supplies every color and font.
"""

from __future__ import annotations

from dataclasses import dataclass
from html import escape

from app.mathesys.study_material.catalog import Template, TemplateSection, Theme, asset_data_uri
from app.mathesys.study_material.layout import SectionLayout, default_section_layout

VISUAL_TYPES = frozenset({"diagram", "image"})
GAP_IN = {"tight": 0.06, "normal": 0.12, "loose": 0.2}
CARD_PADDING_IN = 0.16
CARD_DISCLAIMER_IN = 0.14


@dataclass(frozen=True)
class RenderComponent:
    id: str
    section_id: str
    component_type: str
    html: str | None = None
    svg: str | None = None
    image_src: str | None = None
    alt: str = ""
    caption: str = ""

    @property
    def is_visual(self) -> bool:
        return self.component_type in VISUAL_TYPES


@dataclass(frozen=True)
class RenderInput:
    title: str
    template: Template
    theme: Theme
    options: dict
    components: list[RenderComponent]
    layout: dict[str, SectionLayout]


def _css(template: Template, theme: Theme) -> str:
    colors = theme.colors
    heading = theme.fonts.get("heading", {})
    body = theme.fonts.get("body", {})
    import_url = heading.get("import_url")
    font_import = f"@import url('{import_url}');\n" if import_url else ""
    margin = template.margin_in
    return f"""{font_import}
@page {{ size: {template.width_in:g}in {template.height_in:g}in; margin: 0; }}
:root {{
  --sm-ink: {colors.get('ink', '#000')};
  --sm-heading: {colors.get('heading', '#000')};
  --sm-title: {colors.get('title', colors.get('heading', '#000'))};
  --sm-accent: {colors.get('accent', '#000')};
  --sm-secondary: {colors.get('secondary', '#555')};
  --sm-muted: {colors.get('muted', '#555')};
  --sm-rule: {colors.get('rule', '#999')};
  --sm-border: {colors.get('border', '#aaa')};
  --sm-paper: {colors.get('paper', '#fff')};
  --sm-panel: {colors.get('panel', '#f7f7f5')};
  --sm-font-heading: {heading.get('stack', 'Arial, sans-serif')};
  --sm-font-body: {body.get('stack', 'Arial, sans-serif')};
  --sm-heading-weight: {heading.get('weight', 700)};
  --sm-heading-transform: {heading.get('transform', 'none')};
  --sm-heading-tracking: {heading.get('letter_spacing', 'normal')};
  --sm-body-pt: {template.body_pt:g}pt;
  --sm-title-pt: {template.title_pt:g}pt;
}}
* {{ box-sizing: border-box; }}
html, body {{ margin: 0; padding: 0; background: #fff; }}
body {{
  font-family: var(--sm-font-body); color: var(--sm-ink);
  -webkit-print-color-adjust: exact; print-color-adjust: exact;
}}
.sm-page {{
  position: relative; width: {template.width_in:g}in; height: {template.height_in:g}in;
  overflow: hidden; background: var(--sm-paper);
}}
.sm-safe {{ position: absolute; inset: {margin:g}in; }}
.sm-section {{ position: absolute; overflow: hidden; }}
.sm-section--title {{
  display: flex; align-items: center; justify-content: center; text-align: center;
}}
.sm-title {{
  margin: 0; width: 100%; text-align: center;
  font-family: var(--sm-font-heading); font-weight: var(--sm-heading-weight);
  text-transform: var(--sm-heading-transform); letter-spacing: var(--sm-heading-tracking);
  font-size: var(--sm-title-pt); line-height: 1.08; color: var(--sm-title);
}}
.sm-section--logo {{
  display: flex; align-items: center; justify-content: center;
}}
.sm-logo-panel {{
  height: 100%; display: flex; align-items: center; justify-content: center;
  padding: 0.05in 0.22in;
}}
.sm-logo-panel img {{ height: 100%; width: auto; display: block; }}
.sm-section--footer {{
  display: flex; align-items: center; justify-content: space-between; gap: 0.2in;
  border-top: 0.75pt solid var(--sm-rule); padding-top: 0.04in;
  font-size: 7.5pt; line-height: 1.25; color: var(--sm-muted);
}}
.sm-footer-text {{ min-width: 0; }}
.sm-disclaimer {{ margin-left: auto; text-align: right; font-size: 7pt; color: var(--sm-muted); }}
.sm-section--flexible {{ padding: 0.12in 0.06in 0.06in; }}
.sm-section--divided {{ border-left: 0.75pt solid var(--sm-rule); padding-left: 0.14in; }}
.sm-section--leading {{ padding-right: 0.14in; }}
.sm-section--card {{ padding: {CARD_PADDING_IN}in {CARD_PADDING_IN}in {CARD_PADDING_IN + CARD_DISCLAIMER_IN}in; }}
.sm-card-disclaimer {{
  position: absolute; left: {CARD_PADDING_IN}in; right: {CARD_PADDING_IN}in; bottom: 0.07in;
  font-size: 5.5pt; line-height: 1.1; color: var(--sm-muted); text-align: center;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}}
.sm-cutlines {{ position: absolute; inset: 0; pointer-events: none; }}
.sm-flow {{ display: flex; width: 100%; height: 100%; min-height: 0; }}
.sm-flow--stack {{ flex-direction: column; }}
.sm-flow--row {{ flex-direction: row; }}
.sm-flow--grid {{ display: grid; grid-template-columns: 1fr 1fr; grid-auto-rows: 1fr; }}
.sm-flow--center {{ justify-content: center; }}
.sm-comp {{ min-width: 0; min-height: 0; overflow: hidden; margin: 0; }}
.sm-comp--visual {{ display: flex; flex-direction: column; align-items: center; justify-content: center; }}
.sm-comp--visual > svg, .sm-comp--visual > img {{
  width: 100%; height: auto; max-height: 100%; min-height: 0; flex: 0 1 auto; object-fit: contain; display: block;
}}
.sm-caption {{ flex: none; margin-top: 0.04in; font-size: 7.5pt; line-height: 1.2; color: var(--sm-muted); text-align: center; }}
.sm-text {{ font-size: calc(var(--sm-body-pt) * var(--sm-scale, 1)); line-height: 1.32; }}
.sm-text > :first-child {{ margin-top: 0; }}
.sm-text > :last-child {{ margin-bottom: 0; }}
.sm-text h2, .sm-text h3, .sm-text h4 {{
  font-family: var(--sm-font-heading); font-weight: var(--sm-heading-weight);
  text-transform: var(--sm-heading-transform); letter-spacing: var(--sm-heading-tracking);
  color: var(--sm-heading); line-height: 1.1; margin: 0.55em 0 0.25em;
}}
.sm-text h2 {{ font-size: 1.4em; }}
.sm-text h3 {{ font-size: 1.18em; }}
.sm-text h4 {{ font-size: 1em; color: var(--sm-ink); }}
.sm-text p, .sm-text li, .sm-text dd {{ margin: 0 0 0.35em; }}
.sm-text ul, .sm-text ol {{ margin: 0 0 0.5em 1.15em; padding: 0; }}
.sm-text li::marker {{ color: var(--sm-accent); font-weight: 700; }}
.sm-text .list-compact li {{ margin-bottom: 0.1em; }}
.sm-text dl {{ margin: 0 0 0.5em; }}
.sm-text dt, .sm-text .key-term {{ font-weight: 700; color: var(--sm-accent); }}
.sm-text dd {{ margin-left: 0.9em; }}
.sm-text .definition {{ margin: 0 0 0.35em; }}
.sm-text .kicker, .sm-text .label {{
  font-size: 0.76em; letter-spacing: 0.08em; text-transform: uppercase; color: var(--sm-secondary); font-weight: 700;
}}
.sm-text .lead {{ font-size: 1.1em; }}
.sm-text .callout {{
  border-left: 3pt solid var(--sm-rule); background: var(--sm-panel); padding: 0.3em 0.5em; margin: 0 0 0.5em;
}}
.sm-text .takeaways {{ border-top: 1.5pt solid var(--sm-accent); padding-top: 0.3em; margin-top: 0.4em; }}
.sm-text .question {{ font-weight: 700; }}
.sm-text .caption {{ font-size: 0.8em; color: var(--sm-muted); }}
.sm-text .formula {{ font-family: 'IBM Plex Mono', 'Courier New', monospace; }}
.sm-text .cols-2 {{ columns: 2; column-gap: 0.18in; }}
.sm-text .compare {{ display: grid; grid-template-columns: 1fr 1fr; gap: 0.12in; }}
.sm-text blockquote {{ margin: 0 0 0.5em; padding-left: 0.6em; border-left: 2pt solid var(--sm-accent); font-style: italic; }}
.sm-text table {{ width: 100%; border-collapse: collapse; margin: 0 0 0.5em; font-size: 0.92em; }}
.sm-text th, .sm-text td {{ border: 0.5pt solid var(--sm-border); padding: 0.15em 0.35em; text-align: left; vertical-align: top; }}
.sm-text th {{ background: var(--sm-panel); font-weight: 700; }}
.sm-text hr {{ border: 0; border-top: 0.75pt solid var(--sm-rule); margin: 0.5em 0; }}
.sm-comp.is-emphasis.sm-text {{ border-top: 2pt solid var(--sm-accent); padding-top: 0.08in; }}
"""


def _box_style(template: Template, section: TemplateSection) -> str:
    box = section.box
    return f"left:{box.x}%;top:{box.y}%;width:{box.w}%;height:{box.h}%;"


def _component_html(component: RenderComponent, layout: SectionLayout) -> str:
    size = layout.sizes.get(component.id)
    classes = ["sm-comp"]
    if layout.emphasis == component.id:
        classes.append("is-emphasis")

    if layout.arrangement == "grid":
        flex = ""
    elif component.is_visual:
        flex = f"flex:0 0 {size or 45}%;"
    else:
        flex = f"flex:{max(1, size or 1)} 1 0%;"

    data = f'data-component="{escape(component.id, quote=True)}" data-type="{component.component_type}"'
    if component.component_type == "text":
        classes.extend(["sm-comp--text", "sm-text"])
        return f'<div class="{" ".join(classes)}" {data} style="{flex}">{component.html or ""}</div>'

    classes.extend(["sm-comp--visual", f"sm-comp--{component.component_type}"])
    if component.component_type == "diagram":
        media = component.svg or ""
    else:
        media = (
            f'<img src="{escape(component.image_src or "", quote=True)}" '
            f'alt="{escape(component.alt, quote=True)}" />'
        )
    caption = f'<figcaption class="sm-caption">{escape(component.caption)}</figcaption>' if component.caption else ""
    return f'<figure class="{" ".join(classes)}" {data} style="{flex}">{media}{caption}</figure>'


def _flexible_section_html(
    data: RenderInput,
    section: TemplateSection,
    components: list[RenderComponent],
) -> str:
    template = data.template
    width_in, height_in = template.section_size_in(section)
    layout = data.layout.get(section.id) or default_section_layout(
        [component.id for component in components],
        {component.id for component in components if component.is_visual},
        section_aspect=width_in / height_in if height_in else 1,
    )
    by_id = {component.id: component for component in components}
    ordered = [by_id[cid] for cid in layout.order if cid in by_id]
    ordered.extend(component for component in components if component.id not in layout.order)

    classes = ["sm-section", "sm-section--flexible"]
    if template.disclaimer == "per_section":
        classes.append("sm-section--card")
    elif not template.cut_lines:
        neighbors = [other for other in template.flexible_sections if other.id != section.id]
        if any(abs(other.box.x + other.box.w - section.box.x) < 0.01 for other in neighbors):
            classes.append("sm-section--divided")
        if any(abs(section.box.x + section.box.w - other.box.x) < 0.01 for other in neighbors):
            classes.append("sm-section--leading")

    flow_classes = ["sm-flow", f"sm-flow--{layout.arrangement}"]
    if layout.align == "center":
        flow_classes.append("sm-flow--center")
    gap = GAP_IN.get(layout.gap, GAP_IN["normal"])
    inner = "".join(_component_html(component, layout) for component in ordered)
    disclaimer = ""
    if template.disclaimer == "per_section" and data.theme.disclaimer:
        disclaimer = f'<div class="sm-card-disclaimer">{escape(data.theme.disclaimer)}</div>'

    return (
        f'<section class="{" ".join(classes)}" data-section="{section.id}" style="{_box_style(template, section)}">'
        f'<div class="{" ".join(flow_classes)}" style="gap:{gap}in;--sm-scale:{layout.font_scale};">{inner}</div>'
        f"{disclaimer}</section>"
    )


def _strict_section_html(data: RenderInput, section: TemplateSection) -> str:
    style = _box_style(data.template, section)
    attrs = f'data-section="{section.id}" style="{style}"'
    if section.content == "title":
        return (
            f'<header class="sm-section sm-section--title" {attrs}>'
            f'<h1 class="sm-title">{escape(data.title)}</h1></header>'
        )
    if section.content == "logo":
        panel = ""
        logo_id = data.options.get("logo_id") if data.options.get("logo_locked") else None
        if logo_id:
            logo = data.theme.logo(str(logo_id))
            panel = (
                f'<div class="sm-logo-panel"><img src="{asset_data_uri(logo.file)}" '
                f'alt="{escape(logo.label, quote=True)}" /></div>'
            )
        return f'<div class="sm-section sm-section--logo" {attrs}>{panel}</div>'
    footer_text = str(data.options.get("footer_text") or "")
    disclaimer = (
        f'<span class="sm-disclaimer">{escape(data.theme.disclaimer)}</span>'
        if data.theme.disclaimer and data.template.disclaimer == "footer"
        else ""
    )
    return (
        f'<footer class="sm-section sm-section--footer" {attrs}>'
        f'<span class="sm-footer-text">{escape(footer_text)}</span>{disclaimer}</footer>'
    )


def _cut_lines_svg(template: Template) -> str:
    xs = sorted({s.box.x for s in template.sections} | {s.box.x + s.box.w for s in template.sections})
    ys = sorted({s.box.y for s in template.sections} | {s.box.y + s.box.h for s in template.sections})
    lines = [
        f'<line x1="{x}%" y1="0" x2="{x}%" y2="100%" />' for x in xs
    ] + [
        f'<line x1="0" y1="{y}%" x2="100%" y2="{y}%" />' for y in ys
    ]
    return (
        '<svg class="sm-cutlines" aria-hidden="true" xmlns="http://www.w3.org/2000/svg" width="100%" height="100%">'
        '<g stroke="#A7A7A7" stroke-width="0.6" stroke-dasharray="4 3" fill="none">'
        f'{"".join(lines)}</g></svg>'
    )


def render_document(data: RenderInput) -> str:
    template = data.template
    by_section: dict[str, list[RenderComponent]] = {}
    for component in data.components:
        by_section.setdefault(component.section_id, []).append(component)

    sections_html: list[str] = []
    for section in template.sections:
        if section.is_flexible:
            sections_html.append(_flexible_section_html(data, section, by_section.get(section.id, [])))
        else:
            sections_html.append(_strict_section_html(data, section))

    cut_lines = _cut_lines_svg(template) if template.cut_lines else ""
    return (
        '<!DOCTYPE html><html lang="en"><head><meta charset="utf-8" />'
        f"<title>{escape(data.title)}</title>"
        f"<style>{_css(template, data.theme)}</style></head><body>"
        f'<main class="sm-page" data-template="{template.id}" data-theme="{data.theme.id}">'
        f'<div class="sm-safe">{cut_lines}{"".join(sections_html)}</div>'
        "</main></body></html>"
    )
