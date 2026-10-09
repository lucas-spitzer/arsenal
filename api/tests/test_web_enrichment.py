from app.intellex.source_readiness import source_web_enrichment_complete
from app.intellex.stages.models import WebEnrichmentOutput, WebSource
from app.intellex.stages.promotion import merge_web_enrichment_into_source_metadata
from app.intellex.stages.web_enrichment import (
    WebEnrichmentStage,
    is_restricted_distribution,
)
from app.services.llm.base import LLMCompletionResult


class FakeWebSearchClient:
    provider = "anthropic"
    model = "claude-haiku-5-5"

    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.calls = 0

    def complete_json(self, *, system_prompt: str, user_prompt: str, model: str | None = None):
        raise AssertionError("web enrichment must use the web-search completion")

    def complete_json_with_web_search(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        model: str | None = None,
        max_searches: int = 5,
    ) -> LLMCompletionResult:
        self.calls += 1
        self.last_user_prompt = user_prompt

        return LLMCompletionResult(
            content=self.payload,
            model=self.model,
            provider=self.provider,
            token_usage={
                "input_tokens": 500,
                "output_tokens": 200,
                "total_tokens": 700,
                "web_search_requests": 3,
            },
        )


class NoSearchClient:
    provider = "openai"
    model = "gpt-5.4-mini"

    def complete_json(self, *, system_prompt: str, user_prompt: str, model: str | None = None):
        raise AssertionError("should not be called")


RESEARCH = {
    "document_type": "military_doctrine",
    "title": "Warfighting",
    "identifier": "MCDP 1",
    "issuing_authority": "US Marine Corps",
    "authors": [],
    "version": "1997",
    "publication_date_in_document": "1997-06-20",
    "publication_date_public": None,
    "source_url": None,
    "distribution_line": "Approved for public release; distribution is unlimited.",
    "provenance": {"title": "document"},
    "confidence": {"title": 0.98},
    "researched_at": "2026-07-01T00:00:00+00:00",
}


def test_is_restricted_distribution() -> None:
    assert not is_restricted_distribution(None)
    assert not is_restricted_distribution(
        "Approved for public release; distribution is unlimited.",
    )
    assert is_restricted_distribution("Distribution Statement C: US Government agencies only.")
    assert is_restricted_distribution("FOUO")
    assert is_restricted_distribution("Controlled Unclassified Information (CUI)")
    assert is_restricted_distribution("Not for public release.")


def test_stage_skips_restricted_documents_without_llm_call() -> None:
    stage = WebEnrichmentStage(llm_client=NoSearchClient(), max_searches=3)

    output, execution = stage.run(
        filename="restricted.pdf",
        research={**RESEARCH, "distribution_line": "Distribution Statement D."},
    )

    assert output.searched is False
    assert output.skip_reason is not None
    assert output.status == "unknown"
    assert execution["token_usage"] == {}


def test_stage_skips_when_no_usable_title() -> None:
    stage = WebEnrichmentStage(llm_client=NoSearchClient(), max_searches=3)

    output, _ = stage.run(
        filename="scan.pdf",
        research={**RESEARCH, "title": "Untitled document"},
    )

    assert output.searched is False


def test_stage_errors_when_client_lacks_web_search() -> None:
    stage = WebEnrichmentStage(llm_client=NoSearchClient(), max_searches=3)

    try:
        stage.run(filename="mcdp1.pdf", research=RESEARCH)
    except RuntimeError as exc:
        assert "web search" in str(exc)
    else:
        raise AssertionError("expected RuntimeError for client without web search")


def test_stage_enriches_profile_via_web_search() -> None:
    client = FakeWebSearchClient(
        {
            "status": "current",
            "superseded_by": None,
            "canonical_url": "https://www.marines.mil/portals/1/publications/mcdp%201%20warfighting.pdf",
            "publication_date_public": "1997-06-20",
            "publisher_context": "The US Marine Corps is the issuing authority for Marine Corps doctrine.",
            "public_abstract": None,
            "confirmations": ["title", "identifier"],
            "corrections": {},
            "related_documents": [
                {
                    "title": "MCDP 1-1 Strategy",
                    "identifier": "MCDP 1-1",
                    "url": "https://www.marines.mil/mcdp1-1",
                    "relation": "companion",
                },
                {"title": "", "relation": "companion"},
            ],
            "web_sources": [
                {
                    "url": "https://www.marines.mil/portals/1/publications/mcdp%201%20warfighting.pdf",
                    "title": "MCDP 1 Warfighting",
                    "publisher": "US Marine Corps",
                    "supports": ["canonical_url", "publication_date_public", "status"],
                },
                {"title": "no url, dropped"},
            ],
            "confidence": {"status": 0.9, "canonical_url": 0.95},
            # The model must not decide whether a search ran.
            "searched": False,
            "skip_reason": "should be ignored",
        },
    )
    stage = WebEnrichmentStage(llm_client=client, max_searches=3)

    output, execution = stage.run(filename="mcdp1.pdf", research=RESEARCH)

    assert client.calls == 1
    assert "MCDP 1" in client.last_user_prompt
    assert output.searched is True
    assert output.skip_reason is None
    assert output.status == "current"
    assert output.canonical_url.startswith("https://www.marines.mil")
    assert output.confirmations == ["title", "identifier"]
    assert len(output.related_documents) == 1
    assert output.related_documents[0].relation == "companion"
    assert len(output.web_sources) == 1
    assert execution["search_count"] == 3
    assert execution["provider"] == "anthropic"
    assert execution["token_usage"]["total_tokens"] == 700


def test_output_coerces_messy_values() -> None:
    output = WebEnrichmentOutput.model_validate(
        {
            "status": "definitely current",
            "confirmations": "title",
            "corrections": {"version": None, "identifier": "MCDP-1"},
            "related_documents": "not a list",
            "web_sources": {"url": "not a list"},
            "confidence": {"status": "high", "canonical_url": "0.5"},
        },
    )

    assert output.status == "unknown"
    assert output.confirmations == ["title"]
    assert output.corrections == {"identifier": "MCDP-1"}
    assert output.related_documents == []
    assert output.web_sources == []
    assert output.confidence == {"canonical_url": 0.5}


def test_merge_fills_nulls_and_records_conflicts() -> None:
    enrichment = WebEnrichmentOutput(
        status="superseded",
        superseded_by="MCDP 1 (2018 edition)",
        canonical_url="https://www.marines.mil/mcdp1",
        publication_date_public="1997-06-20",
        corrections={"version": "1997 (Change 1)"},
        web_sources=[
            WebSource(
                url="https://www.marines.mil/mcdp1",
                title="MCDP 1 Warfighting",
                supports=["canonical_url", "status"],
            ),
        ],
        confidence={"canonical_url": 0.95, "publication_date_public": 0.9},
    )

    metadata = merge_web_enrichment_into_source_metadata(
        {"parse": {"page_count": 96}, "research": dict(RESEARCH)},
        enrichment,
        enriched_at="2026-07-06T00:00:00+00:00",
    )

    research = metadata["research"]
    # Web fills nulls with provenance + confidence.
    assert research["publication_date_public"] == "1997-06-20"
    assert research["source_url"] == "https://www.marines.mil/mcdp1"
    assert research["provenance"]["source_url"] == "web"
    assert research["provenance"]["publication_date_public"] == "web"
    assert research["confidence"]["source_url"] == 0.95
    # Document-extracted values untouched.
    assert research["title"] == "Warfighting"
    assert research["version"] == "1997"
    # Correction recorded as a conflict, not applied.
    conflicts = metadata["web_enrichment"]["conflicts"]
    assert {"field": "version", "document_value": "1997", "web_value": "1997 (Change 1)"} in conflicts
    # Enrichment block persisted with completion timestamp.
    assert metadata["web_enrichment"]["enriched_at"] == "2026-07-06T00:00:00+00:00"
    assert metadata["web_enrichment"]["status"] == "superseded"
    assert metadata["parse"]["page_count"] == 96
    # Sources copied onto the research block.
    assert research["web_sources"][0]["url"] == "https://www.marines.mil/mcdp1"


def test_merge_document_value_wins_on_conflict() -> None:
    enrichment = WebEnrichmentOutput(
        publication_date_public="1997-07-01",
        web_sources=[WebSource(url="https://example.mil/record")],
    )

    metadata = merge_web_enrichment_into_source_metadata(
        {"research": {**RESEARCH, "publication_date_public": "1997-06-20"}},
        enrichment,
        enriched_at="2026-07-06T00:00:00+00:00",
    )

    assert metadata["research"]["publication_date_public"] == "1997-06-20"
    assert metadata["web_enrichment"]["conflicts"] == [
        {
            "field": "publication_date_public",
            "document_value": "1997-06-20",
            "web_value": "1997-07-01",
        },
    ]


def test_web_enrichment_readiness() -> None:
    assert not source_web_enrichment_complete({"source_metadata": {}})
    assert not source_web_enrichment_complete(
        {"source_metadata": {"web_enrichment": {}}},
    )
    assert source_web_enrichment_complete(
        {
            "source_metadata": {
                "web_enrichment": {"enriched_at": "2026-07-06T00:00:00+00:00"},
            },
        },
    )
