from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from novel_generator.story_ledger import PromptMemoryContext, StoryLedger, _build_chapter_summary, _trim_text


@dataclass(frozen=True)
class ReviewMemoryContext:
    character_state_text: str = ""
    global_summary_text: str = ""
    plot_arcs_text: str = ""


def _join_labeled_sections(sections: list[tuple[str, str]]) -> str:
    blocks: list[str] = []
    for label, text in sections:
        content = str(text or "").strip()
        if not content:
            continue
        blocks.append(f"【{label}】\n{content}")
    return "\n\n".join(blocks)


class GenerationStateFacade:
    def __init__(self, project_root: str, chapters_per_volume: int = 50) -> None:
        self.ledger = StoryLedger(project_root, chapters_per_volume=chapters_per_volume)

    def load_prompt_memory_context(self, current_chapter_num: int) -> PromptMemoryContext:
        snapshot = self.ledger.build_context_snapshot(current_chapter_num)
        sections: list[str] = []

        global_summary_text = str(snapshot.get("global_summary_text", "") or "").strip()
        character_state_text = str(snapshot.get("character_state_text", "") or "").strip()
        volume_summary_text = str(snapshot.get("volume_summary_text", "") or "").strip()
        hook_summary_text = str(snapshot.get("hook_summary_text", "") or "").strip()
        thread_summary_text = str(snapshot.get("thread_summary_text", "") or "").strip()

        if global_summary_text:
            sections.append(f"【全书状态总览】\n{_trim_text(global_summary_text, 1200)}")
        if character_state_text:
            sections.append(f"【角色状态账本】\n{_trim_text(character_state_text, 1200)}")
        if volume_summary_text:
            sections.append(f"【卷级记忆】\n{_trim_text(volume_summary_text, 1600)}")
        if hook_summary_text:
            sections.append(f"【未回收伏笔】\n{hook_summary_text}")
        if thread_summary_text:
            sections.append(f"【活跃叙事线程】\n{thread_summary_text}")

        return PromptMemoryContext(
            global_summary_text=global_summary_text,
            character_state_text=character_state_text,
            volume_summary_text=volume_summary_text,
            hook_summary_text=hook_summary_text,
            thread_summary_text=thread_summary_text,
            memory_guidance="\n\n".join(sections),
        )

    def load_review_memory_context(
        self,
        current_chapter_num: int,
        plot_arcs_text: str = "",
    ) -> ReviewMemoryContext:
        prompt_context = self.load_prompt_memory_context(current_chapter_num)

        character_state_text = _join_labeled_sections(
            [
                ("角色状态账本", _trim_text(prompt_context.character_state_text, 1600)),
                ("活跃叙事线程", _trim_text(prompt_context.thread_summary_text, 800)),
            ]
        )
        global_summary_text = _join_labeled_sections(
            [
                ("全书状态总览", _trim_text(prompt_context.global_summary_text, 1800)),
                ("卷级记忆", _trim_text(prompt_context.volume_summary_text, 1600)),
            ]
        )
        merged_plot_arcs_text = _join_labeled_sections(
            [
                ("现有剧情要点", _trim_text(plot_arcs_text, 1200)),
                ("活跃叙事线程", _trim_text(prompt_context.thread_summary_text, 1000)),
                ("未回收伏笔", _trim_text(prompt_context.hook_summary_text, 1000)),
            ]
        )
        return ReviewMemoryContext(
            character_state_text=character_state_text,
            global_summary_text=global_summary_text,
            plot_arcs_text=merged_plot_arcs_text,
        )

    def commit_chapter_state(
        self,
        chapter_number: int,
        chapter_text: str,
        global_summary_text: str,
        character_state_text: str,
        chapter_summary: str = "",
        world_state: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.ledger.record_chapter_update(
            chapter_number=chapter_number,
            chapter_text=chapter_text,
            global_summary_text=global_summary_text,
            character_state_text=character_state_text,
            chapter_summary=chapter_summary or _build_chapter_summary(chapter_text),
            world_state=world_state,
            metadata=metadata,
        )
