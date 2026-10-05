from app.pipeline import SUPPORTED_TARGET_ARTIFACTS, build_pipeline


def test_supported_target_artifacts_include_electronic_book() -> None:
    assert "electronic_book" in SUPPORTED_TARGET_ARTIFACTS


def test_removed_narration_artifacts_are_no_longer_supported() -> None:
    assert "speechify_script" not in SUPPORTED_TARGET_ARTIFACTS
    assert "speechify_audio" not in SUPPORTED_TARGET_ARTIFACTS
    assert "elevenlabs_audio" not in SUPPORTED_TARGET_ARTIFACTS
    assert "eleven_reader_script" not in SUPPORTED_TARGET_ARTIFACTS


def test_build_pipeline_appends_electronic_book_step() -> None:
    pipeline = build_pipeline(["electronic_book"])

    step_names = [step["step"] for step in pipeline]

    assert step_names[-2:] == ["web-enrichment", "create-ebook"]


def test_narration_pipeline_does_not_include_web_enrichment() -> None:
    step_names = [step["step"] for step in build_pipeline(["narration_audio"])]

    assert "web-enrichment" not in step_names
    assert step_names[-1] == "generate-narration"
