from __future__ import annotations

import logging

from app.config import Settings
from app.services.queue import enqueue_lesson_objectives_index, enqueue_lesson_resource_index

logger = logging.getLogger(__name__)


class LessonIndexQueue:
    """Queues Discussions indexing for lesson files and ELOs.

    Saving a class or uploading a file must not fail when Redis is down: the
    row keeps index_status 'pending' and an admin can re-index later.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def resource(self, resource_id: str) -> bool:
        try:
            enqueue_lesson_resource_index(self.settings, resource_id)
        except Exception:  # noqa: BLE001 - queue outage must not fail the upload
            logger.warning("Could not queue lesson file %s for indexing.", resource_id, exc_info=True)
            return False
        return True

    def objectives(self, lesson_id: str) -> bool:
        try:
            enqueue_lesson_objectives_index(self.settings, lesson_id)
        except Exception:  # noqa: BLE001 - queue outage must not fail the save
            logger.warning("Could not queue ELOs of lesson %s for indexing.", lesson_id, exc_info=True)
            return False
        return True
