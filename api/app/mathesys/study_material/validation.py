"""Finalization checks: geometry, clipping, image resolution, fonts, assets."""

from __future__ import annotations

from typing import Any

import fitz

from app.mathesys.study_material.catalog import Template
from app.mathesys.study_material.printer import FitReport

MIN_IMAGE_DPI = 150
PAGE_TOLERANCE_IN = 0.02
PDF_POINTS_PER_IN = 72


def _issue(code: str, message: str, **refs: str) -> dict[str, Any]:
    return {"code": code, "message": message, **refs}


def fit_issues(
    report: FitReport,
    template: Template,
    *,
    component_labels: dict[str, str],
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    if (
        abs(report.page_width_in - template.width_in) > PAGE_TOLERANCE_IN
        or abs(report.page_height_in - template.height_in) > PAGE_TOLERANCE_IN
    ):
        issues.append(
            _issue(
                "page_size",
                f"Page rendered at {report.page_width_in} × {report.page_height_in} in; "
                f"expected {template.width_in} × {template.height_in} in.",
            ),
        )

    section_labels = {section.id: section.label for section in template.sections}
    flagged_components: set[str] = set()
    for item in report.components:
        label = component_labels.get(item["id"], item["id"])
        if item.get("overflow"):
            flagged_components.add(item["section"])
            noun = {"text": "Text", "diagram": "Diagram", "image": "Image"}.get(item.get("type"), "Content")
            issues.append(
                _issue(
                    "clipped",
                    f"{noun} in {section_labels.get(item['section'], item['section'])} is clipped ({label}).",
                    section_id=item["section"],
                    component_id=item["id"],
                ),
            )
        if item.get("collapsed"):
            issues.append(
                _issue(
                    "collapsed",
                    f"{label} has almost no room in {section_labels.get(item['section'], item['section'])}.",
                    section_id=item["section"],
                    component_id=item["id"],
                ),
            )

    for item in report.sections:
        if item.get("overflow") and item["id"] not in flagged_components:
            issues.append(
                _issue(
                    "section_overflow",
                    f"{section_labels.get(item['id'], item['id'])} content exceeds its boundary.",
                    section_id=item["id"],
                ),
            )

    for item in report.images:
        label = component_labels.get(item["id"], item["id"])
        if not item.get("loaded"):
            issues.append(_issue("asset_missing", f"{label} image did not load.", component_id=item["id"]))
        elif item.get("dpi", 0) < MIN_IMAGE_DPI:
            issues.append(
                _issue(
                    "low_resolution",
                    f"{label} prints at {round(item['dpi'])} DPI; the minimum is {MIN_IMAGE_DPI}.",
                    component_id=item["id"],
                ),
            )

    for family in report.font_errors:
        issues.append(_issue("font", f"Font '{family}' failed to load."))

    return issues


def pdf_issues(pdf: bytes, template: Template) -> list[dict[str, Any]]:
    document = fitz.open(stream=pdf, filetype="pdf")
    try:
        issues: list[dict[str, Any]] = []
        if document.page_count != 1:
            issues.append(_issue("page_count", f"PDF has {document.page_count} pages; expected 1."))
        if document.page_count:
            rect = document[0].rect
            width_in = rect.width / PDF_POINTS_PER_IN
            height_in = rect.height / PDF_POINTS_PER_IN
            if (
                abs(width_in - template.width_in) > PAGE_TOLERANCE_IN
                or abs(height_in - template.height_in) > PAGE_TOLERANCE_IN
            ):
                issues.append(
                    _issue(
                        "pdf_page_size",
                        f"PDF page is {width_in:.2f} × {height_in:.2f} in; "
                        f"expected {template.width_in} × {template.height_in} in.",
                    ),
                )
        return issues
    finally:
        document.close()
