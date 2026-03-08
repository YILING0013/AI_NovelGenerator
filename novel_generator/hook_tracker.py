# -*- coding: utf-8 -*-
"""
跨章悬念生命周期管理 (Hook Tracker)
追踪悬念/伏笔的埋设与回收，检测超期未回收的悬念，生成提醒prompt。
"""

import re
import json
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class HookTracker:
    """悬念/伏笔生命周期管理器"""
    
    REGISTRY_FILE = "hook_registry.json"
    DEFAULT_OVERDUE_THRESHOLD = 20  # 超过20章未回收视为超期
    
    # 悬念埋设关键词模式
    PLANT_PATTERNS = [
        r'(?:一个|这个)(?:谜团|秘密|疑问|悬念)',
        r'(?:究竟|到底)(?:是什么|为什么|怎么回事)',
        r'(?:日后|将来|以后|终有一天)(?:再|必)',
        r'(?:暗暗记|默默记|牢牢记)',
        r'(?:留下|埋下)(?:了)?(?:一个|这个)?(?:伏笔|隐患|种子)',
        r'此事(?:尚|还|并)(?:未|没)',
        r'(?:谁也)?(?:不知|没想到|没料到)',
        r'(?:这|那)(?:股|道|丝)(?:神秘|诡异|奇怪|异样)(?:的)?(?:力量|气息|感觉)',
    ]
    
    # 悬念回收关键词模式
    RESOLVE_PATTERNS = [
        r'(?:原来|终于|果然|竟然)(?:是|如此)',
        r'(?:谜底|真相|答案)(?:终于|最终)?(?:揭开|揭晓|大白)',
        r'(?:当初|那时|之前)(?:的)?(?:谜团|疑问|伏笔)',
        r'终于(?:明白|理解|知道|想通)(?:了)?(?:当初|那时)',
        r'一切(?:真相|谜团)(?:大白|揭晓)',
    ]
    
    def __init__(self, novel_path: str):
        self.novel_path = Path(novel_path)
        self.registry_file = self.novel_path / self.REGISTRY_FILE
        self._registry = self._load_registry()
    
    def _load_registry(self) -> Dict[str, Any]:
        """加载悬念注册表"""
        if self.registry_file.exists():
            try:
                with open(self.registry_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"加载悬念注册表失败: {e}")
        return {"hooks": [], "stats": {"total_planted": 0, "total_resolved": 0}}
    
    def _save_registry(self):
        """保存悬念注册表"""
        try:
            with open(self.registry_file, 'w', encoding='utf-8') as f:
                json.dump(self._registry, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存悬念注册表失败: {e}")
    
    def register_hooks(self, content: str, chapter_num: int):
        """
        从章节中提取并登记悬念
        """
        for pattern in self.PLANT_PATTERNS:
            matches = re.finditer(pattern, content)
            for match in matches:
                # 提取上下文
                start = max(0, match.start() - 30)
                end = min(len(content), match.end() + 30)
                context = content[start:end].replace('\n', ' ').strip()
                
                # 避免重复登记
                is_duplicate = any(
                    h.get('context', '')[:20] == context[:20] 
                    for h in self._registry["hooks"]
                    if h.get('planted_chapter') == chapter_num
                )
                if is_duplicate:
                    continue
                
                hook = {
                    "id": f"hook_{chapter_num}_{len(self._registry['hooks'])}",
                    "status": "open",
                    "planted_chapter": chapter_num,
                    "resolved_chapter": None,
                    "context": context,
                    "keyword": match.group(),
                    "planted_at": datetime.now().isoformat()
                }
                self._registry["hooks"].append(hook)
                self._registry["stats"]["total_planted"] += 1
                logger.info(f"🎣 登记悬念: 第{chapter_num}章 - '{context[:30]}...'")
        
        self._save_registry()
    
    def check_resolutions(self, content: str, chapter_num: int):
        """
        检测本章是否回收了旧悬念
        """
        resolved_count = 0
        for pattern in self.RESOLVE_PATTERNS:
            if re.search(pattern, content):
                # 尝试匹配最近的开放悬念
                for hook in self._registry["hooks"]:
                    if hook["status"] == "open":
                        # 检查悬念上下文中的关键词是否在回收段落中出现
                        hook_keywords = re.findall(r'[\u4e00-\u9fff]{2,4}', hook.get("context", ""))
                        if any(kw in content for kw in hook_keywords[:3]):
                            hook["status"] = "resolved"
                            hook["resolved_chapter"] = chapter_num
                            resolved_count += 1
                            self._registry["stats"]["total_resolved"] += 1
                            logger.info(f"✅ 悬念回收: {hook['context'][:30]}... (第{hook['planted_chapter']}→{chapter_num}章)")
                            break
        
        if resolved_count > 0:
            self._save_registry()
        return resolved_count
    
    def get_overdue_hooks(self, current_chapter: int, 
                          threshold: int = None) -> List[Dict]:
        """
        获取超期未回收的悬念
        """
        threshold = threshold or self.DEFAULT_OVERDUE_THRESHOLD
        overdue = []
        for hook in self._registry["hooks"]:
            if hook["status"] == "open":
                age = current_chapter - hook["planted_chapter"]
                if age >= threshold:
                    overdue.append({
                        "hook": hook,
                        "age": age,
                        "urgency": "critical" if age > threshold * 2 else "warning"
                    })
        
        return sorted(overdue, key=lambda x: x["age"], reverse=True)
    
    def generate_reminder_prompt(self, current_chapter: int) -> str:
        """
        生成悬念提醒prompt，注入到下一章生成中
        """
        overdue = self.get_overdue_hooks(current_chapter)
        if not overdue:
            return ""
        
        lines = ["\n【🎣 悬念回收提醒】以下伏笔已埋设较久，请考虑在近期章节中回收："]
        for item in overdue[:5]:  # 最多提醒5个
            hook = item["hook"]
            urgency_icon = "🔴" if item["urgency"] == "critical" else "🟡"
            lines.append(
                f"  {urgency_icon} 第{hook['planted_chapter']}章埋设 "
                f"(已{item['age']}章): {hook['context'][:40]}..."
            )
        
        return "\n".join(lines)
    
    def get_stats(self) -> Dict[str, Any]:
        """获取悬念统计"""
        open_hooks = sum(1 for h in self._registry["hooks"] if h["status"] == "open")
        resolved_hooks = sum(1 for h in self._registry["hooks"] if h["status"] == "resolved")
        return {
            "total": len(self._registry["hooks"]),
            "open": open_hooks,
            "resolved": resolved_hooks,
            "resolution_rate": resolved_hooks / max(len(self._registry["hooks"]), 1)
        }
