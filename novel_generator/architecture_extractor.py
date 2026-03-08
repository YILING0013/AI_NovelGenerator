# architecture_extractor.py
# -*- coding: utf-8 -*-
"""
动态架构提取与分析模块
功能：
1. 动态解析架构文件结构（卷、章节、角色、术语）
2. LLM辅助语境萃取（Context Extraction）
"""

import re
import logging
from typing import Any

from novel_generator.common import invoke_with_cleaning


class DynamicArchitectureExtractor:
    """全动态架构解析器"""
    
    def __init__(self, architecture_content: str):
        self.content = architecture_content
        self.structure = self._parse_structure()
        self.characters = self._extract_characters()
        self.sects = self._extract_sects()
        
    def _parse_structure(self) -> dict[str, Any]:
        """解析架构文件的层级结构"""
        structure: dict[str, Any] = {
            "volumes": [],
            "chapters": {},
            "chapter_to_volume": {},
        }
        volume_candidates: list[dict[str, Any]] = []

        legacy_plot_text = self._extract_legacy_section_block(5, 6)
        if legacy_plot_text:
            volume_candidates.extend(self._parse_legacy_volume_blocks(legacy_plot_text))

        volume_candidates.extend(self._parse_markdown_volume_blocks())
        volume_candidates.extend(self._parse_plain_volume_blocks())

        if not volume_candidates:
            volume_candidates.extend(self._parse_legacy_volume_blocks(self.content))

        deduped: dict[int, dict[str, Any]] = {}
        for volume in volume_candidates:
            vol_num = int(volume.get("vol_num", 0) or 0)
            if vol_num <= 0:
                continue
            existing = deduped.get(vol_num)
            if existing is None or len(str(volume.get("content", ""))) > len(str(existing.get("content", ""))):
                deduped[vol_num] = {
                    "vol_num": vol_num,
                    "title": str(volume.get("title", "")).strip() or f"第{vol_num}卷",
                    "content": str(volume.get("content", "")).strip(),
                }

        structure["volumes"] = [deduped[key] for key in sorted(deduped.keys())]

        chapter_range_pattern = re.compile(
            r'(?:第\s*)?(\d{1,4})\s*[-~—–至到]\s*(\d{1,4})\s*章(?:[：:]\s*([^\n]*))?'
        )
        single_chapter_pattern = re.compile(r'第\s*(\d{1,4})\s*章(?:[：:·\s）)]|$)')

        for vol in structure["volumes"]:
            vol_content = str(vol.get("content", ""))
            chapter_numbers: set[int] = set()

            for match in chapter_range_pattern.finditer(vol_content):
                start_ch = int(match.group(1))
                end_ch = int(match.group(2))
                if end_ch < start_ch:
                    start_ch, end_ch = end_ch, start_ch
                line_start = vol_content.rfind("\n", 0, match.start()) + 1
                line_end = vol_content.find("\n", match.end())
                if line_end == -1:
                    line_end = len(vol_content)
                context = vol_content[line_start:line_end].strip() or vol_content[match.start():match.end()].strip()
                if len(context) > 1500:
                    context = context[:1500]

                for ch in range(start_ch, end_ch + 1):
                    existing = str(structure["chapters"].get(ch, ""))
                    if not existing or len(context) > len(existing):
                        structure["chapters"][ch] = context
                    structure["chapter_to_volume"][ch] = vol["vol_num"]
                    chapter_numbers.add(ch)

            for match in single_chapter_pattern.finditer(vol_content):
                ch_num = int(match.group(1))
                if ch_num in chapter_numbers:
                    continue
                start = match.start()
                context = vol_content[start:start + 1500].strip()
                if not context:
                    continue
                structure["chapters"][ch_num] = context
                structure["chapter_to_volume"][ch_num] = vol["vol_num"]
                chapter_numbers.add(ch_num)

            if chapter_numbers:
                vol["chapter_min"] = min(chapter_numbers)
                vol["chapter_max"] = max(chapter_numbers)
            else:
                vol["chapter_min"] = None
                vol["chapter_max"] = None

        self._augment_chapter_mapping_from_global_ranges(structure)

        return structure

    def _extract_legacy_section_block(self, section_num: int, next_section_num: int | None = None) -> str:
        if next_section_num is None:
            pattern = rf'#===\s*{section_num}\)[^\n]*\n?(.*)'
        else:
            pattern = rf'#===\s*{section_num}\)[^\n]*\n?(.*?)(?=#===\s*{next_section_num}\)|\Z)'
        match = re.search(pattern, self.content, re.DOTALL)
        return match.group(1).strip() if match else ""

    def _parse_legacy_volume_blocks(self, text: str) -> list[dict[str, Any]]:
        vol_matches = list(re.finditer(r'(?:第([一二三四五六七八九十\d]+)卷[：:]\s*)([^\n]+)', text))
        volumes: list[dict[str, Any]] = []
        for idx, match in enumerate(vol_matches):
            vol_num = self._cn_to_int(match.group(1))
            if vol_num <= 0:
                continue
            start_idx = match.start()
            end_idx = vol_matches[idx + 1].start() if idx + 1 < len(vol_matches) else len(text)
            block = text[start_idx:end_idx].strip()
            if not block:
                continue
            volumes.append(
                {
                    "vol_num": vol_num,
                    "title": match.group(2).strip(),
                    "content": block,
                }
            )
        return volumes

    def _parse_markdown_volume_blocks(self) -> list[dict[str, Any]]:
        pattern = re.compile(
            r'(?m)^###\s*\d+(?:\.\d+)?\s*卷\s*(\d+)\s*[《「『]?([^》」』\n]+)?[》」』]?[^\n]*情节点[^\n]*$'
        )
        matches = list(pattern.finditer(self.content))
        boundary_pattern = re.compile(r'(?m)^##(?:#)?\s*\d+(?:\.\d+)?\s*[^\n]*$')
        boundary_starts = [m.start() for m in boundary_pattern.finditer(self.content)]
        volumes: list[dict[str, Any]] = []

        for match in matches:
            vol_num = int(match.group(1))
            title = (match.group(2) or "").strip(" 《》「」『』:：") or f"卷{vol_num}"
            start_idx = match.start()
            end_idx = len(self.content)
            for pos in boundary_starts:
                if pos > start_idx:
                    end_idx = pos
                    break
            block = self.content[start_idx:end_idx].strip()
            if not block:
                continue
            volumes.append(
                {
                    "vol_num": vol_num,
                    "title": title,
                    "content": block,
                }
            )

        return volumes

    def _parse_plain_volume_blocks(self) -> list[dict[str, Any]]:
        pattern = re.compile(
            r'(?m)^\s*卷\s*(\d{1,3})\s*[《「『]([^》」』\n]{1,40})[》」』](?:\s*[（(][^\n]{0,40}[)）])?\s*$'
        )
        matches = list(pattern.finditer(self.content))
        boundary_pattern = re.compile(r'(?m)^##\s*\d+(?:\.\d+)?\s*[^\n]*$')
        boundary_starts = [m.start() for m in boundary_pattern.finditer(self.content)]
        volumes: list[dict[str, Any]] = []
        for idx, match in enumerate(matches):
            vol_num = int(match.group(1))
            title = (match.group(2) or "").strip() or f"卷{vol_num}"
            start_idx = match.start()
            end_idx = matches[idx + 1].start() if idx + 1 < len(matches) else len(self.content)
            for pos in boundary_starts:
                if pos > start_idx:
                    end_idx = min(end_idx, pos)
                    break
            block = self.content[start_idx:end_idx].strip()
            if not block:
                continue
            volumes.append(
                {
                    "vol_num": vol_num,
                    "title": title,
                    "content": block,
                }
            )
        return volumes

    def _extract_semantic_table_context(self, table_row: str) -> str:
        cells = [cell.strip() for cell in str(table_row or "").strip().strip("|").split("|")]
        if not cells:
            return ""

        generic_cells = {
            "卷次",
            "章节范围",
            "目标字数",
            "阶段",
            "编号",
            "状态",
            "验收标准",
            "Setup章",
            "Echo章",
            "Resolve章",
            "文本落地",
            "读者可感",
            "设计完成",
            "第一阶段",
            "第二阶段",
            "第三阶段",
            "第四阶段",
        }

        semantic_chunks: list[str] = []
        for cell in cells:
            normalized = re.sub(r"\s+", "", cell)
            if not normalized:
                continue
            if normalized in generic_cells:
                continue
            if re.fullmatch(r"[A-Za-z]{1,4}\d{0,4}", normalized):
                continue
            if re.fullmatch(r"卷\d{1,3}", normalized):
                continue
            if re.fullmatch(r"\d{1,4}\s*[-~—–至到]\s*\d{1,4}(?:章)?", normalized):
                continue
            if re.fullmatch(r"\d+(?:\.\d+)?万\s*[-~—–至到]\s*\d+(?:\.\d+)?万", normalized):
                continue
            if len(re.findall(r"[\u4e00-\u9fff]", normalized)) < 3:
                continue
            semantic_chunks.append(normalized)

        return "，".join(semantic_chunks)[:1500]

    def _is_semantic_chapter_context(self, context: str) -> bool:
        text = str(context or "").strip()
        if not text:
            return False

        chinese_count = len(re.findall(r"[\u4e00-\u9fff]", text))
        if chinese_count < 4:
            return False

        narrative_markers = (
            "主角",
            "反派",
            "女主",
            "伏笔",
            "古碑",
            "天书",
            "重生",
            "追捕",
            "背叛",
            "审判",
            "回收",
            "冲突",
            "危机",
            "线索",
            "谜",
            "战",
        )
        if any(marker in text for marker in narrative_markers):
            return True

        generic_markers = (
            "说明",
            "覆盖",
            "窗口",
            "执行",
            "模板",
            "口径",
            "比例",
            "阶段",
            "章节范围",
            "每窗口",
            "验收",
            "白名单",
        )
        generic_hits = sum(1 for marker in generic_markers if marker in text)
        if generic_hits >= 2:
            return False

        if re.search(r"[A-Za-z]{1,3}\d{2,}", text):
            return False

        return chinese_count >= 8

    def _build_chapter_context_with_followups(self, lines: list[str], line_index: int, base_line: str) -> str:
        fragments = [str(base_line or "").strip()]
        pointer = line_index + 1

        while pointer < len(lines):
            next_line = str(lines[pointer] or "").strip()
            pointer += 1
            if not next_line:
                continue
            if re.match(r"^#{2,}\s*", next_line):
                break
            if next_line.startswith("|"):
                break

            normalized = re.sub(r"^[\-*]\s*", "", next_line)
            normalized = re.sub(r"^\d+[\.)、]\s*", "", normalized)
            if not normalized:
                continue
            if len(re.findall(r"[\u4e00-\u9fff]", normalized)) < 2:
                break

            fragments.append(normalized)
            if len(fragments) >= 3:
                break

        return "，".join(fragments)[:1500]

    def _augment_chapter_mapping_from_global_ranges(self, structure: dict[str, Any]) -> None:
        chapter_defs: dict[int, str] = structure.setdefault("chapters", {})
        chapter_to_volume: dict[int, int] = structure.setdefault("chapter_to_volume", {})

        chapter_range_with_unit = re.compile(r"(\d{1,4})\s*[-~—–至到]\s*(\d{1,4})\s*章")
        table_range_pattern = re.compile(r"(\d{1,4})\s*[-~—–至到]\s*(\d{1,4})")
        volume_pattern = re.compile(r"卷\s*(\d{1,3})")
        table_header = ""

        lines = self.content.splitlines()
        for idx, raw_line in enumerate(lines):
            line = raw_line.strip()
            if not line:
                continue

            if line.startswith("|"):
                if any(keyword in line for keyword in ("章节范围", "Setup章", "Echo章", "Resolve章", "卷次")):
                    table_header = line

                range_matches = list(table_range_pattern.finditer(line))
                if not range_matches:
                    continue

                is_chapter_table = (
                    "章" in line
                    or any(keyword in table_header for keyword in ("章节范围", "Setup章", "Echo章", "Resolve章"))
                )
                if not is_chapter_table:
                    continue

                volume_match = volume_pattern.search(line)
                volume_num = int(volume_match.group(1)) if volume_match else 0
                semantic_context = self._extract_semantic_table_context(line)
                context_is_usable = self._is_semantic_chapter_context(semantic_context)

                for range_match in range_matches:
                    prefix = line[max(0, range_match.start() - 2):range_match.start()]
                    if "卷" in prefix:
                        continue
                    start_ch = int(range_match.group(1))
                    end_ch = int(range_match.group(2))
                    if end_ch < start_ch:
                        start_ch, end_ch = end_ch, start_ch
                    if end_ch - start_ch > 1200:
                        continue

                    for chapter_num in range(start_ch, end_ch + 1):
                        if context_is_usable:
                            existing = str(chapter_defs.get(chapter_num, ""))
                            if not existing or len(semantic_context) > len(existing):
                                chapter_defs[chapter_num] = semantic_context
                        if volume_num > 0:
                            chapter_to_volume[chapter_num] = volume_num
                continue

            for match in chapter_range_with_unit.finditer(line):
                start_ch = int(match.group(1))
                end_ch = int(match.group(2))
                if end_ch < start_ch:
                    start_ch, end_ch = end_ch, start_ch
                if end_ch - start_ch > 1200:
                    continue

                context = self._build_chapter_context_with_followups(lines, idx, line)
                if not self._is_semantic_chapter_context(context):
                    continue
                volume_match = volume_pattern.search(line)
                volume_num = int(volume_match.group(1)) if volume_match else 0

                for chapter_num in range(start_ch, end_ch + 1):
                    existing = str(chapter_defs.get(chapter_num, ""))
                    if not existing or len(context) > len(existing):
                        chapter_defs[chapter_num] = context
                    if volume_num > 0:
                        chapter_to_volume[chapter_num] = volume_num

    def _iter_markdown_sections(self) -> list[dict[str, Any]]:
        sections: list[dict[str, Any]] = []
        heading_pattern = re.compile(r'(?m)^##\s*(\d+)\.\s*([^\n]+?)\s*$')
        matches = list(heading_pattern.finditer(self.content))
        for idx, match in enumerate(matches):
            start = match.end()
            end = matches[idx + 1].start() if idx + 1 < len(matches) else len(self.content)
            sections.append(
                {
                    "number": int(match.group(1)),
                    "title": match.group(2).strip(),
                    "content": self.content[start:end].strip(),
                }
            )
        return sections

    def _extract_markdown_section_block(self, section_number: int) -> str:
        for section in self._iter_markdown_sections():
            if int(section.get("number", -1)) == int(section_number):
                return str(section.get("content", "")).strip()
        return ""

    def _extract_markdown_sections_by_keyword(self, keywords: tuple[str, ...], max_chars: int = 12000) -> str:
        if not keywords:
            return ""
        chunks: list[str] = []
        total_len = 0
        for section in self._iter_markdown_sections():
            title = str(section.get("title", ""))
            if not any(keyword in title for keyword in keywords):
                continue
            block = f"## {section.get('number')}. {title}\n{section.get('content', '')}".strip()
            if not block:
                continue
            chunks.append(block)
            total_len += len(block)
            if total_len >= max_chars:
                break
        return "\n\n".join(chunks)[:max_chars]

    def _find_relevant_volumes(self, start_chapter: int, end_chapter: int) -> list[dict[str, Any]]:
        if end_chapter < start_chapter:
            start_chapter, end_chapter = end_chapter, start_chapter

        volumes: list[dict[str, Any]] = list(self.structure.get("volumes", []))
        if not volumes:
            return []

        ranged_matches: list[dict[str, Any]] = []
        for vol in volumes:
            chapter_min = vol.get("chapter_min")
            chapter_max = vol.get("chapter_max")
            if chapter_min is None or chapter_max is None:
                continue
            if chapter_min <= end_chapter and chapter_max >= start_chapter:
                ranged_matches.append(vol)
        if ranged_matches:
            return sorted(ranged_matches, key=lambda item: int(item.get("vol_num", 0) or 0))

        chapter_to_volume: dict[int, int] = self.structure.get("chapter_to_volume", {})
        volume_lookup: dict[int, dict[str, Any]] = {
            int(vol.get("vol_num", 0) or 0): vol for vol in volumes if vol.get("vol_num") is not None
        }

        mapped_volume_nums: list[int] = []
        for chapter in range(start_chapter, end_chapter + 1):
            mapped = chapter_to_volume.get(chapter)
            if mapped is None:
                continue
            mapped_num = int(mapped)
            if mapped_num not in mapped_volume_nums:
                mapped_volume_nums.append(mapped_num)
        if mapped_volume_nums:
            return [volume_lookup[num] for num in mapped_volume_nums if num in volume_lookup]

        ranged_volumes = [
            vol for vol in volumes
            if vol.get("chapter_min") is not None and vol.get("chapter_max") is not None
        ]
        if ranged_volumes:
            def distance_from_start(vol: dict[str, Any]) -> int:
                chapter_min = int(vol["chapter_min"])
                chapter_max = int(vol["chapter_max"])
                if start_chapter < chapter_min:
                    return chapter_min - start_chapter
                if start_chapter > chapter_max:
                    return start_chapter - chapter_max
                return 0

            return [min(ranged_volumes, key=distance_from_start)]

        return [volumes[0]]

    def _extract_characters(self) -> set[str]:
        """动态提取所有定义过的角色名"""
        chars = set()
        protagonist_match = re.search(r'主角实名[：:]\s*([^\s（(，。,；;]+)', self.content)
        if protagonist_match:
            chars.add(protagonist_match.group(1).strip())

        female_leads = re.findall(
            r'(?m)^\s*\d+\.\s*([^\s（(，。,；;]+)（[^）\n]*线[^）\n]*）',
            self.content,
        )
        for name in female_leads:
            normalized = name.strip()
            if normalized:
                chars.add(normalized)

        # 匹配：### 角色一：角色名
        matches = re.findall(r'### 角色[一二三四五六七八九十\d]+[：:]\s*([^\s（(]+)', self.content)
        for name in matches:
            chars.add(name.strip())
            
        # 匹配辅助角色：**赵铁柱**
        matches_aux = re.findall(r'\*\*([^\s*]+)\*\*[：:]\s*(?:外门|内门|长老|管事|反派)', self.content)
        for name in matches_aux:
            if len(name) < 5: # 排除过长的非人名
                chars.add(name.strip())
                
        return chars

    def _extract_sects(self) -> set[str]:
        """动态提取宗门/地点名称"""
        sects = set()
        # 基于常见模式猜测，或从特定section提取
        # 这里使用简单的关键词匹配来发现大写的组织名
        # 实际更复杂的项目可能需要LLM辅助提取
        keywords = ["宗", "门", "派", "阁", "院", "殿"]
        for kw in keywords:
            matches = re.findall(rf'([^\s，。、（]+{kw})', self.content)
            for m in matches:
                if 2 <= len(m) <= 6:
                    sects.add(m)
        return sects

    def _cn_to_int(self, cn_str: str) -> int:
        """中文数字转INT（简单版）"""
        cn_map = {'一':1, '二':2, '三':3, '四':4, '五':5, '六':6, '七':7, '八':8, '九':9, '十':10}
        if cn_str.isdigit():
            return int(cn_str)
        if len(cn_str) == 1:
            return cn_map.get(cn_str, 1)
        # 简单处理"十一"到"十九"
        if cn_str.startswith('十'):
            return 10 + cn_map.get(cn_str[1], 0)
        return 1

    def get_context_guide_via_llm(self, llm_adapter: Any, start_chapter: int, end_chapter: int) -> str:
        """
        Phase 1: 调用LLM阅读架构，生成生成指南
        """
        # 1. 准备Prompt
        # 截取相关的大块内容（卷情节+角色表）
        # 只要不超过LLM窗口即可。现在的模型一般能吃几万token。
        # 我们可以把 Section 5 (情节) 和 Section 3 (角色) 完整传进去，或者根据卷号筛选。
        
        relevant_volumes = self._find_relevant_volumes(start_chapter, end_chapter)
        current_vol_content = "\n\n".join(
            str(vol.get("content", "")) for vol in relevant_volumes if vol.get("content")
        )
        if not current_vol_content and self.structure.get("volumes"):
            current_vol_content = str(self.structure["volumes"][0].get("content", ""))
        if not current_vol_content:
            current_vol_content = self._extract_markdown_sections_by_keyword(("详细情节点", "情节点", "情节架构"), max_chars=15000)
        if not current_vol_content:
            current_vol_content = self._extract_legacy_section_block(5, 6)[:15000]
        if not current_vol_content:
            current_vol_content = self.content[:15000]

        # 提取角色表内容
        char_text = self._extract_legacy_section_block(3, 4)
        if not char_text:
            char_text = self._extract_markdown_section_block(5)
        if not char_text:
            char_text = self._extract_markdown_sections_by_keyword(("角色", "女主", "反派系统"), max_chars=10000)

        # 提取特定章节的锁定情节（如果有）
        specific_plot = ""
        for ch in range(start_chapter, end_chapter + 1):
            if ch in self.structure["chapters"]:
                specific_plot += f"\n【架构中对第{ch}章的定义】：\n{self.structure['chapters'][ch]}\n"

        prompt = f"""
你是一位专业的长篇小说架构师。请阅读以下《小说设定》片段，为写手生成一份针对**第{start_chapter}章到第{end_chapter}章**的【蓝图生成指南】。

### 输入资料
1. **当前卷情节架构**：
{current_vol_content[:15000]} 

2. **角色设定**：
{char_text[:10000]}

3. **具体章节锁定信息（必须遵守）**：
{specific_plot}

### 任务要求
请分析上述资料，针对第{start_chapter}-{end_chapter}章，总结出必须遵循的关键点。输出格式如下：

【情节锁定】
- 第X章必须发生的核心事件：...
- 必须出场的角色：...
- 必须使用的关键台词/物品：...

【角色状态】
- 主角当前修为/心态：...
- 相关角色的关系进展：...

【世界观与禁忌】
- 本阶段涉及的特殊规则：...
- 严禁出现的BUG（如：此时主角还没获得XX能力）：...

【 tone & style 】
- 本段落的叙事基调（如：压抑、爽快、诡异）：...

只输出指南内容，不要废话。
"""
        logging.info(f"正在进行语境萃取（Context Extraction）: 第{start_chapter}-{end_chapter}章...")
        try:
           guide = invoke_with_cleaning(llm_adapter, prompt)
           return guide
        except Exception as e:
            logging.error(f"语境萃取失败: {e}")
            return f"（语境萃取失败，使用默认模式）\n{specific_plot}"

    def get_character_list(self) -> list[str]:
        return list(self.characters)

    def get_sect_list(self) -> list[str]:
        return list(self.sects)
