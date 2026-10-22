from pydantic import BaseModel

from app.models.artifact import ArtifactResponse
from app.models.assessment import FlashcardResponse, QuizResponse, ScenarioResponse
from app.models.knowledge import KnowledgeRunTitle
from app.models.source import SourceResponse
from app.models.wiki_entry import WikiEntryResponse


class LibraryCatalogResponse(BaseModel):
    sources: list[SourceResponse]
    artifacts: list[ArtifactResponse]
    wiki_entries: list[WikiEntryResponse]
    flashcards: list[FlashcardResponse]
    quizzes: list[QuizResponse]
    scenarios: list[ScenarioResponse]
    knowledge_titles: list[KnowledgeRunTitle]
