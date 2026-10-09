"""Which wiki entries become flashcards, and which uploaded files attach."""

from __future__ import annotations

from typing import Any

from app.knowledge.visuals import cited_wiki_id, storage_path_of


def flashcard_enabled_by_default(entry: dict[str, Any]) -> bool:
    kind = str(entry.get("entry_kind") or "")
    importance = str(entry.get("importance") or "")
    return kind in {"term", "list"} and importance in {"essential", "supporting"}


def flashcard_plan_rows(
    *,
    project_id: str,
    workspace_id: str,
    entries: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for entry in entries:
        rows.append(
            {
                "knowledge_project_id": project_id,
                "workspace_id": workspace_id,
                "wiki_entry_id": str(entry["id"]),
                "item_type": "flashcard",
                "enabled": flashcard_enabled_by_default(entry),
                "layout": "label_description",
                "visual": None,
            },
        )
    return rows


def study_wiki_ids(plans: list[dict[str, Any]], entries: list[dict[str, Any]]) -> set[str]:
    """Enabled flashcard entries, plus the terms named by an enabled list.

    Checking a list in Forge Knowledge drafts that list and its components.
    Questions and scenarios use the same set.
    """
    enabled = enabled_flashcard_wiki_ids(plans)
    by_id = {str(entry["id"]): entry for entry in entries}
    by_label: dict[str, str] = {}
    for entry in entries:
        label = str(entry.get("preferred_label") or "").strip().casefold()
        if label:
            by_label[label] = str(entry["id"])
        for alias in entry.get("aliases") or []:
            alias_label = str(alias).strip().casefold()
            if alias_label:
                by_label.setdefault(alias_label, str(entry["id"]))

    expanded = set(enabled)
    for wiki_id in enabled:
        entry = by_id.get(wiki_id)
        if not entry or str(entry.get("entry_kind") or "") != "list":
            continue
        for item in entry.get("items") or []:
            if not isinstance(item, dict):
                continue
            match = by_label.get(str(item.get("name") or "").strip().casefold())
            if match and match != wiki_id:
                expanded.add(match)
    return expanded


def enabled_flashcard_wiki_ids(plans: list[dict[str, Any]]) -> set[str]:
    return {
        str(plan["wiki_entry_id"])
        for plan in plans
        if plan.get("item_type") == "flashcard" and plan.get("enabled") and plan.get("wiki_entry_id")
    }


def project_wiki_ids(plans: list[dict[str, Any]]) -> set[str]:
    return {str(plan["wiki_entry_id"]) for plan in plans if plan.get("wiki_entry_id")}


def plans_by_wiki_id(plans: list[dict[str, Any]], item_type: str) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for plan in plans:
        if plan.get("item_type") != item_type or not plan.get("wiki_entry_id"):
            continue
        indexed[str(plan["wiki_entry_id"])] = plan
    return indexed


def visual_updates_for_rows(
    plans: list[dict[str, Any]],
    rows: list[dict[str, Any]],
    *,
    item_type: str,
) -> list[tuple[str, str, dict[str, Any]]]:
    """Match drafted rows to plans that already have an uploaded file.

    Returns (assessment_id, plan_id, visual). Plans without a file are skipped.
    """
    by_wiki = plans_by_wiki_id(plans, item_type)
    updates: list[tuple[str, str, dict[str, Any]]] = []
    for row in rows:
        wiki_id = cited_wiki_id(row.get("citations"))
        plan = by_wiki.get(wiki_id or "")
        if not plan:
            continue
        visual = plan.get("visual")
        if not storage_path_of(visual if isinstance(visual, dict) else None):
            continue
        updates.append((str(row["id"]), str(plan["id"]), visual))
    return updates


def item_plan_rows(
    *,
    project_id: str,
    workspace_id: str,
    rows: list[dict[str, Any]],
    item_type: str,
) -> list[dict[str, Any]]:
    planned: list[dict[str, Any]] = []
    for row in rows:
        planned.append(
            {
                "knowledge_project_id": project_id,
                "workspace_id": workspace_id,
                "wiki_entry_id": cited_wiki_id(row.get("citations")),
                "item_type": item_type,
                "enabled": True,
                "assessment_id": str(row["id"]),
                "visual": None,
            },
        )
    return planned
