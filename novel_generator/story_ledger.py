from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _trim_text(value: str, limit: int) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return f"{text[:limit].rstrip()}…"


def _read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8").strip()


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _build_chapter_summary(chapter_text: str, max_length: int = 240) -> str:
    text = str(chapter_text or "").strip()
    if not text:
        return ""

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if lines and lines[0].startswith("第") and "章" in lines[0]:
        lines = lines[1:]
    content = " ".join(lines).strip()
    return _trim_text(content, max_length)


@dataclass(frozen=True)
class PromptMemoryContext:
    global_summary_text: str = ""
    character_state_text: str = ""
    volume_summary_text: str = ""
    hook_summary_text: str = ""
    thread_summary_text: str = ""
    memory_guidance: str = ""


class StoryLedger:
    SCHEMA_VERSION = 1

    def __init__(self, project_root: str, chapters_per_volume: int = 50) -> None:
        self.project_root = Path(project_root)
        self.chapters_per_volume = max(1, int(chapters_per_volume or 50))
        self.story_ledger_dir = self.project_root / "story_ledger"
        self.chapters_dir = self.story_ledger_dir / "chapters"
        self.volumes_dir = self.story_ledger_dir / "volumes"
        self.manifest_path = self.story_ledger_dir / "manifest.json"
        self.legacy_views_path = self.story_ledger_dir / "legacy_views.json"

    def ensure_initialized(self) -> None:
        self.story_ledger_dir.mkdir(parents=True, exist_ok=True)
        self.chapters_dir.mkdir(parents=True, exist_ok=True)
        self.volumes_dir.mkdir(parents=True, exist_ok=True)

        manifest = _read_json(self.manifest_path, {})
        if not manifest:
            manifest = {
                "schema_version": self.SCHEMA_VERSION,
                "chapters_per_volume": self.chapters_per_volume,
                "last_recorded_chapter": 0,
                "created_at": _utc_now(),
                "updated_at": _utc_now(),
            }
        else:
            manifest["schema_version"] = self.SCHEMA_VERSION
            manifest["chapters_per_volume"] = self.chapters_per_volume
            manifest.setdefault("created_at", _utc_now())
            manifest["updated_at"] = _utc_now()
        _write_json(self.manifest_path, manifest)

        if not self.legacy_views_path.exists():
            _write_json(self.legacy_views_path, self._bootstrap_legacy_views())
            self.export_legacy_views()

    def _bootstrap_legacy_views(self) -> dict[str, Any]:
        return {
            "global_summary_text": _read_text(self.project_root / "global_summary.txt"),
            "character_state_text": _read_text(self.project_root / "character_state.txt"),
            "world_state": _read_json(self.project_root / "world_state.json", {}),
            "updated_at": _utc_now(),
            "last_recorded_chapter": 0,
        }

    def load_legacy_views(self) -> dict[str, Any]:
        self.ensure_initialized()
        views = _read_json(self.legacy_views_path, {})
        if not views:
            views = self._bootstrap_legacy_views()
            _write_json(self.legacy_views_path, views)
        views.setdefault("global_summary_text", "")
        views.setdefault("character_state_text", "")
        views.setdefault("world_state", {})
        views.setdefault("updated_at", _utc_now())
        return views

    def export_legacy_views(self) -> None:
        views = self.load_legacy_views()
        (self.project_root / "global_summary.txt").write_text(
            str(views.get("global_summary_text", "") or ""),
            encoding="utf-8",
        )
        (self.project_root / "character_state.txt").write_text(
            str(views.get("character_state_text", "") or ""),
            encoding="utf-8",
        )
        _write_json(self.project_root / "world_state.json", views.get("world_state", {}))

    def record_chapter_update(
        self,
        chapter_number: int,
        chapter_text: str,
        global_summary_text: str,
        character_state_text: str,
        chapter_summary: str = "",
        world_state: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.ensure_initialized()
        chapter_number = int(chapter_number)
        chapter_record = {
            "chapter_number": chapter_number,
            "chapter_summary": chapter_summary.strip() or _build_chapter_summary(chapter_text),
            "chapter_excerpt": _trim_text(chapter_text, 500),
            "global_summary_text": str(global_summary_text or "").strip(),
            "character_state_text": str(character_state_text or "").strip(),
            "metadata": metadata or {},
            "updated_at": _utc_now(),
        }
        _write_json(self.chapters_dir / f"chapter_{chapter_number:06d}.json", chapter_record)

        views = self.load_legacy_views()
        views["global_summary_text"] = chapter_record["global_summary_text"]
        views["character_state_text"] = chapter_record["character_state_text"]
        if world_state is None:
            views["world_state"] = _read_json(self.project_root / "world_state.json", views.get("world_state", {}))
        else:
            views["world_state"] = world_state
        views["updated_at"] = _utc_now()
        views["last_recorded_chapter"] = chapter_number
        _write_json(self.legacy_views_path, views)

        manifest = _read_json(self.manifest_path, {})
        manifest["schema_version"] = self.SCHEMA_VERSION
        manifest["chapters_per_volume"] = self.chapters_per_volume
        manifest["last_recorded_chapter"] = max(int(manifest.get("last_recorded_chapter", 0) or 0), chapter_number)
        manifest.setdefault("created_at", _utc_now())
        manifest["updated_at"] = _utc_now()
        _write_json(self.manifest_path, manifest)

        self._refresh_volume_card(chapter_number)
        self.export_legacy_views()

    def build_context_snapshot(self, current_chapter_num: int) -> dict[str, str]:
        views = self.load_legacy_views()
        reference_chapter = max(1, int(current_chapter_num or 1) - 1)
        volume_number = self._resolve_volume_number(reference_chapter)
        return {
            "global_summary_text": str(views.get("global_summary_text", "") or ""),
            "character_state_text": str(views.get("character_state_text", "") or ""),
            "volume_summary_text": self._load_volume_summary(volume_number),
            "hook_summary_text": self._summarize_hooks(),
            "thread_summary_text": self._summarize_threads(),
        }

    def _resolve_volume_number(self, chapter_number: int) -> int:
        zero_based = max(0, int(chapter_number) - 1)
        return zero_based // self.chapters_per_volume + 1

    def _refresh_volume_card(self, chapter_number: int) -> None:
        volume_number = self._resolve_volume_number(chapter_number)
        start = (volume_number - 1) * self.chapters_per_volume + 1
        end = start + self.chapters_per_volume - 1
        summary_lines: list[str] = []
        for current in range(start, end + 1):
            record = _read_json(self.chapters_dir / f"chapter_{current:06d}.json", {})
            summary = str(record.get("chapter_summary", "") or "").strip()
            if summary:
                summary_lines.append(f"第{current}章：{summary}")

        _write_json(
            self.volumes_dir / f"volume_{volume_number:03d}.json",
            {
                "volume_number": volume_number,
                "chapter_range": [start, end],
                "summary_text": "\n".join(summary_lines),
                "updated_at": _utc_now(),
            },
        )

    def _load_volume_summary(self, volume_number: int) -> str:
        payload = _read_json(self.volumes_dir / f"volume_{volume_number:03d}.json", {})
        return str(payload.get("summary_text", "") or "").strip()

    def _summarize_hooks(self) -> str:
        hook_data = _read_json(self.project_root / "hook_registry.json", {})
        if isinstance(hook_data, dict) and isinstance(hook_data.get("hooks"), list):
            candidates = [item for item in hook_data["hooks"] if isinstance(item, dict)]
        elif isinstance(hook_data, dict):
            candidates = [item for item in hook_data.values() if isinstance(item, dict)]
        elif isinstance(hook_data, list):
            candidates = [item for item in hook_data if isinstance(item, dict)]
        else:
            candidates = []

        lines: list[str] = []
        for item in candidates:
            status = str(item.get("status", "open") or "open").lower()
            if status in {"resolved", "closed", "done"}:
                continue
            label = str(item.get("hook_text") or item.get("title") or item.get("content") or "").strip()
            if label:
                lines.append(_trim_text(label, 80))
            if len(lines) >= 5:
                break
        return "；".join(lines)

    def _summarize_threads(self) -> str:
        thread_data = _read_json(self.project_root / ".narrative_threads.json", {})
        if isinstance(thread_data, dict) and isinstance(thread_data.get("threads"), list):
            candidates = [item for item in thread_data["threads"] if isinstance(item, dict)]
        elif isinstance(thread_data, dict):
            candidates = [item for item in thread_data.values() if isinstance(item, dict)]
        elif isinstance(thread_data, list):
            candidates = [item for item in thread_data if isinstance(item, dict)]
        else:
            candidates = []

        lines: list[str] = []
        for item in candidates:
            label = str(item.get("name") or item.get("thread_name") or item.get("title") or item.get("type") or "").strip()
            if label:
                lines.append(_trim_text(label, 60))
            if len(lines) >= 5:
                break
        return "；".join(lines)
