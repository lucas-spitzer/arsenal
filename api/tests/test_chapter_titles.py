from app.intellex.structuring.chapter_titles import display_chapter_title


def test_spelled_out_chapter_becomes_a_numbered_title() -> None:
    assert (
        display_chapter_title("CHAPTER ONE The Commission and the Oath")
        == "Chapter 1: The Commission and the Oath"
    )


def test_doctrine_space_title_gains_a_colon() -> None:
    assert display_chapter_title("Chapter 1 The Nature of War") == "Chapter 1: The Nature of War"


def test_existing_colon_title_stays_put() -> None:
    assert (
        display_chapter_title("Chapter 2: The Theory of War")
        == "Chapter 2: The Theory of War"
    )


def test_roman_and_compound_word_numbers() -> None:
    assert display_chapter_title("CHAPTER IV The Officer") == "Chapter 4: The Officer"
    assert display_chapter_title("Chapter twenty-one The Last") == "Chapter 21: The Last"


def test_a_title_that_is_not_a_chapter_label_is_unchanged() -> None:
    assert display_chapter_title("WAR DEFINED") == "WAR DEFINED"
