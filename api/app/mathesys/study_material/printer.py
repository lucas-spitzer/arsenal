"""Headless Chromium seam: measure rendered HTML and print it to PDF.

Chromium renders the same HTML the draft preview shows, so the PDF matches it.
Requires ``playwright`` and a one-time ``playwright install chromium``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

CSS_PX_PER_IN = 96
OVERFLOW_TOLERANCE_PX = 1.5

_MEASURE_SCRIPT = """
async (tolerance) => {
  await document.fonts.ready;
  await Promise.all([...document.images].map((img) => img.complete ? null :
    new Promise((resolve) => { img.onload = resolve; img.onerror = resolve; })));
  const over = (el) => el.scrollHeight - el.clientHeight > tolerance
    || el.scrollWidth - el.clientWidth > tolerance;
  const page = document.querySelector('.sm-page').getBoundingClientRect();
  const sections = [...document.querySelectorAll('[data-section]')].map((el) => {
    const title = el.querySelector('.sm-title');
    const titleClipped = title && title.getBoundingClientRect().height - el.clientHeight > tolerance;
    const truncated = [...el.querySelectorAll('.sm-card-disclaimer')]
      .some((child) => child.scrollWidth - child.clientWidth > tolerance);
    return { id: el.dataset.section, overflow: over(el) || titleClipped || truncated };
  });
  const components = [...document.querySelectorAll('[data-component]')].map((el) => {
    const media = el.querySelector(':scope > svg, :scope > img');
    return {
      id: el.dataset.component,
      type: el.dataset.type,
      section: el.closest('[data-section]').dataset.section,
      overflow: over(el),
      collapsed: el.clientHeight < 12 || el.clientWidth < 12 || (media && (media.clientHeight < 12 || media.clientWidth < 12)),
    };
  });
  const images = [...document.querySelectorAll('.sm-comp--image > img')].map((img) => {
    const ratio = Math.min(img.clientWidth / (img.naturalWidth || 1), img.clientHeight / (img.naturalHeight || 1));
    const renderedIn = (img.naturalWidth * ratio) / 96;
    return {
      id: img.closest('[data-component]').dataset.component,
      loaded: img.complete && img.naturalWidth > 0,
      dpi: renderedIn > 0 ? img.naturalWidth / renderedIn : 0,
    };
  });
  const fontErrors = [...document.fonts].filter((face) => face.status === 'error').map((face) => face.family);
  return {
    page: { width: page.width, height: page.height },
    sections, components, images, fontErrors,
  };
}
"""


@dataclass
class FitReport:
    page_width_in: float
    page_height_in: float
    sections: list[dict[str, Any]] = field(default_factory=list)
    components: list[dict[str, Any]] = field(default_factory=list)
    images: list[dict[str, Any]] = field(default_factory=list)
    font_errors: list[str] = field(default_factory=list)

    def overflowing_sections(self) -> set[str]:
        flagged = {item["id"] for item in self.sections if item.get("overflow")}
        flagged |= {item["section"] for item in self.components if item.get("overflow")}
        return flagged


class HtmlRenderer(Protocol):
    def measure(self, html: str, *, width_in: float, height_in: float) -> FitReport: ...

    def print_pdf(self, html: str, *, width_in: float, height_in: float) -> bytes: ...


class ChromiumRenderer:
    """One browser per job; call close() (or use as a context manager) when done."""

    def __init__(self) -> None:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise RuntimeError(
                "playwright is required to render study material. "
                "Install it in the API environment, then run `playwright install chromium`.",
            ) from exc
        self._playwright = sync_playwright().start()
        try:
            self._browser = self._playwright.chromium.launch()
        except Exception:
            self._playwright.stop()
            raise

    def __enter__(self) -> ChromiumRenderer:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def close(self) -> None:
        try:
            self._browser.close()
        finally:
            self._playwright.stop()

    def _page(self, html: str, *, width_in: float, height_in: float) -> Any:
        page = self._browser.new_page(
            viewport={
                "width": round(width_in * CSS_PX_PER_IN),
                "height": round(height_in * CSS_PX_PER_IN),
            },
        )
        page.emulate_media(media="print")
        page.set_content(html, wait_until="networkidle")
        return page

    def measure(self, html: str, *, width_in: float, height_in: float) -> FitReport:
        page = self._page(html, width_in=width_in, height_in=height_in)
        try:
            raw = page.evaluate(_MEASURE_SCRIPT, OVERFLOW_TOLERANCE_PX)
        finally:
            page.close()
        return FitReport(
            page_width_in=round(raw["page"]["width"] / CSS_PX_PER_IN, 3),
            page_height_in=round(raw["page"]["height"] / CSS_PX_PER_IN, 3),
            sections=raw["sections"],
            components=raw["components"],
            images=raw["images"],
            font_errors=sorted(set(raw["fontErrors"])),
        )

    def print_pdf(self, html: str, *, width_in: float, height_in: float) -> bytes:
        page = self._page(html, width_in=width_in, height_in=height_in)
        try:
            page.evaluate("document.fonts.ready.then(() => true)")
            pdf = page.pdf(
                width=f"{width_in}in",
                height=f"{height_in}in",
                print_background=True,
                prefer_css_page_size=True,
                margin={"top": "0", "right": "0", "bottom": "0", "left": "0"},
            )
        finally:
            page.close()
        if not pdf:
            raise RuntimeError("Chromium produced an empty PDF.")
        return pdf
