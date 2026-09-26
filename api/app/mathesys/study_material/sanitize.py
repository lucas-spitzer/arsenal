"""Sanitize model-written HTML for Text components.

The theme owns every visual decision, so model HTML keeps structure only: no
inline styles, no scripts, no external resources, and only the classes the
renderer styles.
"""

from __future__ import annotations

from html import escape
from html.parser import HTMLParser

SKIP_TAGS = frozenset({"script", "style", "iframe", "object", "embed", "link", "meta", "svg", "img"})
VOID_TAGS = frozenset({"br", "hr"})
ALLOWED_TAGS = frozenset(
    {
        "section",
        "div",
        "span",
        "p",
        "h2",
        "h3",
        "h4",
        "ul",
        "ol",
        "li",
        "dl",
        "dt",
        "dd",
        "table",
        "thead",
        "tbody",
        "tr",
        "th",
        "td",
        "strong",
        "em",
        "b",
        "i",
        "code",
        "small",
        "blockquote",
        "br",
        "hr",
        "sup",
        "sub",
    }
)
# Heading levels the model may not use are demoted rather than dropped, so the
# words survive and the title stays the only h1 on the page.
TAG_ALIASES = {"h1": "h2", "h5": "h4", "h6": "h4"}
ALLOWED_CLASSES = frozenset(
    {
        "callout",
        "caption",
        "cols-2",
        "compare",
        "definition",
        "formula",
        "key-term",
        "kicker",
        "label",
        "lead",
        "list-compact",
        "question",
        "steps",
        "takeaways",
    }
)
_GLOBAL_ATTRS = frozenset({"class"})
_TABLE_ATTRS = frozenset({"class", "colspan", "rowspan"})
_ATTRS_BY_TAG = {"td": _TABLE_ATTRS, "th": _TABLE_ATTRS}


class _FragmentSanitizer(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        lowered = TAG_ALIASES.get(tag.lower(), tag.lower())
        if self._skip_depth:
            if lowered in SKIP_TAGS:
                self._skip_depth += 1
            return
        if lowered in SKIP_TAGS:
            if lowered not in VOID_TAGS and lowered != "img":
                self._skip_depth = 1
            return
        if lowered not in ALLOWED_TAGS:
            return
        self.parts.append(_render_start(lowered, attrs))

    def handle_endtag(self, tag: str) -> None:
        lowered = TAG_ALIASES.get(tag.lower(), tag.lower())
        if self._skip_depth:
            if lowered in SKIP_TAGS:
                self._skip_depth -= 1
            return
        if lowered in SKIP_TAGS or lowered not in ALLOWED_TAGS or lowered in VOID_TAGS:
            return
        self.parts.append(f"</{lowered}>")

    def handle_data(self, data: str) -> None:
        if self._skip_depth or not data:
            return
        self.parts.append(escape(data, quote=False))

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        lowered = TAG_ALIASES.get(tag.lower(), tag.lower())
        if self._skip_depth or lowered in SKIP_TAGS or lowered not in ALLOWED_TAGS:
            return
        self.parts.append(_render_start(lowered, attrs, self_closing=True))


def _render_start(
    tag: str,
    attrs: list[tuple[str, str | None]],
    *,
    self_closing: bool = False,
) -> str:
    allowed = _ATTRS_BY_TAG.get(tag, _GLOBAL_ATTRS)
    cleaned: list[str] = []
    for raw_name, raw_value in attrs:
        name = (raw_name or "").lower()
        if name not in allowed:
            continue
        value = raw_value or ""
        if name == "class":
            kept = [cls for cls in value.split() if cls in ALLOWED_CLASSES]
            if not kept:
                continue
            value = " ".join(kept)
        elif name in {"colspan", "rowspan"} and not value.isdigit():
            continue
        cleaned.append(f'{name}="{escape(value, quote=True)}"')
    attr_html = (" " + " ".join(cleaned)) if cleaned else ""
    if tag in VOID_TAGS or self_closing:
        return f"<{tag}{attr_html} />"
    return f"<{tag}{attr_html}>"


def sanitize_fragment(raw: str) -> str:
    parser = _FragmentSanitizer()
    parser.feed(raw or "")
    parser.close()
    return "".join(parser.parts).strip()
