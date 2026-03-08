import json
import os
from typing import Dict, List
from novel_generator.validators.base import BaseValidator, ValidationContext
from novel_generator.core.rules import get_rules_config

class ForeshadowingValidator(BaseValidator):
    def __init__(self, context: ValidationContext):
        super().__init__(context)
        self.rules = get_rules_config()
        self.major_reversals = self._get_reversal_definitions()

    def _get_reversal_definitions(self) -> Dict:
        """加载反转定义（优先加载项目级配置，否则加载默认配置）"""
        # 1. 尝试加载项目级配置 (novel_corpus/config/foreshadowing_rules.json)
        # Assuming context has project path info, but validation context might just have filepath.
        # We'll look relative to the validation context root if possible, or fallback to default.
        
        # Default config path
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        default_config_path = os.path.join(base_dir, "config", "default_foreshadowing_rules.json")
        
        # Try to find novel specific config
        # context.filepath is usually the chapter file path. 
        # We try to find the novel root.
        novel_config_path = None
        if self.context.filepath:
             # Heuristic: traverse up to find 'Novel_architecture.txt' or similar marker
             current_dir = os.path.dirname(os.path.abspath(self.context.filepath))
             for _ in range(5): # Go up 5 levels max
                 check_path = os.path.join(current_dir, "foreshadowing_rules.json")
                 if os.path.exists(check_path):
                     novel_config_path = check_path
                     break
                 current_dir = os.path.dirname(current_dir)

        config_path = novel_config_path if novel_config_path else default_config_path
        
        try:
            if os.path.exists(config_path):
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    return config.get("major_reversals", {})
            else:
                return {} # Return empty if no config found
        except Exception as e:
            print(f"Error loading foreshadowing rules from {config_path}: {e}")
            return {}

    def validate(self) -> Dict:
        results = {
            "name": "反转伏笔验证",
            "passed": True,
            "issues": [],
            "warnings": [],
            "details": {}
        }
        
        reversals = self.major_reversals
        total_reversals = len(reversals)
        fully_foreshadowed = 0
        
        for name, info in reversals.items():
            required_fs = info["required_foreshadowing"]
            found_fs = 0
            
            for req in required_fs:
                chapter = req["chapter"]
                content = self.context.get_chapter_content(chapter)
                
                # 检查关键词
                keywords = info["keywords"]
                matches = [k for k in keywords if k in content] if content else []
                
                if len(matches) >= 2 or (content and "伏笔" in content):
                    found_fs += 1
                else:
                    results["issues"].append(f"反转【{name}】在第{chapter}章缺失伏笔：{req['content']}")
            
            score = found_fs / len(required_fs) * 100 if required_fs else 0
            if score >= 80:
                fully_foreshadowed += 1
                
            results["details"][name] = {
                "score": score,
                "passed": score >= 80
            }
            
        if total_reversals > 0:
            overall_score = fully_foreshadowed / total_reversals * 100
            results["score"] = overall_score
            results["passed"] = overall_score >= 50
            
        return results
