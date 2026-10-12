import { apiGet } from "@/lib/api";
import type { CharacterFactPositionV1 } from "@/types/characterFacts";
import type { HierarchyRecord } from "@/types/hierarchy";

/** 功能：读取现目录的真实章节锚，不按创建时间或数字章号猜位置。Args: 小说与取消信号。Returns: 带父级标题的可选章节。 */
export async function loadCharacterFactChapters(novelId: string, signal?: AbortSignal): Promise<HierarchyRecord[]> {
  const volumes = (await apiGet<{ data: HierarchyRecord[] }>(`/api/volumes/novel/${novelId}`, { signal })).data;
  const arcs = (await Promise.all(volumes.map((row) => apiGet<{ data: HierarchyRecord[] }>(`/api/arcs/volume/${row.volume_id}`, { signal })))).flatMap((page) => page.data);
  const scenes = (await Promise.all(arcs.map((row) => apiGet<{ data: HierarchyRecord[] }>(`/api/scenes/arc/${row.arc_id}`, { signal })))).flatMap((page) => page.data);
  const chapters = (await Promise.all(scenes.map((row) => apiGet<{ data: HierarchyRecord[] }>(`/api/chapters/scene/${row.scene_id}`, { signal })))).flatMap((page) => page.data);
  if ([...volumes, ...arcs, ...scenes, ...chapters].some((row) => row.novel_id !== novelId || row.is_deleted)) throw new Error("CHARACTER_FACT_DIRECTORY_CHANGED");
  return chapters.map((chapter) => ({ ...chapter, title: [volumes.find((row) => row.volume_id === chapter.volume_id)?.title, arcs.find((row) => row.arc_id === chapter.arc_id)?.title, scenes.find((row) => row.scene_id === chapter.scene_id)?.title, chapter.title].filter(Boolean).join(" / ") }));
}

/** 功能：从明确选择的锚选项还原合同位置。Args: 原小说及界面选项。Returns: 锚或未选择，不生成第二套时间。 */
export function characterFactPositionFromKey(novelId: string, key: string): CharacterFactPositionV1 | null {
  if (!key) return null;
  if (key === "book_start") return { version: 1, intent: "book_start", target_type: "novel", target_id: novelId };
  const [intent, targetId] = key.split(":");
  if (intent === "volume_start" && targetId) return { version: 1, intent, target_type: "volume", target_id: targetId };
  if ((intent !== "chapter_before" && intent !== "chapter_after") || !targetId) throw new Error("CHARACTER_FACT_POSITION_INVALID");
  return { version: 1, intent, target_type: "chapter", target_id: targetId };
}

/** 功能：稳定映射位置选择控件。Args: 原锚。Returns: 选项值。 */
export function characterFactPositionKey(position: CharacterFactPositionV1 | null): string {
  return !position ? "" : position.intent === "book_start" ? "book_start" : `${position.intent}:${position.target_id}`;
}
