# architecture_consistency_checker.py
# -*- coding: utf-8 -*-
"""
架构一致性检查器
确保生成的章节目录与小说架构保持一致
"""
import re
import logging
from typing import Dict, List, Tuple, Any

class ArchitectureConsistencyChecker:
    def __init__(self):
        self.consistency_rules = {
            "narrative_flow": 0.8,      # 叙事流畅性
            "character_arc": 0.7,       # 角色弧光
            "plot_progression": 0.9,    # 情节推进
            "world_building": 0.6,      # 世界构建
            "theme_consistency": 0.8    # 主题一致性
        }

    def parse_architecture(self, architecture_text: str) -> Dict[str, Any]:
        """解析小说架构"""
        architecture = {
            "total_chapters": 0,
            "main_plot_points": [],
            "character_arcs": [],
            "world_elements": [],
            "themes": [],
            "structure_elements": []
        }

        # 提取总章节数
        chapter_match = re.search(r'总章节数[：:]\s*(\d+)', architecture_text)
        if chapter_match:
            architecture["total_chapters"] = int(chapter_match.group(1))

        # 提取主要情节要点
        plot_patterns = [
            r'主要冲突[：:](.*?)(?=\n|$)',
            r'核心矛盾[：:](.*?)(?=\n|$)',
            r'故事主线[：:](.*?)(?=\n|$)'
        ]

        for pattern in plot_patterns:
            matches = re.findall(pattern, architecture_text)
            for match in matches:
                if match.strip():
                    architecture["main_plot_points"].append(match.strip())

        # 提取角色信息
        character_patterns = [
            r'主角[：:](.*?)(?=\n|$)',
            r'主要角色[：:](.*?)(?=\n|$)'
        ]

        for pattern in character_patterns:
            matches = re.findall(pattern, architecture_text)
            for match in matches:
                if match.strip():
                    architecture["character_arcs"].append(match.strip())

        # 提取世界元素
        world_patterns = [
            r'世界观[：:](.*?)(?=\n|$)',
            r'背景设定[：:](.*?)(?=\n|$)',
            r'环境设定[：:](.*?)(?=\n|$)'
        ]

        for pattern in world_patterns:
            matches = re.findall(pattern, architecture_text)
            for match in matches:
                if match.strip():
                    architecture["world_elements"].append(match.strip())

        return architecture

    def parse_chapter_directory(self, directory_text: str) -> List[Dict[str, Any]]:
        """解析章节目录"""
        chapters = []
        chapter_blocks = re.split(r'\n\s*\n', directory_text.strip())

        chapter_pattern = re.compile(r'^第\s*(\d+)\s*章\s*(?:-\s*(.*))?\s*$')

        for block in chapter_blocks:
            lines = [line.strip() for line in block.split('\n') if line.strip()]
            if not lines:
                continue

            # 解析章节标题
            title_match = chapter_pattern.match(lines[0])
            if not title_match:
                continue

            chapter_num = int(title_match.group(1))
            chapter_title = title_match.group(2).strip() if title_match.group(2) else ""

            chapter = {
                "number": chapter_num,
                "title": chapter_title,
                "content": lines,
                "elements": self._extract_chapter_elements(lines)
            }

            chapters.append(chapter)

        return sorted(chapters, key=lambda x: x["number"])

    def _extract_chapter_elements(self, lines: List[str]) -> Dict[str, str]:
        """提取章节元素"""
        elements = {
            "role": "",
            "purpose": "",
            "suspense": "",
            "foreshadowing": "",
            "twist": "",
            "conflict": "",
            "character_arc": "",
            "hook": ""
        }

        # 提取关键元素
        patterns = {
            "role": [r'定位[：:](.*?)(?=\n|$)', r'写作重点[：:](.*?)(?=\n|$)'],
            "purpose": [r'作用[：:](.*?)(?=\n|$)', r'核心作用[：:](.*?)(?=\n|$)'],
            "suspense": [r'悬念[：:](.*?)(?=\n|$)', r'张力评级[：:](.*?)(?=\n|$)'],
            "foreshadowing": [r'伏笔[：:](.*?)(?=\n|$)', r'长期伏笔[：:](.*?)(?=\n|$)'],
            "twist": [r'转折[：:](.*?)(?=\n|$)', r'认知颠覆[：:](.*?)(?=\n|$)'],
            "conflict": [r'冲突[：:](.*?)(?=\n|$)', r'关键冲突[：:](.*?)(?=\n|$)'],
            "character_arc": [r'人物弧光[：:](.*?)(?=\n|$)', r'角色发展[：:](.*?)(?=\n|$)'],
            "hook": [r'钩子[：:](.*?)(?=\n|$)', r'主钩子[：:](.*?)(?=\n|$)']
        }

        for element, pattern_list in patterns.items():
            for pattern in pattern_list:
                matches = re.findall(pattern, '\n'.join(lines), re.IGNORECASE)
                if matches:
                    elements[element] = matches[0].strip()
                    break

        return elements

    def check_narrative_flow_consistency(self, chapters: List[Dict[str, Any]]) -> Tuple[bool, List[str]]:
        """检查叙事流畅性"""
        issues = []

        for i in range(1, len(chapters)):
            prev_chapter = chapters[i-1]
            curr_chapter = chapters[i]

            # 检查章节编号连续性
            if curr_chapter["number"] != prev_chapter["number"] + 1:
                issues.append(f"章节编号不连续：第{prev_chapter['number']}章后应为第{prev_chapter['number']+1}章，实际为第{curr_chapter['number']}章")

            # 检查情节推进的合理性
            prev_purpose = prev_chapter["elements"].get("purpose", "")
            curr_role = curr_chapter["elements"].get("role", "")

            # 如果前一章是"结尾"或"收尾"，当前章应该是"开端"或"新阶段"
            if any(keyword in prev_purpose.lower() for keyword in ["结尾", "收尾", "完结"]) and \
               not any(keyword in curr_role.lower() for keyword in ["开端", "新", "开始", "启动"]):
                issues.append(f"情节推进异常：第{prev_chapter['number']}章是结尾章节，第{curr_chapter['number']}章应有新的开始")

        return len(issues) == 0, issues

    def check_character_arc_consistency(self, chapters: List[Dict[str, Any]]) -> Tuple[bool, List[str]]:
        """检查角色弧光一致性"""
        issues = []
        character_arcs = {}

        for chapter in chapters:
            arc_text = chapter["elements"].get("character_arc", "")
            if arc_text:
                # 提取角色发展关键词
                development_keywords = self._extract_development_keywords(arc_text)
                for keyword in development_keywords:
                    if keyword not in character_arcs:
                        character_arcs[keyword] = []
                    character_arcs[keyword].append((chapter["number"], arc_text))

        # 检查角色发展的连续性
        for character, arc_list in character_arcs.items():
            if len(arc_list) > 1:
                for i in range(1, len(arc_list)):
                    prev_chapter, prev_arc = arc_list[i-1]
                    curr_chapter, curr_arc = arc_list[i]

                    # 检查角色发展是否有逻辑断裂
                    if self._has_arc_break(prev_arc, curr_arc):
                        issues.append(f"角色弧光断裂：'{character}'在第{prev_chapter}章和第{curr_chapter}章之间发展不连贯")

        return len(issues) == 0, issues

    def check_plot_progression_consistency(self, chapters: List[Dict[str, Any]]) -> Tuple[bool, List[str]]:
        """检查情节推进一致性"""
        issues = []
        plot_intensity = []

        for chapter in chapters:
            # 分析情节强度
            suspense = chapter["elements"].get("suspense", "")
            conflict = chapter["elements"].get("conflict", "")

            intensity = self._calculate_plot_intensity(suspense, conflict)
            plot_intensity.append((chapter["number"], intensity))

        # 检查情节强度曲线的合理性
        for i in range(1, len(plot_intensity)):
            prev_num, prev_intensity = plot_intensity[i-1]
            curr_num, curr_intensity = plot_intensity[i]

            # 检查是否存在不合理的强度跳跃
            if abs(curr_intensity - prev_intensity) > 3:  # 强度跳跃超过3级
                issues.append(f"情节强度异常：第{prev_num}章到第{curr_num}章强度跳跃过大({prev_intensity}->{curr_intensity})")

        return len(issues) == 0, issues

    def check_world_building_consistency(self, chapters: List[Dict[str, Any]]) -> Tuple[bool, List[str]]:
        """检查世界构建一致性"""
        issues = []
        world_elements = {}

        for chapter in chapters:
            # 提取世界元素
            title = chapter["title"]
            content = " ".join(chapter["content"])

            # 检查是否有世界观矛盾
            if self._has_world_contradiction(content):
                issues.append(f"世界观矛盾：第{chapter['number']}章《{title}》中可能存在世界观设定冲突")

        return len(issues) == 0, issues

    def check_theme_consistency(self, chapters: List[Dict[str, Any]]) -> Tuple[bool, List[str]]:
        """检查主题一致性"""
        issues = []
        themes = []

        for chapter in chapters:
            # 提取主题元素
            purpose = chapter["elements"].get("purpose", "")
            role = chapter["elements"].get("role", "")

            theme_keywords = self._extract_theme_keywords(purpose + " " + role)
            themes.extend(theme_keywords)

        # 检查主题的一致性
        unique_themes = set(themes)
        if len(unique_themes) > len(themes) * 0.5:  # 如果主题过于分散
            issues.append("主题分散：章节中的主题元素过于分散，可能缺乏统一的核心主题")

        return len(issues) == 0, issues

    def _extract_development_keywords(self, text: str) -> List[str]:
        """提取角色发展关键词"""
        keywords = []
        development_patterns = [
            r'(成长|进步|提升)',
            r'(堕落|退步|沉沦)',
            r'(觉醒|顿悟|领悟)',
            r'(转变|改变|蜕变)',
            r'(迷茫|困惑|迷失)',
            r'(坚定|决绝|果断)'
        ]

        for pattern in development_patterns:
            matches = re.findall(pattern, text)
            keywords.extend(matches)

        return keywords

    def _has_arc_break(self, prev_arc: str, curr_arc: str) -> bool:
        """检查是否有角色弧光断裂"""
        # 定义矛盾的发展方向
        contradictory_pairs = [
            ("成长", "堕落"),
            ("觉醒", "迷茫"),
            ("坚定", "困惑")
        ]

        for prev_word, curr_word in contradictory_pairs:
            if prev_word in prev_arc and curr_word in curr_arc:
                return True

        return False

    def _calculate_plot_intensity(self, suspense: str, conflict: str) -> int:
        """计算情节强度（1-10级）"""
        intensity = 1

        # 根据悬念评级计算强度
        if "★" in suspense:
            stars = suspense.count("★")
            intensity += stars * 2

        # 根据冲突类型计算强度
        high_intensity_conflicts = ["生死", "决战", "背叛", "毁灭", "重大危机"]
        medium_intensity_conflicts = ["争执", "对抗", "挑战", "困难"]

        combined_text = (conflict + " " + suspense).lower()

        for conflict_type in high_intensity_conflicts:
            if conflict_type in combined_text:
                intensity += 3
                break

        for conflict_type in medium_intensity_conflicts:
            if conflict_type in combined_text:
                intensity += 1
                break

        return min(intensity, 10)

    def _has_world_contradiction(self, content: str) -> bool:
        """检查是否有世界观矛盾"""
        # 这里可以实现更复杂的世界观矛盾检测逻辑
        # 比如检查时间线、地理设定、规则系统等的一致性
        return False

    def _extract_theme_keywords(self, text: str) -> List[str]:
        """提取主题关键词"""
        themes = []
        theme_patterns = [
            r'(成长|成熟|进步)',
            r'(背叛|欺骗|信任)',
            r'(牺牲|奉献)',
            r'(正义|邪恶)',
            r'(自由|束缚)',
            r'(希望|绝望)'
        ]

        for pattern in theme_patterns:
            matches = re.findall(pattern, text)
            themes.extend(matches)

        return themes

    def check_full_consistency(self, architecture_text: str, directory_text: str) -> Dict[str, Any]:
        """全面一致性检查"""
        result = {
            "overall_score": 0.0,
            "checks": {},
            "issues": [],
            "recommendations": []
        }

        try:
            # 解析架构和目录
            architecture = self.parse_architecture(architecture_text)
            chapters = self.parse_chapter_directory(directory_text)

            if not chapters:
                result["issues"].append("无法解析章节目录")
                return result

            # 执行各项检查
            checks = [
                ("narrative_flow", self.check_narrative_flow_consistency),
                ("character_arc", self.check_character_arc_consistency),
                ("plot_progression", self.check_plot_progression_consistency),
                ("world_building", self.check_world_building_consistency),
                ("theme_consistency", self.check_theme_consistency)
            ]

            total_score = 0.0
            total_weight = 0.0

            for check_name, check_function in checks:
                try:
                    is_consistent, issues = check_function(chapters)
                    weight = self.consistency_rules.get(check_name, 0.5)

                    result["checks"][check_name] = {
                        "consistent": is_consistent,
                        "issues": issues,
                        "score": 1.0 if is_consistent else 0.0,
                        "weight": weight
                    }

                    if not is_consistent:
                        result["issues"].extend(issues)

                    total_score += (1.0 if is_consistent else 0.0) * weight
                    total_weight += weight

                except Exception as e:
                    logging.error(f"一致性检查失败 {check_name}: {e}")
                    result["checks"][check_name] = {
                        "consistent": False,
                        "issues": [f"检查异常: {str(e)}"],
                        "score": 0.0,
                        "weight": 0.5
                    }
                    total_weight += 0.5

            # 计算总体得分
            if total_weight > 0:
                result["overall_score"] = total_score / total_weight

            # 生成建议
            if result["overall_score"] < 0.8:
                result["recommendations"].append("建议重新审视章节目录的连贯性")

            if result["overall_score"] < 0.6:
                result["recommendations"].append("建议修改部分章节以确保与整体架构一致")

        except Exception as e:
            logging.error(f"全面一致性检查异常: {e}")
            result["issues"].append(f"检查过程异常: {str(e)}")

        return result

def check_architecture_consistency(architecture_file: str, directory_file: str) -> Dict[str, Any]:
    """检查架构一致性的便捷函数"""
    try:
        with open(architecture_file, 'r', encoding='utf-8') as f:
            architecture_text = f.read()

        with open(directory_file, 'r', encoding='utf-8') as f:
            directory_text = f.read()

        checker = ArchitectureConsistencyChecker()
        return checker.check_full_consistency(architecture_text, directory_text)

    except Exception as e:
        return {
            "overall_score": 0.0,
            "checks": {},
            "issues": [f"检查失败: {str(e)}"],
            "recommendations": ["请检查文件是否存在且格式正确"]
        }

if __name__ == "__main__":
    import sys as _sys
    
    if len(_sys.argv) > 1:
        novel_folder = _sys.argv[1]
    else:
        print("Usage: python architecture_consistency_checker.py <novel_folder>")
        _sys.exit(1)
    
    architecture_file = f"{novel_folder}/Novel_architecture.txt"
    directory_file = f"{novel_folder}/Novel_directory.txt"

    result = check_architecture_consistency(architecture_file, directory_file)

    print("🔍 架构一致性检查结果")
    print(f"总体得分: {result['overall_score']:.2f}")

    if result["issues"]:
        print("\n❌ 发现问题:")
        for issue in result["issues"]:
            print(f"  - {issue}")

    if result["recommendations"]:
        print("\n💡 建议:")
        for rec in result["recommendations"]:
            print(f"  - {rec}")

    print("\n📊 详细检查结果:")
    for check_name, check_result in result["checks"].items():
        status = "✅" if check_result["consistent"] else "❌"
        print(f"  {status} {check_name}: {check_result['score']:.2f} (权重: {check_result['weight']})")

        if check_result["issues"]:
            for issue in check_result["issues"]:
                print(f"    - {issue}")