# -*- coding: utf-8 -*-
"""
批量生成预检查模块
v3.0: 集成深度验证器（占位符、结构、重复、一致性）
"""

import logging
from typing import Dict
from datetime import datetime

# 导入所有验证器
from novel_generator.validators.base import ValidationContext
from novel_generator.validators.female_growth import FemaleGrowthValidator
from novel_generator.validators.romance import RomanceValidator
from novel_generator.validators.foreshadowing import ForeshadowingValidator
from novel_generator.validators.placeholder import PlaceholderDetector
from novel_generator.validators.structure import StructureValidator
from novel_generator.validators.duplicate import DuplicateDetector
from novel_generator.validators.consistency import ConsistencyValidator

logger = logging.getLogger(__name__)


class BatchPreChecker:
    """批量生成预检查器 v3.0"""
    
    def __init__(self, filepath: str):
        self.filepath = filepath
        # 初始化共享上下文
        self.context = ValidationContext(filepath)
        self.report = {
            "timestamp": "",
            "filepath": filepath,
            "checks": {},
            "deep_checks": {},  # 新增：深度检查结果
            "warnings": [],
            "recommendations": [],
            "passed": True
        }
    
    def run_all_checks(self, start_chapter: int = 1, end_chapter: int = 400, 
                       deep_scan: bool = False) -> Dict:
        """
        运行所有检查
        
        Args:
            start_chapter: 起始章节
            end_chapter: 结束章节
            deep_scan: 是否运行深度扫描（占位符、结构、重复、一致性）
        """
        self.report["timestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.report["chapter_range"] = f"{start_chapter}-{end_chapter}"
        
        logger.info(f"开始批量生成预检查: 第{start_chapter}-{end_chapter}章")
        
        # ============ 基础检查 ============
        
        # 1. 蓝图完整性检查
        self._check_blueprint_completeness(start_chapter, end_chapter)

        # 2. 女主成长线检查
        self._run_validator("female_lead_growth", FemaleGrowthValidator)
        
        # 3. 暧昧密度检查
        self._run_validator("romance_density", RomanceValidator)
        
        # 4. 反转伏笔检查
        self._run_validator("reversal_foreshadowing", ForeshadowingValidator)
        
        # ============ 深度检查（可选）============
        if deep_scan:
            self._run_deep_scan(start_chapter=start_chapter, end_chapter=end_chapter)
        
        # 生成总结
        self._generate_summary()
        
        return self.report
    
    def _run_validator(self, key: str, validator_class):
        """运行单个验证器"""
        try:
            validator = validator_class(self.context)
            result = validator.validate()
            self._process_validator_result(key, result)
        except Exception as e:
            self.report["checks"][key] = {"status": "❌ 错误", "error": str(e)}
    
    @staticmethod
    def _is_chapter_in_range(chapter_num: int, start_chapter: int, end_chapter: int) -> bool:
        try:
            chapter = int(chapter_num)
        except (TypeError, ValueError):
            return False
        return int(start_chapter) <= chapter <= int(end_chapter)

    def _run_deep_scan(self, start_chapter: int, end_chapter: int):
        """运行深度扫描（严格按批量范围过滤）。"""
        logger.info("开始深度扫描...")
        
        # 1. 占位符检测
        try:
            detector = PlaceholderDetector(self.context)
            all_result = detector.scan_all_chapters()
            result = {
                chapter_num: placeholders
                for chapter_num, placeholders in all_result.items()
                if self._is_chapter_in_range(chapter_num, start_chapter, end_chapter)
            }
            if result:
                chapter_list = sorted(result.keys())
                chapter_preview = ", ".join(str(x) for x in chapter_list[:10])
                if len(chapter_list) > 10:
                    chapter_preview += f" ... 等{len(chapter_list)}章"
                total_count = sum(len(v) for v in result.values())
                report_text = (
                    f"⚠️ 扫描范围内发现 {total_count} 个占位符问题:\n\n"
                    f"  - 命中章节: {chapter_preview}"
                )
            else:
                report_text = "✅ 扫描范围内未发现占位符"
            self.report["deep_checks"]["placeholder"] = {
                "status": "✅ 通过" if not result else "⚠️ 发现问题",
                "count": sum(len(v) for v in result.values()) if result else 0,
                "chapters_affected": len(result),
                "report": report_text
            }
        except Exception as e:
            self.report["deep_checks"]["placeholder"] = {"status": "❌ 错误", "error": str(e)}
        
        # 2. 结构完整性检测
        try:
            validator = StructureValidator(self.context)
            all_result = validator.scan_all_chapters()
            result = {
                chapter_num: issue
                for chapter_num, issue in all_result.items()
                if self._is_chapter_in_range(chapter_num, start_chapter, end_chapter)
            }
            if result:
                chapter_list = sorted(result.keys())
                chapter_preview = ", ".join(str(x) for x in chapter_list[:10])
                if len(chapter_list) > 10:
                    chapter_preview += f" ... 等{len(chapter_list)}章"
                report_text = (
                    f"⚠️ 扫描范围内发现 {len(result)} 个章节结构不完整:\n\n"
                    f"  - 命中章节: {chapter_preview}"
                )
            else:
                report_text = "✅ 扫描范围内章节结构完整"
            self.report["deep_checks"]["structure"] = {
                "status": "✅ 通过" if not result else "⚠️ 发现问题",
                "chapters_affected": len(result),
                "report": report_text
            }
        except Exception as e:
            self.report["deep_checks"]["structure"] = {"status": "❌ 错误", "error": str(e)}
        
        # 3. 内容重复检测
        try:
            detector = DuplicateDetector(self.context)
            all_result = detector.scan_all_chapters()
            result = [
                item for item in all_result
                if (
                    isinstance(item, tuple)
                    and len(item) >= 2
                    and self._is_chapter_in_range(item[0], start_chapter, end_chapter)
                    and self._is_chapter_in_range(item[1], start_chapter, end_chapter)
                )
            ]
            if result:
                preview = []
                for item in result[:8]:
                    try:
                        preview.append(f"{int(item[0])}↔{int(item[1])}")
                    except (TypeError, ValueError):
                        continue
                preview_text = ", ".join(preview) if preview else "（章节对解析失败）"
                report_text = (
                    f"⚠️ 扫描范围内发现 {len(result)} 对相邻章节存在重复风险:\n\n"
                    f"  - 章节对: {preview_text}"
                )
            else:
                report_text = "✅ 扫描范围内未发现相邻章节内容重复"
            self.report["deep_checks"]["duplicate"] = {
                "status": "✅ 通过" if not result else "⚠️ 发现问题",
                "pairs_found": len(result),
                "report": report_text
            }
        except Exception as e:
            self.report["deep_checks"]["duplicate"] = {"status": "❌ 错误", "error": str(e)}
        
        # 4. 一致性检测（仅供参考，不作为必须修复的问题）
        try:
            validator = ConsistencyValidator(self.context)
            all_result = validator.scan_all_chapters()
            result = [
                item for item in all_result
                if (
                    isinstance(item, tuple)
                    and len(item) >= 1
                    and self._is_chapter_in_range(item[0], start_chapter, end_chapter)
                )
            ]
            if result:
                chapter_nums = []
                for item in result:
                    try:
                        chapter_nums.append(int(item[0]))
                    except (TypeError, ValueError):
                        continue
                chapter_nums = sorted(set(chapter_nums))
                chapter_preview = ", ".join(str(x) for x in chapter_nums[:10])
                if len(chapter_nums) > 10:
                    chapter_preview += f" ... 等{len(chapter_nums)}章"
                report_text = (
                    f"⚠️ 扫描范围内发现 {len(chapter_nums)} 个章节存在一致性提示:\n\n"
                    f"  - 命中章节: {chapter_preview}"
                )
            else:
                report_text = "✅ 扫描范围内章节一致性良好"
            # 注意：一致性检测易产生误报，仅作提示用
            self.report["deep_checks"]["consistency"] = {
                "status": "ℹ️ 仅供参考" if result else "✅ 通过",
                "chapters_affected": len(result),
                "report": report_text,
                "note": "预告匹配检测易误报，建议人工复核"
            }
        except Exception as e:
            self.report["deep_checks"]["consistency"] = {"status": "❌ 错误", "error": str(e)}
        
    def _process_validator_result(self, key: str, result: Dict):
        """处理标准化验证器的结果"""
        status = "✅ 通过" if result.get("passed", False) else "⚠️ 需关注"
        score = f"{result.get('score', 0):.1f}%"
        
        self.report["checks"][key] = {
            "status": status,
            "score": score,
            "details": result
        }
        
        # 严重问题才加入顶层warnings
        if not result.get("passed", False):
            self.report["warnings"].append(f"{result.get('name')}未达标（得分：{score}）")

    def _check_blueprint_completeness(self, start_chapter: int, end_chapter: int):
        """检查蓝图完整性"""
        existing_chapters = self.context.get_existing_chapters()
        total_chapters = end_chapter - start_chapter + 1
        found_chapters = sum(1 for c in range(start_chapter, end_chapter + 1) if c in existing_chapters)
        
        completeness = found_chapters / total_chapters * 100 if total_chapters > 0 else 0
        
        self.report["checks"]["blueprint_completeness"] = {
            "status": "✅ 通过" if completeness >= 95 else "⚠️ 需关注",
            "score": f"{completeness:.1f}%",
            "found": found_chapters,
            "total": total_chapters
        }
        
        if completeness < 95:
            self.report["warnings"].append(f"蓝图完整率仅{completeness:.1f}%")

    def _generate_summary(self):
        """生成总结"""
        if self.report["warnings"]:
            self.report["passed"] = False
            self.report["recommendations"].append("建议在批量生成前处理上述警告")
        
        passed_checks = sum(1 for check in self.report["checks"].values() 
                          if check.get("status", "").startswith("✅"))
        total_checks = len(self.report["checks"])
        
        self.report["summary"] = {
            "passed_checks": passed_checks,
            "total_checks": total_checks,
            "warnings_count": len(self.report["warnings"]),
            "overall_status": "✅ 可以开始生成" if self.report["passed"] else "⚠️ 建议先处理警告"
        }
    
    def print_report(self, include_deep: bool = True):
        """打印检查报告"""
        import os
        novel_name = os.path.basename(self.filepath) if self.filepath else "小说"
        print("=" * 60)
        print(f"《{novel_name}》批量生成预检查报告")
        print("=" * 60)
        print(f"检查时间: {self.report['timestamp']}")
        
        print(f"\n📊 基础检查结果:")
        for key, check in self.report["checks"].items():
            print(f"  {key}: {check['status']} {check.get('score', '')}")
        
        # 深度检查结果
        if include_deep and self.report.get("deep_checks"):
            print(f"\n🔍 深度扫描结果:")
            for key, check in self.report["deep_checks"].items():
                status = check.get("status", "未知")
                print(f"  {key}: {status}")
                if "report" in check and "发现" in check.get("report", ""):
                    # 只打印报告的前几行
                    lines = check["report"].split("\n")[:5]
                    for line in lines:
                        print(f"    {line}")
            
        if self.report["warnings"]:
            print(f"\n⚠️ 警告 ({len(self.report['warnings'])}条):")
            for warning in self.report["warnings"]:
                print(f"  - {warning}")
        
        summary = self.report.get("summary", {})
        print(f"\n📋 总结:")
        print(f"  通过检查: {summary.get('passed_checks', 0)}/{summary.get('total_checks', 0)}")
        print(f"  {summary.get('overall_status', '未知')}")
        print("=" * 60)


def run_pre_check(filepath: str, start_chapter: int = 1, end_chapter: int = 400, 
                  print_report: bool = True, deep_scan: bool = False) -> Dict:
    """
    运行预检查
    
    Args:
        filepath: 项目路径
        start_chapter: 起始章节
        end_chapter: 结束章节
        print_report: 是否打印报告
        deep_scan: 是否运行深度扫描
    """
    checker = BatchPreChecker(filepath)
    report = checker.run_all_checks(start_chapter, end_chapter, deep_scan=deep_scan)
    if print_report:
        checker.print_report(include_deep=deep_scan)
    return report


if __name__ == "__main__":
    import sys as _sys
    
    if len(_sys.argv) > 1:
        filepath = _sys.argv[1]
    else:
        print("Usage: python batch_pre_checker.py <novel_folder>")
        _sys.exit(1)
    
    # 默认运行基础检查 + 深度扫描
    run_pre_check(filepath, start_chapter=1, end_chapter=400, deep_scan=True)
