import fitz
import pytest

from app.intellex.structuring.boundaries import auto_boundaries, trim
from app.intellex.structuring.chunk import (
    build_segments_and_chapters,
    display_markdown,
    flatten_markdown,
)
from app.worker.narration_executor import pack_chapter_clips
from app.intellex.structuring.classify import classify
from app.intellex.structuring.models import Book, Chapter, Paragraph, Section, book_from_dict
from app.intellex.structuring.normalize import normalize_structured_pages
from app.intellex.structuring.validate import (
    StructureValidationError,
    _norm,
    pdf_text_layer,
    validate_against_pdf,
)
from app.mathesys.structured_epub import book_to_epub_chapters


def _item(itype, md, *, value=None, level=None, bbox=None):
    item = {"type": itype, "md": md}
    if value is not None:
        item["value"] = value
    if level is not None:
        item["level"] = level
    if bbox is not None:
        item["bbox"] = bbox
    return item


def _page(page_number, items):
    return {"page_number": page_number, "items": items}


def _bbox(label: str, confidence: float, *, count: int = 1):
    return [
        {"label": label, "confidence": confidence, "x": index, "y": index}
        for index in range(count)
    ]


def _doc_pages():
    """A miniature document exercising every rule the stages must enforce."""
    return [
        _page(1, [
            _item("header", "MCDP 1"),
            _item("heading", "# Warfighting", value="Warfighting", level=1),
            _item("text", "Front matter title page.", value="Front matter title page."),
            _item("footer", "i"),
        ]),
        _page(2, [
            _item("header", "MCDP 1"),
            _item("heading", "# FOREWORD", value="FOREWORD", level=1),
            _item("text", "Front matter foreword body.", value="Front matter foreword body."),
        ]),
        _page(3, [
            _item("heading", "# Chapter 1", value="Chapter 1", level=1),       # bare marker
            _item("heading", "# The Nature of War", value="The Nature of War", level=1),  # title (merged)
            _item("text", '*"An epigraph."*<sup>1</sup>', value='"An epigraph."'),   # footnote marker
            _item("heading", "# WAR DEFINED", value="WAR DEFINED", level=1),   # section as L1
            _item("text", "War is a clash of wills.<sup>2</sup>", value="War is a clash of wills."),
            _item("code", "graph TD; A-->B", value="graph TD; A-->B"),         # figure -> dropped
            _item("heading", "## FRICTION", value="FRICTION", level=2),        # section as L2
            _item("text", "Friction makes the simple difficult.", value="Friction makes the simple difficult."),
        ]),
        _page(4, [
            _item("heading", "# Chapter 2", value="Chapter 2", level=1),
            _item("heading", "# The Theory of War", value="The Theory of War", level=1),
            _item("text", "Theory frames practice.", value="Theory frames practice."),
            _item("heading", "## CONCLUSION", value="CONCLUSION", level=2),
            _item("text", "War is an extension of policy.", value="War is an extension of policy."),
        ]),
        _page(5, [
            # Back matter: chapter titles reappear as endnote dividers.
            _item("heading", "# The Nature of War", value="The Nature of War", level=1),
            _item("list", "1. A note.\n2. Another note.", value=None),
            _item("text", "Endnote text that must be excluded.", value="Endnote text that must be excluded."),
        ]),
    ]


def _build_book():
    elements, _ = normalize_structured_pages(_doc_pages())
    start, end, _ = auto_boundaries(elements)
    return elements, classify(trim(elements, start_index=start, end_index=end))


def test_normalize_drops_headers_and_footers_and_indexes_in_order() -> None:
    elements, dropped = normalize_structured_pages(_doc_pages())

    assert dropped == {"header": 2, "footer": 1}
    assert all(e.type != "header" and e.type != "footer" for e in elements)
    # Indices are sequential reading order; page numbers are preserved.
    assert [e.index for e in elements] == list(range(len(elements)))
    assert elements[0].text == "Warfighting" and elements[0].page == 1


def test_normalize_preserves_compact_layout_provenance() -> None:
    pages = [
        _page(1, [
            _item(
                "heading",
                "# TEST",
                value="TEST",
                bbox=[
                    {"label": "paragraph_title", "confidence": 0.94},
                    {"label": "text", "confidence": 0.81},
                ],
            ),
        ]),
    ]

    elements, _ = normalize_structured_pages(pages)

    assert elements[0].layout_labels == ("paragraph_title", "text")
    assert elements[0].min_layout_confidence == pytest.approx(0.81)
    assert elements[0].max_layout_confidence == pytest.approx(0.94)
    assert elements[0].layout_fragment_count == 2
    assert elements[0].to_dict()["layout_labels"] == ["paragraph_title", "text"]


def test_normalize_keeps_division_labels_typed_as_headers() -> None:
    pages = [
        _page(10, [
            _item("header", "THE ARMED FORCES OFFICER"),
            _item("header", "CHAPTER ONE"),
            _item("footer", "1"),
            _item("heading", "# The Commission and the Oath", value="The Commission and the Oath", level=1),
        ]),
    ]

    elements, dropped = normalize_structured_pages(pages)

    assert dropped == {"header": 1, "footer": 1}
    assert [(element.type, element.text) for element in elements] == [
        ("heading", "CHAPTER ONE"),
        ("heading", "The Commission and the Oath"),
    ]


def test_auto_boundaries_detects_first_chapter_and_repeated_title_back_matter() -> None:
    elements, _ = normalize_structured_pages(_doc_pages())
    start, end, reasons = auto_boundaries(elements)

    start_el = next(e for e in elements if e.index == start)
    end_el = next(e for e in elements if e.index == end)
    assert start_el.text == "Chapter 1"            # skips title page + FOREWORD
    assert end_el.text == "The Nature of War" and end_el.page == 5  # endnotes divider
    assert "repeated chapter title" in reasons["end"]


def test_auto_boundaries_detects_spelled_out_chapter_numbers() -> None:
    pages = [
        _page(1, [
            _item("heading", "# Contents", value="Contents", level=1),
            _item("heading", "# Foreword", value="Foreword", level=1),
            _item("heading", "# Introduction", value="Introduction", level=1),
        ]),
        _page(50, [
            _item("heading", "# CHAPTER ONE", value="CHAPTER ONE", level=1),
            _item("heading", "# Tending to Produce", value="Tending to Produce", level=1),
            _item("text", "Boyd's early career.", value="Boyd's early career."),
        ]),
        _page(82, [
            _item("heading", "# CHAPTER TWO", value="CHAPTER TWO", level=1),
            _item("heading", "# Done with the Jungle", value="Done with the Jungle", level=1),
            _item("text", "After Vietnam.", value="After Vietnam."),
        ]),
        _page(226, [
            _item("heading", "# Epilogue", value="Epilogue", level=1),
            _item("text", "Back-matter close.", value="Back-matter close."),
        ]),
        _page(248, [
            _item("heading", "# APPENDIX A", value="APPENDIX A", level=1),
        ]),
    ]
    elements, _ = normalize_structured_pages(pages)
    start, end, reasons = auto_boundaries(elements)

    start_el = next(e for e in elements if e.index == start)
    end_el = next(e for e in elements if e.index == end)
    assert start_el.text == "CHAPTER ONE"
    assert end_el.text == "Epilogue"
    assert "first bare chapter marker" in reasons["start"]
    assert "back-matter label" in reasons["end"]


def test_auto_boundaries_starts_after_contents_cluster_of_chapter_kickers() -> None:
    pages = [
        _page(5, [
            _item("heading", "# Contents", value="Contents", level=1),
            _item("heading", "# CHAPTER ONE", value="CHAPTER ONE", level=1),
            _item("heading", "# CHAPTER TWO", value="CHAPTER TWO", level=1),
        ]),
        _page(10, [
            _item("header", "CHAPTER ONE"),
            _item("heading", "# The Commission and the Oath", value="The Commission and the Oath", level=1),
            _item("text", "You become an officer by accepting a commission.", value="You become an officer by accepting a commission."),
        ]),
        _page(23, [
            _item("header", "CHAPTER TWO"),
            _item("heading", "# The Profession of Arms", value="The Profession of Arms", level=1),
            _item("text", "Humans fight as individuals and as groups.", value="Humans fight as individuals and as groups."),
        ]),
        _page(153, [
            _item("heading", "# APPENDIX A", value="APPENDIX A", level=1),
            _item("text", "Founding documents.", value="Founding documents."),
        ]),
    ]
    elements, _ = normalize_structured_pages(pages)
    start, end, reasons = auto_boundaries(elements)
    trimmed = trim(elements, start_index=start, end_index=end)
    book = classify(trimmed)

    start_el = next(element for element in elements if element.index == start)
    end_el = next(element for element in elements if element.index == end)
    assert start_el.text == "CHAPTER ONE" and start_el.page == 10
    assert end_el.text == "APPENDIX A"
    assert "contents cluster" in reasons["start"]
    assert [chapter.title for chapter in book.chapters] == [
        "CHAPTER ONE The Commission and the Oath",
        "CHAPTER TWO The Profession of Arms",
    ]


def test_auto_boundaries_treats_same_line_chapter_title_as_division() -> None:
    pages = [
        _page(3, [
            _item("heading", "# Chapter 1: The Nature of War", value="Chapter 1: The Nature of War", level=1),
            _item("text", "War is a clash of wills.", value="War is a clash of wills."),
            _item("heading", "# Chapter 2: The Theory of War", value="Chapter 2: The Theory of War", level=1),
            _item("text", "Theory frames practice.", value="Theory frames practice."),
            _item("heading", "# Notes", value="Notes", level=1),
        ]),
    ]
    elements, _ = normalize_structured_pages(pages)
    start, end, _ = auto_boundaries(elements)
    book = classify(trim(elements, start_index=start, end_index=end))

    assert next(element for element in elements if element.index == start).text == "Chapter 1: The Nature of War"
    assert next(element for element in elements if element.index == end).text == "Notes"
    assert [chapter.title for chapter in book.chapters] == [
        "Chapter 1: The Nature of War",
        "Chapter 2: The Theory of War",
    ]


def test_auto_boundaries_treats_part_labels_as_divisions() -> None:
    pages = [
        _page(1, [
            _item("heading", "# Preface", value="Preface", level=1),
            _item("text", "Opening note.", value="Opening note."),
        ]),
        _page(4, [
            _item("heading", "# Part I", value="Part I", level=1),
            _item("heading", "# The Commission", value="The Commission", level=1),
            _item("text", "Officers accept a commission.", value="Officers accept a commission."),
        ]),
        _page(20, [
            _item("heading", "# Part II", value="Part II", level=1),
            _item("text", "The profession has its own ethic.", value="The profession has its own ethic."),
            _item("heading", "# Index", value="Index", level=1),
        ]),
    ]
    elements, _ = normalize_structured_pages(pages)
    start, end, _ = auto_boundaries(elements)
    book = classify(trim(elements, start_index=start, end_index=end))

    assert next(element for element in elements if element.index == start).text == "Part I"
    assert next(element for element in elements if element.index == end).text == "Index"
    assert [chapter.title for chapter in book.chapters] == [
        "Part I The Commission",
        "Part II",
    ]


def test_a_sentence_that_mentions_a_chapter_is_not_a_new_chapter() -> None:
    pages = [
        _page(37, [
            _item("text", "logo: CHAPTER THREE with decorative flourish", value="logo: CHAPTER THREE with decorative flourish"),
            _item("heading", "# The Officer in the Profession of Arms", value="The Officer in the Profession of Arms", level=1),
            _item(
                "text",
                "Chapter 2 described four characteristics common to all professions.",
                value="Chapter 2 described four characteristics common to all professions.",
            ),
            _item("heading", "# Character and Character Development", value="Character and Character Development", level=1),
            _item("text", "Mature adults can be reminded of the values.", value="Mature adults can be reminded of the values."),
        ]),
    ]
    elements, _ = normalize_structured_pages(pages)
    book = classify(elements)

    assert [chapter.title for chapter in book.chapters] == [
        "CHAPTER THREE The Officer in the Profession of Arms",
    ]
    assert [section.title for section in book.chapters[0].sections] == [
        "Character and Character Development",
    ]


def test_logo_kickers_open_every_chapter_and_stop_notes_from_swallowing_the_next() -> None:
    pages = [
        _page(5, [
            _item("text", "CHAPTER ONE\nThe Commission and the Oath 1", value="CHAPTER ONE\nThe Commission and the Oath 1"),
            _item("text", "CHAPTER TWO\nThe Profession of Arms 15", value="CHAPTER TWO\nThe Profession of Arms 15"),
        ]),
        _page(10, [
            _item("text", "logo: CHAPTER ONE with decorative flourish", value="logo: CHAPTER ONE with decorative flourish"),
            _item("heading", "# The Commission and the Oath", value="The Commission and the Oath", level=1),
            _item("text", "You become an officer by accepting a commission.", value="You become an officer by accepting a commission."),
            _item("heading", "# Notes", value="Notes", level=1),
            _item("text", "1 Hackett, The Profession of Arms, 9.", value="1 Hackett, The Profession of Arms, 9."),
        ]),
        _page(37, [
            _item("text", "logo: CHAPTER THREE with decorative flourish", value="logo: CHAPTER THREE with decorative flourish"),
            _item("heading", "# The Officer in the Profession of Arms", value="The Officer in the Profession of Arms", level=1),
            _item("text", "Armed Forces officers are the appointed leaders.", value="Armed Forces officers are the appointed leaders."),
        ]),
        _page(51, [
            _item("text", "CHAPTER FOUR\nlogo: decorative flourish", value="CHAPTER FOUR\nlogo: decorative flourish"),
            _item("heading", "# The Officer at Work: The Ethical Use of Force", value="The Officer at Work: The Ethical Use of Force", level=1),
            _item("text", "Being a person of virtue is necessary.", value="Being a person of virtue is necessary."),
            _item("heading", "# Appendix A: Founding Documents", value="Appendix A: Founding Documents", level=1),
        ]),
    ]
    elements, _ = normalize_structured_pages(pages)
    start, end, _ = auto_boundaries(elements)
    book = classify(trim(elements, start_index=start, end_index=end))

    assert [chapter.title for chapter in book.chapters] == [
        "CHAPTER ONE The Commission and the Oath",
        "CHAPTER THREE The Officer in the Profession of Arms",
        "CHAPTER FOUR The Officer at Work: The Ethical Use of Force",
    ]
    assert "Hackett" not in " ".join(
        paragraph.md for chapter in book.chapters for paragraph in chapter.intro
    )
    assert "Founding Documents" not in " ".join(chapter.title for chapter in book.chapters)


def test_classify_drops_ornament_description_from_chapter_title() -> None:
    pages = [
        _page(23, [
            _item(
                "heading",
                "# CHAPTER TWO\nlogo: decorative flourish The Profession of Arms",
                value="CHAPTER TWO\nlogo: decorative flourish The Profession of Arms",
                level=1,
            ),
            _item(
                "text",
                "Humans fight as individuals and as groups.",
                value="Humans fight as individuals and as groups.",
            ),
        ]),
        _page(37, [
            _item("heading", "# CHAPTER THREE", value="CHAPTER THREE", level=1),
            _item("text", "logo: decorative flourish", value="logo: decorative flourish"),
            _item(
                "heading",
                "# The Officer in the Profession of Arms",
                value="The Officer in the Profession of Arms",
                level=1,
            ),
            _item(
                "text",
                "Armed Forces officers are the appointed leaders.",
                value="Armed Forces officers are the appointed leaders.",
            ),
        ]),
    ]
    elements, _ = normalize_structured_pages(pages)
    book = classify(elements)

    assert book.chapters[0].title == "CHAPTER TWO The Profession of Arms"
    assert "logo" not in book.chapters[0].title.lower()
    assert "flourish" not in book.chapters[0].title.lower()
    assert book.chapters[1].title == "CHAPTER THREE The Officer in the Profession of Arms"
    assert all("flourish" not in paragraph.md for paragraph in book.chapters[1].intro)


def test_classify_strips_footnote_tags_from_section_titles() -> None:
    pages = [
        _page(37, [
            _item("heading", "# CHAPTER THREE", value="CHAPTER THREE", level=1),
            _item(
                "text",
                "Officers are simultaneously leaders and followers.",
                value="Officers are simultaneously leaders and followers.",
            ),
            _item(
                "heading",
                "# Leaders and Followers<sup>19</sup>",
                value="Leaders and Followers<sup>19</sup>",
                level=1,
            ),
            _item(
                "text",
                "Every officer leads and follows.",
                value="Every officer leads and follows.",
            ),
        ]),
    ]
    elements, _ = normalize_structured_pages(pages)
    book = classify(elements)

    assert [section.title for section in book.chapters[0].sections] == ["Leaders and Followers"]
    assert "<sup>" not in book.chapters[0].sections[0].title


def test_classify_drops_in_chapter_notes_until_next_chapter() -> None:
    pages = [
        _page(23, [
            _item("heading", "# CHAPTER TWO", value="CHAPTER TWO", level=1),
            _item(
                "text",
                "Humans fight as individuals and as groups.",
                value="Humans fight as individuals and as groups.",
            ),
            _item("heading", "# Notes", value="Notes", level=1),
            _item(
                "text",
                "1 Hackett, The Profession of Arms, 9.",
                value="1 Hackett, The Profession of Arms, 9.",
            ),
        ]),
        _page(37, [
            _item("heading", "# CHAPTER THREE", value="CHAPTER THREE", level=1),
            _item(
                "text",
                "Armed Forces officers are the appointed leaders.",
                value="Armed Forces officers are the appointed leaders.",
            ),
        ]),
    ]
    elements, _ = normalize_structured_pages(pages)
    book = classify(elements)

    assert [chapter.title for chapter in book.chapters] == ["CHAPTER TWO", "CHAPTER THREE"]
    assert book.chapters[0].sections == []
    assert [paragraph.md for paragraph in book.chapters[0].intro] == [
        "Humans fight as individuals and as groups.",
    ]


def test_auto_boundaries_keeps_middle_when_no_division_markers() -> None:
    pages = [
        _page(1, [
            _item("heading", "# Foreword", value="Foreword", level=1),
            _item("text", "A foreword.", value="A foreword."),
            _item("heading", "# Methods", value="Methods", level=1),
            _item("text", "The method is simple and repeatable for officers.", value="The method is simple and repeatable for officers."),
            _item("heading", "# Results", value="Results", level=1),
            _item("text", "The results follow from the method described above.", value="The results follow from the method described above."),
            _item("heading", "# Bibliography", value="Bibliography", level=1),
            _item("text", "Cited works.", value="Cited works."),
        ]),
    ]
    elements, _ = normalize_structured_pages(pages)
    start, end, reasons = auto_boundaries(elements)
    assert start is not None and end is not None
    assert "error" not in reasons

    trimmed = trim(elements, start_index=start, end_index=end)
    book = classify(trimmed)

    assert [element.text for element in trimmed] == [
        "Methods",
        "The method is simple and repeatable for officers.",
        "Results",
        "The results follow from the method described above.",
    ]
    assert len(book.chapters) == 1
    assert book.chapters[0].title == "Methods"
    assert [section.title for section in book.chapters[0].sections] == ["Results"]


def test_classify_merges_spelled_out_chapter_with_following_title() -> None:
    pages = [
        _page(50, [
            _item("heading", "# CHAPTER ONE", value="CHAPTER ONE", level=1),
            _item("heading", "# Tending to Produce", value="Tending to Produce", level=1),
            _item(
                "heading",
                "# John Boyd from the Pool to the Pentagon",
                value="John Boyd from the Pool to the Pentagon",
                level=1,
            ),
            _item("heading", "# RAISED TO PRODUCE", value="RAISED TO PRODUCE", level=1),
            _item("text", "Boyd's early career.", value="Boyd's early career."),
        ]),
        _page(82, [
            _item("heading", "# CHAPTER TWO", value="CHAPTER TWO", level=1),
            _item("heading", "# Done with the Jungle", value="Done with the Jungle", level=1),
            _item(
                "text",
                "The Marine Corps' Near Future after Vietnam",
                value="The Marine Corps' Near Future after Vietnam",
            ),
            _item("text", "After Vietnam the Corps needed a new theory.", value="After Vietnam the Corps needed a new theory."),
        ]),
    ]
    elements, _ = normalize_structured_pages(pages)
    book = classify(elements)

    assert [chapter.title for chapter in book.chapters] == [
        "CHAPTER ONE Tending to Produce: John Boyd from the Pool to the Pentagon",
        "CHAPTER TWO Done with the Jungle: The Marine Corps' Near Future after Vietnam",
    ]
    assert [section.title for section in book.chapters[0].sections] == ["RAISED TO PRODUCE"]
    assert book.chapters[1].sections == []
    assert [paragraph.md for paragraph in book.chapters[1].intro] == [
        "After Vietnam the Corps needed a new theory.",
    ]


def test_classify_merges_empty_heading_with_following_title_line() -> None:
    pages = [
        _page(82, [
            _item("heading", "# CHAPTER TWO", value="CHAPTER TWO", level=1),
            _item("heading", "# Done with the Jungle", value="Done with the Jungle", level=1),
            _item("heading", "# INTERNAL ADAPTABILITY", value="INTERNAL ADAPTABILITY", level=1),
            _item("text", "The Corps adapted internally.", value="The Corps adapted internally."),
            _item("heading", "# OPLAN 316", value="OPLAN 316", level=1),
            _item(
                "heading",
                "# When the Cold War Almost Went Hot",
                value="When the Cold War Almost Went Hot",
                level=1,
            ),
            _item("text", "The plan assumed a short warning.", value="The plan assumed a short warning."),
        ]),
    ]
    elements, _ = normalize_structured_pages(pages)
    book = classify(elements)

    assert [section.title for section in book.chapters[0].sections] == [
        "INTERNAL ADAPTABILITY",
        "OPLAN 316: When the Cold War Almost Went Hot",
    ]
    assert [paragraph.md for paragraph in book.chapters[0].sections[1].body] == [
        "The plan assumed a short warning.",
    ]


def test_classify_keeps_title_case_section_when_body_intervenes() -> None:
    pages = [
        _page(109, [
            _item("heading", "# CHAPTER THREE", value="CHAPTER THREE", level=1),
            _item(
                "heading",
                "# Where Does the Marine Corps Go from Here?",
                value="Where Does the Marine Corps Go from Here?",
                level=1,
            ),
            _item("heading", "# THE BIG QUESTIONS", value="THE BIG QUESTIONS", level=1),
            _item("text", "Marines asked where to fight next.", value="Marines asked where to fight next."),
            _item("heading", "# Finding a Battlefield", value="Finding a Battlefield", level=1),
            _item("text", "Norway became the candidate theater.", value="Norway became the candidate theater."),
        ]),
    ]
    elements, _ = normalize_structured_pages(pages)
    book = classify(elements)

    assert book.chapters[0].title == "CHAPTER THREE Where Does the Marine Corps Go from Here?"
    assert [section.title for section in book.chapters[0].sections] == [
        "THE BIG QUESTIONS",
        "Finding a Battlefield",
    ]


def test_classify_drops_page_footnotes_and_rejoins_split_sentence() -> None:
    pages = [
        _page(57, [
            _item("heading", "# Chapter 1", value="Chapter 1", level=1),
            _item("heading", "# Tending to Produce", value="Tending to Produce", level=1),
            _item("heading", "# LESSONS IN THE AIR", value="LESSONS IN THE AIR", level=1),
            _item(
                "text",
                "Selected to fly the North American F-86 Sabre jet fighter, Boyd",
                value="Selected to fly the North American F-86 Sabre jet fighter, Boyd",
                bbox=_bbox("text", 0.96),
            ),
            _item(
                "text",
                "<sup>17</sup> Boyd Air Force oral history, 6–7, emphasis in original.",
                value="<sup>17</sup> Boyd Air Force oral history, 6–7, emphasis in original.",
                bbox=_bbox("footnote", 0.96),
            ),
            _item(
                "text",
                "<sup>18</sup> Coram, *Boyd*, 45.",
                value="<sup>18</sup> Coram, Boyd, 45.",
                bbox=_bbox("footnote", 0.97),
            ),
        ]),
        _page(58, [
            _item(
                "text",
                "was promoted to first lieutenant in January 1953, and Boyd only "
                "accumulated 29 missions and 44 combat flight",
                value="was promoted to first lieutenant in January 1953, and Boyd only "
                "accumulated 29 missions and 44 combat flight",
                bbox=_bbox("text", 0.99),
            ),
            _item(
                "text",
                "<sup>21</sup> Boyd official military records.",
                value="<sup>21</sup> Boyd official military records.",
                bbox=_bbox("footnote", 0.97),
            ),
            _item(
                "text",
                "*Gun camera photo of a Russian-built MiG-15.*",
                value="Gun camera photo of a Russian-built MiG-15.",
                bbox=_bbox("caption", 0.97),
            ),
        ]),
        _page(59, [
            _item(
                "text",
                "National Museum of the U.S. Air Force",
                value="National Museum of the U.S. Air Force",
                bbox=_bbox("text", 0.93),
            ),
            _item(
                "text",
                "hours before the signing of the Armistice.",
                value="hours before the signing of the Armistice.",
                bbox=_bbox("text", 1.0),
            ),
        ]),
    ]
    elements, _ = normalize_structured_pages(pages)
    book = classify(elements)

    body = [paragraph.md for paragraph in book.chapters[0].sections[0].body]
    assert body == [
        "Selected to fly the North American F-86 Sabre jet fighter, Boyd "
        "was promoted to first lieutenant in January 1953, and Boyd only "
        "accumulated 29 missions and 44 combat flight hours before the "
        "signing of the Armistice."
    ]
    assert book.dropped_nontext == {
        "footnote": 3,
        "visual_description": 1,
        "caption": 1,
    }
    xhtml = book_to_epub_chapters(book)[0]["xhtml_body"]
    assert "oral history" not in xhtml
    assert "official military records" not in xhtml
    assert "National Museum" not in xhtml
    assert "Gun camera photo" not in xhtml
    assert "<sup>" not in xhtml


def test_classify_drops_source_notes_and_rejoins_split_sentence() -> None:
    pages = [
        _page(1, [
            _item("heading", "# Chapter 1", value="Chapter 1", level=1),
            _item("heading", "# Boyd and the Uncertainty Principle", value="Boyd and the Uncertainty Principle", level=1),
            _item("heading", "# UNCERTAINTY", value="UNCERTAINTY", level=1),
            _item(
                "text",
                "An early incarnation appeared in a 1927 paper by Werner",
                value="An early incarnation appeared in a 1927 paper by Werner",
                bbox=_bbox("text", 0.99),
            ),
            _item(
                "text",
                'Source: Boyd, “Interview #859,” 2–3; and Boyd official military records.',
                value='Source: Boyd, “Interview #859,” 2–3; and Boyd official military records.',
                bbox=_bbox("text", 0.98),
            ),
            _item(
                "text",
                "Heisenberg, entitled “On the Perceptual Content.”",
                value="Heisenberg, entitled “On the Perceptual Content.”",
                bbox=_bbox("text", 0.99),
            ),
        ]),
    ]
    elements, _ = normalize_structured_pages(pages)
    book = classify(elements)

    body = [paragraph.md for paragraph in book.chapters[0].sections[0].body]
    assert body == [
        "An early incarnation appeared in a 1927 paper by Werner "
        "Heisenberg, entitled “On the Perceptual Content.”"
    ]
    assert book.dropped_nontext == {"reference": 1}
    xhtml = book_to_epub_chapters(book)[0]["xhtml_body"]
    assert "Source:" not in xhtml
    assert "official military records" not in xhtml


def test_classify_merges_titles_ignores_level_strips_footnotes_drops_figures() -> None:
    _, book = _build_book()

    assert [c.title for c in book.chapters] == [
        "Chapter 1 The Nature of War",
        "Chapter 2 The Theory of War",
    ]
    # Sections come from headings regardless of L1/L2.
    assert [s.title for s in book.chapters[0].sections] == ["WAR DEFINED", "FRICTION"]
    # The Mermaid code block is dropped; the list (back matter) was trimmed away.
    assert book.dropped_nontext == {"code": 1}
    # Footnote markers are stripped from body and epigraph.
    assert "<sup>" not in book.chapters[0].intro[0].md
    war_defined_body = book.chapters[0].sections[0].body[0].md
    assert war_defined_body == "War is a clash of wills."
    # Back matter excluded entirely.
    all_body = " ".join(
        p.md for c in book.chapters for s in c.sections for p in s.body
    )
    assert "must be excluded" not in all_body


def test_chunk_builds_one_chapter_row_per_chapter_with_heading_first() -> None:
    _, book = _build_book()
    segments, chapters = build_segments_and_chapters(book, source_id="src-1", workspace_id="ws-1")

    assert len(chapters) == 2
    assert chapters[0]["level"] == 1
    assert chapters[0]["title"] == "Chapter 1 The Nature of War"
    # First segment of a chapter is its title heading.
    first_segment_id = chapters[0]["segment_ids"][0]
    first_segment = next(s for s in segments if s["id"] == first_segment_id)
    assert first_segment["kind"] == "heading"
    # Headings = 2 chapter titles + 3 section titles; rest are paragraphs.
    assert sum(1 for s in segments if s["kind"] == "heading") == 5
    # Segment text is plain (markdown emphasis flattened).
    assert all("*" not in s["text"] for s in segments)
    # Sections capture each level-2 heading plus its body segments.
    sections = chapters[0]["sections"]
    assert [s["title"] for s in sections] == ["WAR DEFINED", "FRICTION"]
    assert sections[0]["level"] == 2
    assert sections[0]["heading_segment_id"] == sections[0]["segment_ids"][0]
    assert all(sid in chapters[0]["segment_ids"] for sid in sections[0]["segment_ids"])


def test_epub_render_emits_three_types_and_preserves_emphasis() -> None:
    _, book = _build_book()
    chapters = book_to_epub_chapters(book)

    body = chapters[0]["xhtml_body"]
    assert body.startswith("<h1>Chapter 1 The Nature of War</h1>")
    assert "<h2>WAR DEFINED</h2>" in body
    assert "<p>War is a clash of wills.</p>" in body
    assert "<em>" in body  # epigraph italics preserved


def test_classify_joins_paragraph_split_only_by_page_boundary() -> None:
    pages = [
        _page(3, [
            _item("heading", "# Chapter 1", value="Chapter 1", level=1),
            _item("heading", "# The Nature of War", value="The Nature of War", level=1),
            _item("heading", "## WAR DEFINED", value="WAR DEFINED", level=2),
            _item(
                "text",
                "War is thus a process of continuous",
                value="War is thus a process of continuous",
            ),
        ]),
        _page(4, [
            _item(
                "text",
                "mutual adaptation, of give and take.",
                value="mutual adaptation, of give and take.",
            ),
        ]),
    ]
    elements, _ = normalize_structured_pages(pages)
    book = classify(elements)

    assert [p.md for p in book.chapters[0].sections[0].body] == [
        "War is thus a process of continuous mutual adaptation, of give and take."
    ]
    body = book_to_epub_chapters(book)[0]["xhtml_body"]
    assert (
        "<p>War is thus a process of continuous mutual adaptation, of give and take.</p>"
        in body
    )


@pytest.mark.parametrize(
    ("first_text", "second_page", "intervening_item"),
    [
        ("A complete paragraph.", 4, None),
        ("An incomplete paragraph", 5, None),
        ("An incomplete paragraph", 4, _item("heading", "## NEXT", value="NEXT", level=2)),
        ("An incomplete paragraph", 4, _item("list", "- A separate list item")),
    ],
)
def test_classify_does_not_join_across_true_structure_boundaries(
    first_text, second_page, intervening_item
) -> None:
    first_items = [
        _item("heading", "# Chapter 1", value="Chapter 1", level=1),
        _item("heading", "# Test", value="Test", level=1),
        _item("text", first_text, value=first_text),
    ]
    if intervening_item is not None:
        first_items.append(intervening_item)
    pages = [
        _page(3, first_items),
        _page(second_page, [_item("text", "Next text.", value="Next text.")]),
    ]
    elements, _ = normalize_structured_pages(pages)
    book = classify(elements)

    paragraphs = [
        paragraph.md
        for chapter in book.chapters
        for paragraph in chapter.intro
    ] + [
        paragraph.md
        for chapter in book.chapters
        for section in chapter.sections
        for paragraph in section.body
    ]
    assert paragraphs == [first_text, "Next text."]


def test_classify_joins_sentence_around_omitted_figure_and_caption() -> None:
    pages = [
        _page(28, [
            _item("heading", "# Chapter 2", value="Chapter 2", level=1),
            _item("heading", "# The Theory of War", value="The Theory of War", level=1),
            _item(
                "text",
                "The lowest level is the *tactical level*. Tactics refers to the "
                "concepts and methods used to accomplish a particular mission",
                value=(
                    "The lowest level is the tactical level. Tactics refers to the "
                    "concepts and methods used to accomplish a particular mission"
                ),
            ),
        ]),
        _page(29, [
            _item("image", "figure-1.png", value="figure-1.png"),
            _item(
                "text",
                "Figure 1. The Levels of War.",
                value="Figure 1. The Levels of War.",
            ),
            _item(
                "text",
                "in either combat or other military operations. In war, tactics "
                "focuses on the application of combat power.",
                value=(
                    "in either combat or other military operations. In war, tactics "
                    "focuses on the application of combat power."
                ),
            ),
        ]),
    ]
    elements, _ = normalize_structured_pages(pages)
    book = classify(elements)

    paragraphs = book.chapters[0].intro
    assert len(paragraphs) == 1
    assert "particular mission in either combat" in paragraphs[0].md
    assert "mission  in" not in paragraphs[0].md
    assert "Figure 1" not in paragraphs[0].md
    assert book.dropped_nontext == {"image": 1, "caption": 1}

    xhtml = book_to_epub_chapters(book)[0]["xhtml_body"]
    assert xhtml.count("<p>") == 1
    assert "particular mission in either combat" in xhtml
    assert "Figure 1" not in xhtml

    segments, _ = build_segments_and_chapters(book, source_id="src-1", workspace_id="ws-1")
    body_segments = [segment for segment in segments if segment["kind"] == "paragraph"]
    assert len(body_segments) == 1
    assert "particular mission in either combat" in body_segments[0]["text"]


def test_classify_keeps_epigraph_quotes_and_attributions_separate() -> None:
    pages = [
        _page(1, [
            _item("heading", "# Chapter 1", value="Chapter 1", level=1),
            _item("heading", "# The Nature of War", value="The Nature of War", level=1),
            _item(
                "text",
                '*"Everything in war is simple, but the simplest thing is difficult."*',
                value='"Everything in war is simple, but the simplest thing is difficult."',
            ),
            _item("text", "*—Carl von Clausewitz*", value="—Carl von Clausewitz"),
            _item(
                "text",
                '*"In war the chief incalculable is the human will."*',
                value='"In war the chief incalculable is the human will."',
            ),
            _item("text", "*—B. H. Liddell Hart*", value="—B. H. Liddell Hart"),
            _item(
                "text",
                "To understand the Marine Corps' philosophy of warfighting, we first "
                "need an appreciation for the nature of war itself.",
                value=(
                    "To understand the Marine Corps' philosophy of warfighting, we first "
                    "need an appreciation for the nature of war itself."
                ),
            ),
        ]),
    ]
    elements, _ = normalize_structured_pages(pages)
    book = classify(elements)

    intro = [paragraph.md for paragraph in book.chapters[0].intro]
    assert intro == [
        '*"Everything in war is simple, but the simplest thing is difficult."*',
        "*—Carl von Clausewitz*",
        '*"In war the chief incalculable is the human will."*',
        "*—B. H. Liddell Hart*",
        (
            "To understand the Marine Corps' philosophy of warfighting, we first "
            "need an appreciation for the nature of war itself."
        ),
    ]

    xhtml = book_to_epub_chapters(book)[0]["xhtml_body"]
    assert xhtml.count("<p>") == 5
    assert '<p><em>"Everything in war is simple, but the simplest thing is difficult."</em></p>' in xhtml
    assert "<p><em>—Carl von Clausewitz</em></p>" in xhtml
    assert "<p><em>—B. H. Liddell Hart</em></p>" in xhtml
    assert "Clausewitz</em> <em>\"" not in xhtml
    assert "Hart</em> <em>\"" not in xhtml


def test_classify_splits_quote_and_attribution_packed_in_one_item() -> None:
    pages = [
        _page(1, [
            _item("heading", "# Chapter 2", value="Chapter 2", level=1),
            _item("heading", "# The Theory of War", value="The Theory of War", level=1),
            _item(
                "text",
                '*"The political object is the goal."*\n—Carl von Clausewitz',
                value='"The political object is the goal."\n—Carl von Clausewitz',
            ),
        ]),
    ]
    elements, _ = normalize_structured_pages(pages)
    book = classify(elements)

    assert [paragraph.md for paragraph in book.chapters[0].intro] == [
        '*"The political object is the goal."*',
        "—Carl von Clausewitz",
    ]
    xhtml = book_to_epub_chapters(book)[0]["xhtml_body"]
    assert xhtml.count("<p>") == 2
    assert '<p><em>"The political object is the goal."</em></p>' in xhtml
    assert "<p>—Carl von Clausewitz</p>" in xhtml


def test_classify_drops_standalone_visual_captions_but_keeps_inline_references() -> None:
    pages = [
        _page(1, [
            _item("heading", "# Chapter 1", value="Chapter 1", level=1),
            _item("heading", "# Test", value="Test", level=1),
            _item(
                "text",
                "As shown in Figure 1, the levels interact.",
                value="As shown in Figure 1, the levels interact.",
            ),
            _item(
                "text",
                "Figure 1. The Levels of War.",
                value="Figure 1. The Levels of War.",
            ),
            _item("text", "Fig. IV: Another omitted visual.", value="Fig. IV: Another omitted visual."),
            _item(
                "text",
                "Figure 1 shows how the levels interact.",
                value="Figure 1 shows how the levels interact.",
            ),
        ]),
    ]
    elements, _ = normalize_structured_pages(pages)
    book = classify(elements)

    assert book.dropped_nontext == {"caption": 2}
    kept = [paragraph.md for paragraph in book.chapters[0].intro]
    assert kept == [
        "As shown in Figure 1, the levels interact.",
        "Figure 1 shows how the levels interact.",
    ]

    xhtml = book_to_epub_chapters(book)[0]["xhtml_body"]
    assert "The Levels of War" not in xhtml
    assert "Another omitted visual" not in xhtml
    assert "As shown in Figure 1" in xhtml

    segments, _ = build_segments_and_chapters(book, source_id="src-1", workspace_id="ws-1")
    segment_text = " ".join(segment["text"] for segment in segments)
    assert "The Levels of War" not in segment_text
    assert "Another omitted visual" not in segment_text
    assert "As shown in Figure 1" in segment_text


def test_visual_map_pages_do_not_pollute_structure_segments_or_epub() -> None:
    pages = [
        _page(1, [
            _item(
                "heading",
                "# Chapter 2",
                value="Chapter 2",
                level=1,
                bbox=_bbox("paragraph_title", 0.95),
            ),
            _item(
                "heading",
                "# Achieving a Decision",
                value="Achieving a Decision",
                level=1,
                bbox=_bbox("paragraph_title", 0.95),
            ),
            _item(
                "heading",
                "## ANZIO: A MODEL OF TACTICAL INDECISIVENESS",
                value="ANZIO: A MODEL OF TACTICAL INDECISIVENESS",
                level=2,
                bbox=_bbox("paragraph_title", 0.96),
            ),
            _item(
                "text",
                "The Allies sought a decision in Italy.",
                value="The Allies sought a decision in Italy.",
                bbox=_bbox("text", 0.99),
            ),
        ]),
        _page(2, [
            _item(
                "heading",
                "# Indecisiveness: Anzio, 1944. THE OPPORTUNITY",
                value="Indecisiveness: Anzio, 1944. THE OPPORTUNITY",
                level=1,
                bbox=_bbox("text", 0.70),
            ),
            _item(
                "text",
                "Map of Italy showing forces around Rome and Anzio.",
                value="Map of Italy showing forces around Rome and Anzio.",
                bbox=_bbox("text", 0.40, count=8),
            ),
        ]),
        _page(3, [
            _item(
                "text",
                "The Allies achieved surprise but failed to press their advantage.",
                value="The Allies achieved surprise but failed to press their advantage.",
                bbox=_bbox("text", 0.99),
            ),
        ]),
        _page(4, [
            _item(
                "heading",
                "# Indecisiveness: Anzio, 1944. OPPORTUNITY LOST",
                value="Indecisiveness: Anzio, 1944. OPPORTUNITY LOST",
                level=1,
                bbox=_bbox("text", 0.71),
            ),
            _item(
                "text",
                "Map of the Anzio beachhead showing Allied and enemy positions.",
                value="Map of the Anzio beachhead showing Allied and enemy positions.",
                bbox=_bbox("text", 0.40, count=8),
            ),
        ]),
        _page(5, [
            _item(
                "heading",
                "# CANNAE: A CLEAR TACTICAL DECISION ACHIEVED",
                value="CANNAE: A CLEAR TACTICAL DECISION ACHIEVED",
                level=1,
                bbox=_bbox("paragraph_title", 0.96),
            ),
            _item(
                "text",
                "Hannibal tailored his tactics to the opposing force.",
                value="Hannibal tailored his tactics to the opposing force.",
                bbox=_bbox("text", 0.99),
            ),
        ]),
        _page(6, [
            _item(
                "heading",
                "# Visualizing the Battle: Gettysburg, 1863",
                value="Visualizing the Battle: Gettysburg, 1863",
                level=1,
                bbox=_bbox("image", 0.73),
            ),
            _item(
                "text",
                "Map of Gettysburg showing troop positions and key terrain.",
                value="Map of Gettysburg showing troop positions and key terrain.",
                bbox=_bbox("image", 0.90),
            ),
        ]),
        _page(7, [
            _item(
                "heading",
                "# Acting Decisively",
                value="Acting Decisively",
                level=1,
                bbox=_bbox("paragraph_title", 0.96),
            ),
            _item(
                "text",
                "Leaders must exploit opportunities fully and aggressively.",
                value="Leaders must exploit opportunities fully and aggressively.",
                bbox=_bbox("text", 0.99),
            ),
        ]),
    ]
    elements, _ = normalize_structured_pages(pages)
    book = classify(elements)

    section_titles = [section.title for section in book.chapters[0].sections]
    assert section_titles == [
        "ANZIO: A MODEL OF TACTICAL INDECISIVENESS",
        "CANNAE: A CLEAR TACTICAL DECISION ACHIEVED",
        "Acting Decisively",
    ]
    assert book.dropped_nontext == {
        "visual_heading": 3,
        "visual_description": 3,
    }
    anzio_body = [paragraph.md for paragraph in book.chapters[0].sections[0].body]
    assert anzio_body == [
        "The Allies sought a decision in Italy.",
        "The Allies achieved surprise but failed to press their advantage.",
    ]

    segments, chapters = build_segments_and_chapters(
        book,
        source_id="src-1",
        workspace_id="ws-1",
    )
    output_text = " ".join(segment["text"] for segment in segments)
    assert [section["title"] for section in chapters[0]["sections"]] == section_titles
    assert "THE OPPORTUNITY" not in output_text
    assert "OPPORTUNITY LOST" not in output_text
    assert "Visualizing the Battle" not in output_text
    assert "Map of" not in output_text

    xhtml = book_to_epub_chapters(book)[0]["xhtml_body"]
    assert xhtml.count("<h2>") == 3
    assert "THE OPPORTUNITY" not in xhtml
    assert "Visualizing the Battle" not in xhtml
    assert "Map of" not in xhtml

    pdf = _pdf_with_pages([
        "Chapter 2 Achieving a Decision",
        "ANZIO A MODEL OF TACTICAL INDECISIVENESS",
        "CANNAE A CLEAR TACTICAL DECISION ACHIEVED",
        "Acting Decisively",
    ])
    assert validate_against_pdf(book, pdf)["valid"] is True


def test_visual_cleanup_keeps_high_confidence_prose_on_chart_page() -> None:
    pages = [
        _page(1, [
            _item("heading", "# Chapter 1", value="Chapter 1"),
            _item("heading", "# Cooperation", value="Cooperation"),
            _item("code", "graph TD", value="graph TD", bbox=_bbox("chart", 0.95)),
            _item("text", "COMMANDER", value="COMMANDER"),
            _item(
                "text",
                "This body of thought helps form tacticians through education.",
                value="This body of thought helps form tacticians through education.",
                bbox=[
                    {"label": "chart", "confidence": 0.99},
                    {"label": "text", "confidence": 0.99},
                ],
            ),
        ]),
    ]

    elements, _ = normalize_structured_pages(pages)
    book = classify(elements)

    assert [paragraph.md for paragraph in book.chapters[0].intro] == [
        "This body of thought helps form tacticians through education."
    ]
    assert book.dropped_nontext == {"code": 1, "visual_description": 1}


def test_book_round_trips_through_dict() -> None:
    _, book = _build_book()
    rebuilt = book_from_dict(book.to_dict())

    assert [c.title for c in rebuilt.chapters] == [c.title for c in book.chapters]
    assert rebuilt.body_paragraph_count() == book.body_paragraph_count()


def test_content_image_becomes_a_note_and_plate_text_is_dropped() -> None:
    before = (
        "The form of the commission document remains much like that granted "
        "by the Continental Congress to officers of the Continental Army "
        'during the American Revolution. The commanders must show "honor and virtue '
        'to their officers and men."'
    )
    before_md = before + "<sup>5</sup>"
    after = (
        "The Armed Forces of the United States depend for their success "
        "on a web of trust."
    )
    pages = [
        _page(1, [
            _item("heading", "# Chapter 1", value="Chapter 1", level=1),
            _item("text", before_md, value=before_md),
            _item("text", "icon: decorative flourish", value="icon: decorative flourish"),
            _item(
                "text",
                "photo: historical commission document",
                value="photo: historical commission document",
            ),
            _item("text", "IN CONGRESS.", value="IN CONGRESS."),
            _item(
                "text",
                "The DELEGATES of the UNITED STATES of New-Hampshire, Massachusetts-Bay, "
                "Rhode-Island, and Georgia, TO",
                value="The DELEGATES of the UNITED STATES of New-Hampshire",
            ),
            _item(
                "text",
                "WE, reposing especial Trust and Confidence in your Patriotism, Valour, "
                "Conduct and Fidelity, DO, by these Presents, constitute and appoint you to be",
                value="WE, reposing especial Trust and Confidence",
            ),
            _item("text", "Henry Laurens, PRESIDENT.", value="Henry Laurens, PRESIDENT."),
            _item("text", after, value=after),
        ]),
    ]
    elements, _ = normalize_structured_pages(pages)
    pdf_pages = pdf_text_layer(_pdf_with_pages([f"{before}\n{after}"]))
    book = classify(elements, pdf_pages=pdf_pages)

    body = [paragraph.md for paragraph in book.chapters[0].intro]
    assert body == [
        before,
        "An image is not included here. It shows a historical commission document.",
        after,
    ]
    joined = " ".join(body)
    assert "IN CONGRESS" not in joined
    assert "DELEGATES" not in joined
    assert "Henry Laurens" not in joined
    assert "flourish" not in joined


def test_image_note_follows_a_sentence_the_picture_interrupted() -> None:
    pages = [
        _page(1, [
            _item("heading", "# Chapter 1", value="Chapter 1", level=1),
            _item(
                "text",
                "The Allies sought a decision",
                value="The Allies sought a decision",
            ),
            _item("text", "image: map of the landing", value="image: map of the landing"),
            _item(
                "text",
                "Map of Italy showing forces around Rome and Anzio during the campaign.",
                value="Map of Italy showing forces around Rome and Anzio during the campaign.",
            ),
            _item(
                "text",
                "in Italy before the enemy could react.",
                value="in Italy before the enemy could react.",
            ),
        ]),
    ]
    elements, _ = normalize_structured_pages(pages)
    pdf_pages = pdf_text_layer(_pdf_with_pages([
        "The Allies sought a decision in Italy before the enemy could react. "
        "The landing remained the subject of the chapter.",
    ]))
    book = classify(elements, pdf_pages=pdf_pages)

    assert [paragraph.md for paragraph in book.chapters[0].intro] == [
        "The Allies sought a decision in Italy before the enemy could react.",
        "An image is not included here. It shows a map of the landing.",
    ]


def test_image_note_is_the_same_plain_sentence_in_the_ebook_and_narration() -> None:
    pages = [
        _page(1, [
            _item("heading", "# Chapter 1", value="Chapter 1", level=1),
            _item(
                "text",
                "The paragraph before the picture is long enough to mark a text layer.",
                value="The paragraph before the picture is long enough to mark a text layer.",
            ),
            _item(
                "text",
                "photo: historical *commission* document <sup>2</sup>, 1777",
                value="photo: historical *commission* document <sup>2</sup>, 1777",
            ),
            _item(
                "text",
                "The paragraph after the picture is also real prose in the text layer.",
                value="The paragraph after the picture is also real prose in the text layer.",
            ),
        ]),
    ]
    elements, _ = normalize_structured_pages(pages)
    pdf_pages = pdf_text_layer(_pdf_with_pages([
        "The paragraph before the picture is long enough to mark a text layer. "
        "The paragraph after the picture is also real prose in the text layer.",
    ]))
    book = classify(elements, pdf_pages=pdf_pages)
    note = "An image is not included here. It shows a historical commission document."
    assert [paragraph.md for paragraph in book.chapters[0].intro][1] == note

    xhtml = book_to_epub_chapters(book)[0]["xhtml_body"]
    assert f"<p>{note}</p>" in xhtml
    assert "<em>" not in xhtml
    assert "<sup>" not in xhtml

    assert flatten_markdown(note) == note
    assert display_markdown(note) is None
    segments, _chapters = build_segments_and_chapters(
        book, source_id="src", workspace_id="ws"
    )
    spoken = [row for row in segments if row["text"] == note]
    assert len(spoken) == 1
    assert spoken[0]["kind"] == "paragraph"
    assert spoken[0]["md"] is None

    clips, oversize, empty = pack_chapter_clips(spoken, 500)
    assert oversize == []
    assert empty == 0
    assert clips == [spoken]


def test_scanned_page_keeps_image_transcription() -> None:
    pages = [
        _page(1, [
            _item("heading", "# Chapter 1", value="Chapter 1", level=1),
            _item(
                "text",
                "photo: historical commission document",
                value="photo: historical commission document",
            ),
            _item("text", "IN CONGRESS.", value="IN CONGRESS."),
            _item(
                "text",
                "The DELEGATES of the UNITED STATES of New-Hampshire and Georgia, TO",
                value="The DELEGATES of the UNITED STATES of New-Hampshire and Georgia, TO",
            ),
        ]),
    ]
    elements, _ = normalize_structured_pages(pages)
    book = classify(elements, pdf_pages=pdf_text_layer(_pdf_with_pages(["2"])))

    body = [paragraph.md for paragraph in book.chapters[0].intro]
    assert "An image is not included here" not in " ".join(body)
    assert any("DELEGATES" in paragraph for paragraph in body)


def _pdf_with_pages(page_texts: list[str]) -> bytes:
    doc = fitz.open()
    for text in page_texts:
        page = doc.new_page()
        page.insert_text((72, 72), text, fontsize=12)
    data = doc.tobytes()
    doc.close()
    return data


def test_validate_compares_titles_without_sup_tags() -> None:
    assert _norm("Leaders and Followers<sup>19</sup>") == "leaders and followers"


def test_validate_passes_when_titles_present_in_pdf() -> None:
    _, book = _build_book()
    pdf = _pdf_with_pages([
        "Chapter 1 The Nature of War WAR DEFINED FRICTION",
        "Chapter 2 The Theory of War CONCLUSION",
    ])
    # Page attribution in the synthetic book (pages 3-4) won't line up with the
    # 2-page PDF, but the titles are present, so validate should pass with warnings.
    report = validate_against_pdf(book, pdf)
    assert report["valid"] is True


def test_validate_raises_when_front_matter_leaks() -> None:
    _, book = _build_book()
    book.chapters[0].title = "FOREWORD"  # simulate a missed boundary
    pdf = _pdf_with_pages(["FOREWORD", "Chapter 2 The Theory of War"])

    with pytest.raises(StructureValidationError, match="Front/back-matter heading leaked"):
        validate_against_pdf(book, pdf)


def test_validate_keeps_pdf_spelling_when_a_long_heading_has_one_typo() -> None:
    title = (
        "The U.S. Navy, by Admiral Gary Roughhead, USN (Ret.), "
        "Chief of Naval Operations, 2007–2011"
    )
    book = Book(chapters=[
        Chapter(
            title="CHAPTER NINE Service Identity and Joint Warfighting",
            page=1,
            intro=[Paragraph(md="Service identity shapes how officers fight.", page=1)] * 3,
            sections=[Section(title=title, page=1, body=[])],
        ),
    ])
    pdf = _pdf_with_pages([
        "CHAPTER NINE Service Identity and Joint Warfighting\n"
        "The U.S. Navy, by Admiral Gary Roughead, USN (Ret.),\n"
        "Chief of Naval Operations, 2007–2011",
    ])

    report = validate_against_pdf(book, pdf)

    assert report["valid"] is True
    assert book.chapters[0].sections[0].title == (
        "The U.S. Navy, by Admiral Gary Roughead, USN (Ret.), "
        "Chief of Naval Operations, 2007–2011"
    )
    assert report["title_corrections"] == [{
        "kind": "section",
        "page": 1,
        "from": title,
        "to": book.chapters[0].sections[0].title,
    }]


def test_validate_rejects_a_changed_chapter_number() -> None:
    book = Book(chapters=[
        Chapter(
            title="Chapter 1 The Nature of War",
            page=1,
            intro=[Paragraph(md="War is a violent clash of interests.", page=1)] * 3,
        ),
    ])
    pdf = _pdf_with_pages(["Chapter 2 The Nature of War"])

    with pytest.raises(StructureValidationError, match="Chapter 1 The Nature of War"):
        validate_against_pdf(book, pdf)


def test_validate_still_raises_for_unsupported_section_title() -> None:
    _, book = _build_book()
    book.chapters[0].sections[0].title = "INVENTED SECTION"
    pdf = _pdf_with_pages([
        "Chapter 1 The Nature of War FRICTION",
        "Chapter 2 The Theory of War CONCLUSION",
    ])

    with pytest.raises(StructureValidationError, match="INVENTED SECTION.*in the PDF at all"):
        validate_against_pdf(book, pdf)
