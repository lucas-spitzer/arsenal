from typing import Any

from app.services.supabase_rest import SupabaseRestClient

LESSONS = "lessons"
OBJECTIVES = "lesson_objectives"
RESOURCES = "lesson_resources"


class LessonRepository:
    def __init__(self, db: SupabaseRestClient) -> None:
        self.db = db

    async def list_with_children(self, workspace_id: str) -> list[dict[str, Any]]:
        """Every class in the workspace with its ordered ELOs and resources nested."""
        scope = {"workspace_id": f"eq.{workspace_id}"}
        lessons = await self.db.select_many(LESSONS, filters=scope, order="sort_order.asc,title.asc")
        objectives = await self.db.select_many(OBJECTIVES, filters=scope, order="position.asc")
        resources = await self.db.select_many(
            RESOURCES, filters=scope, order="position.asc,created_at.asc"
        )
        return group_lessons(lessons, objectives, resources)

    async def get_with_children(self, lesson_id: str, workspace_id: str) -> dict[str, Any] | None:
        lesson = await self.get(lesson_id, workspace_id)
        if not lesson:
            return None
        objectives = await self.list_objectives(lesson_id)
        resources = await self.list_resources(lesson_id)
        return group_lessons([lesson], objectives, resources)[0]

    async def get(self, lesson_id: str, workspace_id: str) -> dict[str, Any] | None:
        return await self.db.select_one(
            LESSONS,
            filters={"id": f"eq.{lesson_id}", "workspace_id": f"eq.{workspace_id}"},
        )

    async def next_sort_order(self, workspace_id: str) -> int:
        rows = await self.db.select_many(
            LESSONS,
            filters={"workspace_id": f"eq.{workspace_id}"},
            columns="sort_order",
            order="sort_order.desc",
            limit=1,
        )
        return (int(rows[0]["sort_order"]) + 1) if rows else 1

    async def create(self, payload: dict[str, Any]) -> dict[str, Any]:
        rows = await self.db.insert(LESSONS, payload)
        return rows[0]

    async def update(
        self, lesson_id: str, workspace_id: str, payload: dict[str, Any]
    ) -> dict[str, Any] | None:
        rows = await self.db.update(
            LESSONS,
            filters={"id": f"eq.{lesson_id}", "workspace_id": f"eq.{workspace_id}"},
            payload=payload,
        )
        return rows[0] if rows else None

    async def delete(self, lesson_id: str, workspace_id: str) -> None:
        await self.db.delete(
            LESSONS,
            filters={"id": f"eq.{lesson_id}", "workspace_id": f"eq.{workspace_id}"},
        )

    async def list_objectives(self, lesson_id: str) -> list[dict[str, Any]]:
        return await self.db.select_many(
            OBJECTIVES, filters={"lesson_id": f"eq.{lesson_id}"}, order="position.asc"
        )

    async def replace_objectives(
        self, lesson_id: str, workspace_id: str, objectives: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        await self.db.delete(OBJECTIVES, filters={"lesson_id": f"eq.{lesson_id}"})
        if not objectives:
            return []
        rows = [
            {**objective, "lesson_id": lesson_id, "workspace_id": workspace_id, "position": index}
            for index, objective in enumerate(objectives, start=1)
        ]
        return await self.db.insert(OBJECTIVES, rows)

    async def list_resources(self, lesson_id: str) -> list[dict[str, Any]]:
        return await self.db.select_many(
            RESOURCES,
            filters={"lesson_id": f"eq.{lesson_id}"},
            order="position.asc,created_at.asc",
        )

    async def list_file_resources(self, workspace_id: str) -> list[dict[str, Any]]:
        return await self.db.select_many(
            RESOURCES,
            filters={"workspace_id": f"eq.{workspace_id}", "kind": "eq.file"},
        )

    async def get_resource(
        self, resource_id: str, lesson_id: str, workspace_id: str
    ) -> dict[str, Any] | None:
        return await self.db.select_one(
            RESOURCES,
            filters={
                "id": f"eq.{resource_id}",
                "lesson_id": f"eq.{lesson_id}",
                "workspace_id": f"eq.{workspace_id}",
            },
        )

    async def next_resource_position(self, lesson_id: str) -> int:
        rows = await self.db.select_many(
            RESOURCES,
            filters={"lesson_id": f"eq.{lesson_id}"},
            columns="position",
            order="position.desc",
            limit=1,
        )
        return (int(rows[0]["position"]) + 1) if rows else 0

    async def create_resource(self, payload: dict[str, Any]) -> dict[str, Any]:
        rows = await self.db.insert(RESOURCES, payload)
        return rows[0]

    async def update_resource(
        self, resource_id: str, workspace_id: str, payload: dict[str, Any]
    ) -> dict[str, Any] | None:
        rows = await self.db.update(
            RESOURCES,
            filters={"id": f"eq.{resource_id}", "workspace_id": f"eq.{workspace_id}"},
            payload=payload,
        )
        return rows[0] if rows else None

    async def delete_resource(self, resource_id: str, workspace_id: str) -> None:
        await self.db.delete(
            RESOURCES,
            filters={"id": f"eq.{resource_id}", "workspace_id": f"eq.{workspace_id}"},
        )


def group_lessons(
    lessons: list[dict[str, Any]],
    objectives: list[dict[str, Any]],
    resources: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    by_lesson: dict[str, dict[str, Any]] = {
        str(lesson["id"]): {**lesson, "objectives": [], "resources": []} for lesson in lessons
    }
    for objective in objectives:
        lesson = by_lesson.get(str(objective["lesson_id"]))
        if lesson is not None:
            lesson["objectives"].append(objective)
    for resource in resources:
        lesson = by_lesson.get(str(resource["lesson_id"]))
        if lesson is not None:
            lesson["resources"].append(resource)
    return list(by_lesson.values())
