import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path


NODE_TO_CARD_SECTION: dict[int, int] = {
    121: 122,
    123: 124,
    125: 126,
    127: 128,
    129: 130,
    131: 132,
}

REQUIRED_TOP_SECTIONS = [119, 121, 122, 123, 124, 125, 126, 127, 128, 129, 130, 131, 132, 133, 134, 136]
REQUIRED_GATE_FIELDS = [
    "fate_flip_mode",
    "villain_struct_win",
    "mythic_core",
    "debt_chain_stage",
    "route_track",
    "supporting_recovery_slot",
]
REQUIRED_V29_MARKERS = [
    "0-12",
    "88-136",
    "outcome_once`等价“大改命”",
    "冷却锁按章号差执行",
    "旧节中出现的高危词仅可作为“幕后术语/历史口径”",
    "制度纯台词章`占比上限25%",
    "卷34后禁止修改终局制度主判",
]


@dataclass
class NodeVolumeCheck:
    volume: int
    outcome_chapters: list[int]
    cost_only_count: int


@dataclass
class CardVolumeCheck:
    volume: int
    outcome_suggestions: list[int]
    has_villain_struct_win: bool
    has_mythic_core: bool


class CliArgs(argparse.Namespace):
    architecture: str | None = None
    strict: bool = False


def split_top_sections(text: str) -> dict[int, str]:
    heading_re = re.compile(r"^##\s+(\d+)\.\s+.*$", re.MULTILINE)
    matches = list(heading_re.finditer(text))
    sections: dict[int, str] = {}
    for idx, match in enumerate(matches):
        section_num = int(match.group(1))
        start = match.start()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        sections[section_num] = text[start:end]
    return sections


def split_subsections(section_text: str) -> list[tuple[str, str, str]]:
    heading_re = re.compile(r"^###\s+(\d+\.\d+)\s+([^\n]+)$", re.MULTILINE)
    matches = list(heading_re.finditer(section_text))
    chunks: list[tuple[str, str, str]] = []
    for idx, match in enumerate(matches):
        sub_id = match.group(1)
        title = match.group(2).strip()
        body_start = match.end()
        body_end = matches[idx + 1].start() if idx + 1 < len(matches) else len(section_text)
        body = section_text[body_start:body_end].strip()
        chunks.append((sub_id, title, body))
    return chunks


def extract_node_volumes(section_text: str) -> dict[int, NodeVolumeCheck]:
    result: dict[int, NodeVolumeCheck] = {}
    for _, title, body in split_subsections(section_text):
        if not title.startswith("卷"):
            continue

        volume_match = re.search(r"卷\s*(\d+)", title)
        if not volume_match:
            continue

        volume = int(volume_match.group(1))
        outcome_chapters = [
            int(m.group(1))
            for m in re.finditer(r"^\s*(\d+)\.\s+.*本卷唯一`outcome_once`", body, re.MULTILINE)
        ]
        cost_only_count = len(re.findall(r"`cost_only`", body))
        result[volume] = NodeVolumeCheck(
            volume=volume,
            outcome_chapters=outcome_chapters,
            cost_only_count=cost_only_count,
        )
    return result


def extract_card_volumes(section_text: str) -> dict[int, CardVolumeCheck]:
    result: dict[int, CardVolumeCheck] = {}
    for _, title, body in split_subsections(section_text):
        if not title.startswith("卷"):
            continue

        volume_match = re.search(r"卷\s*(\d+)", title)
        if not volume_match:
            continue

        volume = int(volume_match.group(1))
        outcome_suggestions = [
            int(match.group(1))
            for match in re.finditer(r"`outcome_once`[^\n。]*建议\s*(\d+)", body)
        ]
        has_villain_struct_win = (
            "`villain_struct_win`" in body
            or "反派结构胜场" in body
        )
        has_mythic_core = "`mythic_core`" in body

        result[volume] = CardVolumeCheck(
            volume=volume,
            outcome_suggestions=outcome_suggestions,
            has_villain_struct_win=has_villain_struct_win,
            has_mythic_core=has_mythic_core,
        )
    return result


def parse_args() -> CliArgs:
    project_root = Path(__file__).resolve().parent.parent
    fallback_architecture = project_root / "wxhyj" / "Novel_architecture.txt"
    default_architecture = fallback_architecture

    parser = argparse.ArgumentParser(
        description="校验 v2.8 卷17-40（121-134）门禁一致性"
    )
    _ = parser.add_argument(
        "--architecture",
        default=None,
        help="架构路径（默认：项目根目录/wxhyj/Novel_architecture.txt）",
    )
    _ = parser.add_argument(
        "--strict",
        action="store_true",
        help="将 warning 视为失败（非0退出）",
    )
    args = parser.parse_args(namespace=CliArgs())
    if args.architecture is None:
        args.architecture = str(default_architecture)
    return args


def validate(text: str) -> tuple[list[str], list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    notes: list[str] = []

    sections = split_top_sections(text)

    for section_num in REQUIRED_TOP_SECTIONS:
        if section_num not in sections:
            errors.append(f"缺少必需节：{section_num}")

    section_119 = sections.get(119, "")
    for field_name in REQUIRED_GATE_FIELDS:
        if f"`{field_name}`" not in section_119:
            errors.append(f"119未声明关键字段：`{field_name}`")

    outcome_by_volume: dict[int, int] = {}
    checked_volume_pairs = 0

    for node_section, card_section in NODE_TO_CARD_SECTION.items():
        node_text = sections.get(node_section, "")
        card_text = sections.get(card_section, "")
        if not node_text or not card_text:
            continue

        node_volumes = extract_node_volumes(node_text)
        card_volumes = extract_card_volumes(card_text)

        all_volumes = sorted(set(node_volumes.keys()) | set(card_volumes.keys()))
        if len(all_volumes) != 4:
            errors.append(
                f"节{node_section}/{card_section}卷数量异常：检测到{len(all_volumes)}卷（期望4卷）"
            )

        for volume in all_volumes:
            checked_volume_pairs += 1
            node_info = node_volumes.get(volume)
            card_info = card_volumes.get(volume)

            if node_info is None:
                errors.append(f"节{node_section}缺少卷{volume}节点块")
                continue
            if card_info is None:
                errors.append(f"节{card_section}缺少卷{volume}验收卡")
                continue

            if len(node_info.outcome_chapters) != 1:
                errors.append(
                    f"卷{volume}在节{node_section}的`outcome_once`唯一触发数={len(node_info.outcome_chapters)}（应为1）"
                )
            if node_info.cost_only_count > 2:
                errors.append(
                    f"卷{volume}在节{node_section}的`cost_only`出现{node_info.cost_only_count}次（应<=2）"
                )

            if len(card_info.outcome_suggestions) != 1:
                errors.append(
                    f"卷{volume}在节{card_section}的`outcome_once`建议位数量={len(card_info.outcome_suggestions)}（应为1）"
                )

            if not card_info.has_villain_struct_win:
                errors.append(f"卷{volume}在节{card_section}缺少`villain_struct_win`门禁")
            if not card_info.has_mythic_core:
                errors.append(f"卷{volume}在节{card_section}缺少`mythic_core`门禁")

            if len(node_info.outcome_chapters) == 1 and len(card_info.outcome_suggestions) == 1:
                node_chapter = node_info.outcome_chapters[0]
                card_chapter = card_info.outcome_suggestions[0]
                if node_chapter != card_chapter:
                    errors.append(
                        f"卷{volume}建议位不一致：节{node_section}为{node_chapter}，节{card_section}为{card_chapter}"
                    )
                else:
                    outcome_by_volume[volume] = node_chapter

        for required_line in [
            "四卷累计`outcome_once`=4",
            "四卷累计`villain_struct_win`",
            "四卷累计`mythic_core`>=8",
        ]:
            if required_line not in card_text:
                errors.append(f"节{card_section}缺少组级门禁：{required_line}")

    section_133 = sections.get(133, "")
    seq_match = re.search(r"卷17-40分别对应([^。\n]+)", section_133)
    if not seq_match:
        errors.append("节133缺少卷17-40建议位映射序列")
    else:
        seq_values = [
            int(match.group(1))
            for match in re.finditer(r"(\d+)", seq_match.group(1))
        ]
        if len(seq_values) != 24:
            errors.append(f"节133建议位序列数量={len(seq_values)}（应为24）")
        ordered_volumes = list(range(17, 41))
        missing_volumes = [v for v in ordered_volumes if v not in outcome_by_volume]
        if missing_volumes:
            warnings.append(f"无法完成节133全量交叉比对，缺少卷数据：{missing_volumes}")
        else:
            expected_values = [outcome_by_volume[v] for v in ordered_volumes]
            if seq_values != expected_values:
                errors.append(
                    "节133建议位序列与121/123/125/127/129/131抽取值不一致"
                )

    section_134 = sections.get(134, "")
    expected_entries = [
        "卷17-20：执行`122`",
        "卷21-24：执行`124`",
        "卷25-28：执行`126`",
        "卷29-32：执行`128`",
        "卷33-36：执行`130`",
        "卷37-40：执行`132`",
    ]
    for entry in expected_entries:
        if entry not in section_134:
            errors.append(f"节134执行入口缺失：{entry}")

    section_136 = sections.get(136, "")
    for marker in REQUIRED_V29_MARKERS:
        if marker not in section_136:
            errors.append(f"节136缺少v2.9关键口径：{marker}")

    notes.append(f"已校验卷级节点/验收卡配对数：{checked_volume_pairs}")
    if outcome_by_volume:
        notes.append(
            f"已提取卷17-40建议位数量：{len(outcome_by_volume)}"
        )

    return errors, warnings, notes


def main() -> int:
    args = parse_args()
    if args.architecture is None:
        print("❌ --architecture 解析失败")
        return 2
    architecture_path = Path(args.architecture).resolve()

    if not architecture_path.exists():
        print(f"❌ 文件不存在: {architecture_path}")
        return 2

    text = architecture_path.read_text(encoding="utf-8")
    errors, warnings, notes = validate(text)

    print("=== v2.8 Gate Consistency Check ===")
    print(f"目标文件: {architecture_path}")

    for note in notes:
        print(f"ℹ️  {note}")

    if warnings:
        print("\n⚠️ Warnings:")
        for item in warnings:
            print(f"- {item}")

    if errors:
        print("\n❌ Errors:")
        for item in errors:
            print(f"- {item}")
    else:
        print("\n✅ 所有门禁一致性检查通过。")

    if errors:
        return 1
    if args.strict and warnings:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
