"""在设置保存时同步当前任务方案的 Provider 引用。"""

from __future__ import annotations

from typing import Any

from .contracts import Flow, FlowRef
from .graph import validate_flow
from .store import FlowStore


class ProviderReferencedError(ValueError):
    """要删除的 Provider 仍被当前方案或当前默认修订使用。"""

    def __init__(self, references: list[dict[str, Any]]) -> None:
        """保留可定位的方案引用，不暴露模型配置或密钥。

        Args:
            references: 使用待删除 Provider 的方案、修订和节点位置。

        Returns:
            无。
        """
        self.references = references
        aliases = sorted({item["provider"] for item in references})
        names = list(dict.fromkeys(item["flow_name"] for item in references))
        extra = f"等 {len(names)} 个方案" if len(names) > 3 else ""
        super().__init__(
            f"Provider {', '.join(aliases)} 仍被任务方案「{'、'.join(names[:3])}」{extra}使用，"
            "请先在这些方案中解除引用后再删除"
        )


def update_flow_provider_references(
    store: FlowStore,
    previous_aliases: set[str],
    current_aliases: set[str],
    renames: list[tuple[str, str]],
) -> list[FlowRef]:
    """检查删除引用，并一次发布全部当前方案的 Provider 重命名修订。

    Args:
        store: 当前任务方案文件存储。
        previous_aliases: 设置保存前的 Provider 别名。
        current_aliases: 设置校验后实际保留的 Provider 别名。
        renames: 与配置更新相同顺序的旧名、新名列表。

    Returns:
        本次发布的新修订引用；未改变方案时返回空列表。
    """
    rename_targets: dict[str, str] = {}
    for source, target in renames:
        # A→B→C 必须与设置提交的顺序一致，已有 A、B 引用都最终指向 C。
        rename_targets = {
            alias: target if destination == source else destination
            for alias, destination in rename_targets.items()
        }
        rename_targets[source] = target
    removed = {
        rename_targets.get(alias, alias) for alias in previous_aliases
    } - current_aliases
    if not rename_targets and not removed:
        return []

    with store._locked():
        index = store._read_index()
        current: dict[tuple[str, int], Flow] = {}
        for flow_id, summary in index["flows"].items():
            reference = (flow_id, summary["revision"])
            current[reference] = store._read_flow(*reference)
        # 默认可以固定在较旧修订，它仍在使用，不能只检查最新编辑稿。
        for selected in index["defaults"].values():
            reference = (selected["id"], selected["revision"])
            if reference not in current:
                current[reference] = store._read_flow(*reference)

        pending: dict[tuple[str, int], Flow] = {}
        references: list[dict[str, Any]] = []
        for reference, flow in current.items():
            changed = False
            nested = [(flow, "")]
            while nested:
                graph, path = nested.pop()
                old_alias = graph.default_provider
                graph.default_provider = rename_targets.get(old_alias, old_alias)
                changed |= graph.default_provider != old_alias
                locations = [(graph.default_provider, path + "default_provider")]
                for node in graph.nodes:
                    if node.type != "llm":
                        continue
                    old_alias = node.config.get("provider", "")
                    alias = rename_targets.get(old_alias, old_alias)
                    if alias != old_alias:
                        node.config["provider"] = alias
                        changed = True
                    locations.append((alias, path + "nodes/" + node.id))
                for alias, location in locations:
                    if alias and alias in removed:
                        references.append({
                            "provider": alias,
                            "flow_id": flow.id,
                            "revision": flow.revision,
                            "flow_name": flow.name,
                            "location": location,
                        })
                nested.extend(
                    (child, path + "subflows/" + child_id + "/")
                    for child_id, child in graph.subflows.items()
                )
            if changed:
                pending[reference] = validate_flow(flow)
        if references:
            raise ProviderReferencedError(references)
        if not pending:
            return []

        # 较旧的默认稿与最新稿可能不同，分别派生修订，保持各自原内容。
        for flow_id, _revision in list(pending):
            latest = (flow_id, index["flows"][flow_id]["revision"])
            pending.setdefault(latest, current[latest])
        published: list[FlowRef] = []
        for reference, flow in sorted(pending.items()):
            flow_id, old_revision = reference
            next_revision = index["flows"][flow_id]["revision"] + 1
            while (store.root / "flows" / flow_id / f"{next_revision}.json").exists():
                next_revision += 1
            saved = flow.model_copy(update={"revision": next_revision}, deep=True)
            store._atomic_write(
                store.root / "flows" / flow_id / f"{next_revision}.json",
                saved.model_dump(mode="json"),
            )
            index["flows"][flow_id] = {
                "task": saved.task, "name": saved.name, "revision": next_revision,
            }
            selected = index["defaults"].get(flow.task)
            if selected == {"id": flow_id, "revision": old_revision}:
                index["defaults"][flow.task] = {"id": flow_id, "revision": next_revision}
            published.append(FlowRef(id=flow_id, revision=next_revision))

        # 修订文件不可变；只有目录原子替换成功才一起对外生效。
        index["version"] += 1
        store._atomic_write(store.root / "index.json", index)
        return published
