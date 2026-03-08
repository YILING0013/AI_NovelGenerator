import json
import os
import re
from datetime import datetime
from typing import Dict, List, Tuple

from utils import resolve_architecture_file


def read_file(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except UnicodeDecodeError:
        try:
            with open(path, "r", encoding="gbk") as f:
                return f.read()
        except Exception:
            return ""
    except FileNotFoundError:
        return ""


class ArchitectureComplianceChecker:
    REQUIRED_FIELDS: List[Tuple[str, List[str]]] = [
        ("1. 基础元信息", [r"^\s*##\s*1\.\s*基础元信息", r"^\s*1\.\s*基础元信息"]),
        ("2. 张力与冲突", [r"^\s*##\s*2\.\s*张力与冲突", r"^\s*2\.\s*张力与冲突"]),
        ("3. 匠心思维应用", [r"^\s*##\s*3\.\s*匠心思维应用", r"^\s*3\.\s*匠心思维应用"]),
        ("4. 伏笔与信息差", [r"^\s*##\s*4\.\s*伏笔与信息差", r"^\s*4\.\s*伏笔与信息差"]),
        ("5. 暧昧与修罗场", [r"^\s*##\s*5\.\s*暧昧与修罗场", r"^\s*5\.\s*暧昧与修罗场"]),
        ("6. 剧情精要", [r"^\s*##\s*6\.\s*剧情精要", r"^\s*6\.\s*剧情精要"]),
        ("7. 衔接设计", [r"^\s*##\s*7\.\s*衔接设计", r"^\s*7\.\s*衔接设计"]),
    ]

    def __init__(self, novel_dir: str, novel_corpus_name: str = ""):
        self.novel_dir = novel_dir
        self.novel_corpus_name = novel_corpus_name or ""
        if self.novel_corpus_name:
            candidate_dir = os.path.join(novel_dir, self.novel_corpus_name)
            self.project_dir = candidate_dir if os.path.isdir(candidate_dir) else novel_dir
        else:
            self.project_dir = novel_dir
        self.architecture_path = resolve_architecture_file(self.project_dir)
        self.directory_path = os.path.join(self.project_dir, "Novel_directory.txt")

    def parse_directory(self, content: str) -> Dict[int, str]:
        chapters = {}
        lines = content.split("\n")
        current_chapter = None
        current_content = []

        chapter_pattern = r"^第\s*(\d+)\s*章"
        for line in lines:
            match = re.search(chapter_pattern, line.strip())
            if match:
                if current_chapter is not None:
                    chapters[current_chapter] = "\n".join(current_content)
                current_chapter = int(match.group(1))
                current_content = [line]
            elif current_chapter is not None:
                current_content.append(line)

        if current_chapter is not None:
            chapters[current_chapter] = "\n".join(current_content)
        return chapters

    def _load_key_points(self) -> List[Tuple[int, List[str], str]]:
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        default_config_path = os.path.join(base_dir, "config", "default_foreshadowing_rules.json")
        novel_config_path = os.path.join(self.project_dir, "config", "foreshadowing_rules.json")
        config_path = novel_config_path if os.path.exists(novel_config_path) else default_config_path

        key_points = []
        if not os.path.exists(config_path):
            return key_points

        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
            reversals = config.get("major_reversals", {})
            for name, info in reversals.items():
                reveal_chapter = int(info.get("reveal_chapter", 0) or 0)
                keywords = info.get("keywords", [])
                if isinstance(keywords, str):
                    keywords = [keywords]
                keywords = [str(k).strip() for k in keywords if str(k).strip()]
                desc = f"{name}: {str(info.get('description', ''))[:20]}..."
                key_points.append((reveal_chapter, keywords, desc))
        except Exception:
            return []

        key_points.sort(key=lambda x: x[0])
        return key_points

    def check_compliance_result(self) -> dict:
        hard_fail_reasons: List[str] = []
        details = {
            "missing_chapters": [],
            "missing_fields": {},
            "key_point_missing": [],
        }

        if not os.path.exists(self.architecture_path):
            hard_fail_reasons.append("Architecture file missing")
        if not os.path.exists(self.directory_path):
            hard_fail_reasons.append("Directory file missing")
        if hard_fail_reasons:
            return {
                "passed": False,
                "hard_fail_reasons": hard_fail_reasons,
                "summary": {"total_chapters": 0, "last_chapter": 0},
                "details": details,
            }

        dir_content = read_file(self.directory_path)
        chapters = self.parse_directory(dir_content)
        if not chapters:
            hard_fail_reasons.append("No chapters found in Novel_directory.txt")
            return {
                "passed": False,
                "hard_fail_reasons": hard_fail_reasons,
                "summary": {"total_chapters": 0, "last_chapter": 0},
                "details": details,
            }

        chapter_nums = sorted(chapters.keys())
        total_chapters = len(chapter_nums)
        last_chapter = chapter_nums[-1]

        missing = [i for i in range(1, last_chapter + 1) if i not in chapters]
        if missing:
            details["missing_chapters"] = missing
            hard_fail_reasons.append(f"章节不连续，缺失 {len(missing)} 章")

        for idx in chapter_nums:
            content = chapters[idx]
            missing_fields = []
            for display_name, alternatives in self.REQUIRED_FIELDS:
                if not any(re.search(pattern, content, flags=re.MULTILINE) for pattern in alternatives):
                    missing_fields.append(display_name)
            if missing_fields:
                details["missing_fields"][str(idx)] = missing_fields
                hard_fail_reasons.append(f"第{idx}章缺少必要字段: {', '.join(missing_fields)}")

        for chap_num, keywords, desc in self._load_key_points():
            if chap_num <= 0 or chap_num > last_chapter:
                continue
            content = chapters.get(chap_num, "")
            if not content:
                details["key_point_missing"].append((chap_num, desc))
                hard_fail_reasons.append(f"第{chap_num}章关键剧情点未生成: {desc}")
                continue
            if keywords:
                found = any(keyword in content for keyword in keywords)
                if not found:
                    details["key_point_missing"].append((chap_num, desc))
                    hard_fail_reasons.append(f"第{chap_num}章关键剧情点关键词缺失: {desc}")

        # 去重，保持输出稳定
        hard_fail_reasons = list(dict.fromkeys(hard_fail_reasons))
        return {
            "passed": len(hard_fail_reasons) == 0,
            "hard_fail_reasons": hard_fail_reasons,
            "summary": {
                "total_chapters": total_chapters,
                "last_chapter": last_chapter,
            },
            "details": details,
        }

    def check_compliance(self) -> List[str]:
        result = self.check_compliance_result()
        summary = result.get("summary", {})
        hard_fail_reasons = result.get("hard_fail_reasons", [])
        details = result.get("details", {})

        report = []
        report.append("📊 **基础统计**")
        report.append(f"- 识别到的章节数: {summary.get('total_chapters', 0)}")
        report.append(f"- 最后一章编号: {summary.get('last_chapter', 0)}")

        missing_chapters = details.get("missing_chapters", [])
        if missing_chapters:
            report.append(f"❌ **章节缺失警告**: {missing_chapters[:20]}")
        else:
            if summary.get("last_chapter", 0) > 0:
                report.append(f"✅ **连续性检查**: 所有章节编号连续 (1-{summary.get('last_chapter', 0)})")

        report.append("\n📝 **模板完整性检查（全章节）**")
        missing_fields = details.get("missing_fields", {})
        if missing_fields:
            for chap, fields in sorted(missing_fields.items(), key=lambda x: int(x[0])):
                report.append(f"❌ 第{chap}章 缺少字段: {fields}")
        else:
            report.append("✅ 全章节均包含 1-7 节")

        report.append("\n🔑 **关键剧情点一致性检查**")
        key_missing = details.get("key_point_missing", [])
        if key_missing:
            for chap_num, desc in key_missing:
                report.append(f"❌ 第{chap_num}章 [{desc}] 未满足关键词要求")
        else:
            report.append("✅ 关键剧情点检查通过")

        report.append("\n✅ **综合结论**")
        if hard_fail_reasons:
            report.append("❌ 架构合规性未通过")
            for reason in hard_fail_reasons:
                report.append(f"- {reason}")
        else:
            report.append("✅ 架构合规性通过")

        return report

    def generate_report_file(self) -> str:
        report_lines = self.check_compliance()
        report_path = os.path.join(self.novel_dir, "architecture_compliance_report.md")
        with open(report_path, "w", encoding="utf-8") as f:
            f.write("# 架构合规性验证报告\n\n")
            f.write(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            f.write("\n\n".join(report_lines))
        return report_path
