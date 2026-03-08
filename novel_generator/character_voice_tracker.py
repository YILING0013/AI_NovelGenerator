# -*- coding: utf-8 -*-
"""
角色声音一致性追踪器 (Character Voice Tracker)
追踪每个角色的语言特征（口癖、语气、句式），检测不同角色说话过于相似的问题。
"""

import re
import json
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional
from collections import Counter

logger = logging.getLogger(__name__)


class CharacterVoiceTracker:
    """角色声音指纹追踪器"""
    
    VOICE_DB_FILE = ".voice_fingerprints.json"
    
    # 常见语气词分类
    MODAL_PARTICLES = {
        "强势": ["哼", "哈", "呸", "嘁", "切"],
        "温和": ["呢", "吧", "啊", "呀", "嘛", "哦"],
        "傲慢": ["不过如此", "蝼蚁", "可笑", "区区", "也配"],
        "谨慎": ["或许", "可能", "也许", "似乎", "恐怕"],
        "热血": ["定要", "必须", "一定", "绝不", "誓要"],
    }
    
    def __init__(self, novel_path: str):
        self.novel_path = Path(novel_path)
        self.voice_db_file = self.novel_path / self.VOICE_DB_FILE
        self._voice_db = self._load_voice_db()
        self._architecture_profiles = self._load_architecture_profiles()
    
    def _load_voice_db(self) -> Dict[str, Any]:
        """加载语音指纹数据库"""
        if self.voice_db_file.exists():
            try:
                with open(self.voice_db_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except (OSError, json.JSONDecodeError) as e:
                logger.warning(f"加载语音指纹库失败: {e}")
        return {"characters": {}, "updated_chapter": 0}
    
    def _save_voice_db(self):
        """保存语音指纹数据库"""
        try:
            with open(self.voice_db_file, 'w', encoding='utf-8') as f:
                json.dump(self._voice_db, f, ensure_ascii=False, indent=2)
        except (OSError, json.JSONDecodeError) as e:
            logger.error(f"保存语音指纹库失败: {e}")
    
    def _load_architecture_profiles(self) -> Dict[str, Dict]:
        """从架构文件加载角色语言画像"""
        profiles = {}
        arch_file = self.novel_path / "architecture.json"
        if not arch_file.exists():
            arch_file = self.novel_path / "novel_architecture.txt"
        if arch_file.exists():
            try:
                content = arch_file.read_text(encoding='utf-8')
                # 尝试提取角色说话风格描述
                char_patterns = [
                    r'(?:角色|人物)[：:]\s*(\S{2,6}).*?(?:说话|语气|口头禅|性格)[：:]\s*(.+?)(?:\n|$)',
                    r'(\S{2,6}).*?(?:说话风格|语言特点)[：:]\s*(.+?)(?:\n|$)',
                ]
                for pattern in char_patterns:
                    matches = re.findall(pattern, content)
                    for name, style in matches:
                        profiles[name] = {"expected_style": style.strip()}
            except (OSError, UnicodeDecodeError) as e:
                logger.debug(f"加载架构角色画像失败: {e}")
        return profiles
    
    def extract_dialogues(self, content: str) -> Dict[str, List[str]]:
        """
        从章节内容中提取各角色的对话
        返回: {角色名: [对话1, 对话2, ...]}
        """
        dialogues = {}
        
        # 模式1: "XXX说道："..."" 或 "XXX道："...""
        pattern1 = r'(\S{2,6})(?:说道|道|喝道|冷笑道|怒道|笑道|叹道|低声道|沉声道)[：:]\s*[""「](.+?)[""」]'
        # 模式2: "..."XXX说 或 直接 "..."
        pattern2 = r'[""「](.+?)[""」]\s*(\S{2,6})(?:说|道|喊)'
        
        for match in re.finditer(pattern1, content):
            name, dialogue = match.group(1), match.group(2)
            name = name.strip()
            if name not in dialogues:
                dialogues[name] = []
            dialogues[name].append(dialogue)
        
        for match in re.finditer(pattern2, content):
            dialogue, name = match.group(1), match.group(2)
            name = name.strip()
            if name not in dialogues:
                dialogues[name] = []
            dialogues[name].append(dialogue)
        
        return dialogues
    
    def analyze_voice_features(self, dialogues: List[str]) -> Dict[str, Any]:
        """分析一组对话的语言特征"""
        if not dialogues:
            return {}
        
        all_text = "".join(dialogues)
        features = {
            "avg_length": sum(len(d) for d in dialogues) / len(dialogues),
            "modal_particles": {},
            "question_ratio": sum(1 for d in dialogues if '？' in d or '?' in d) / len(dialogues),
            "exclamation_ratio": sum(1 for d in dialogues if '！' in d or '!' in d) / len(dialogues),
            "total_dialogues": len(dialogues),
        }
        
        # 统计语气词类别
        for category, particles in self.MODAL_PARTICLES.items():
            count = sum(all_text.count(p) for p in particles)
            if count > 0:
                features["modal_particles"][category] = count
        
        return features
    
    def compute_similarity(self, features_a: Dict, features_b: Dict) -> float:
        """计算两个角色语音特征的相似度 (0-1)"""
        if not features_a or not features_b:
            return 0.0
        
        similarity = 0.0
        weights_total = 0.0
        
        # 1. 平均句长相似度 (权重0.3)
        len_a = features_a.get('avg_length', 0)
        len_b = features_b.get('avg_length', 0)
        if len_a > 0 and len_b > 0:
            len_sim = 1.0 - min(abs(len_a - len_b) / max(len_a, len_b), 1.0)
            similarity += 0.3 * len_sim
            weights_total += 0.3
        
        # 2. 语气词类别分布相似度 (权重0.4)
        particles_a = features_a.get('modal_particles', {})
        particles_b = features_b.get('modal_particles', {})
        all_categories = set(list(particles_a.keys()) + list(particles_b.keys()))
        if all_categories:
            overlap = sum(1 for c in all_categories if c in particles_a and c in particles_b)
            particle_sim = overlap / len(all_categories)
            similarity += 0.4 * particle_sim
            weights_total += 0.4
        
        # 3. 问句/感叹句比例相似度 (权重0.3)
        q_diff = abs(features_a.get('question_ratio', 0) - features_b.get('question_ratio', 0))
        e_diff = abs(features_a.get('exclamation_ratio', 0) - features_b.get('exclamation_ratio', 0))
        tone_sim = 1.0 - (q_diff + e_diff) / 2
        similarity += 0.3 * tone_sim
        weights_total += 0.3
        
        return similarity / weights_total if weights_total > 0 else 0.0
    
    def update_voice_db(self, content: str, chapter_num: int):
        """从新章节更新语音指纹库"""
        dialogues = self.extract_dialogues(content)
        
        for char_name, char_dialogues in dialogues.items():
            if len(char_dialogues) < 2:
                continue  # 对话太少不足以分析
            
            features = self.analyze_voice_features(char_dialogues)
            
            if char_name not in self._voice_db["characters"]:
                self._voice_db["characters"][char_name] = {
                    "features_history": [],
                    "latest_features": features,
                }
            
            char_data = self._voice_db["characters"][char_name]
            char_data["latest_features"] = features
            char_data["features_history"].append({
                "chapter": chapter_num,
                "features": features
            })
            # 最多保留最近20章的特征
            char_data["features_history"] = char_data["features_history"][-20:]
        
        self._voice_db["updated_chapter"] = chapter_num
        self._save_voice_db()
    
    def check_voice_consistency(self, content: str, chapter_num: int) -> List[str]:
        """
        检查章节中角色声音的一致性问题
        返回: 问题描述列表
        """
        issues = []
        dialogues = self.extract_dialogues(content)
        
        if len(dialogues) < 2:
            return issues
        
        # 计算当前章各角色的特征
        current_features = {}
        for char_name, char_dialogues in dialogues.items():
            if len(char_dialogues) >= 2:
                current_features[char_name] = self.analyze_voice_features(char_dialogues)
        
        # 检测1: 不同角色之间的相似度过高
        char_names = list(current_features.keys())
        for i in range(len(char_names)):
            for j in range(i + 1, len(char_names)):
                name_a, name_b = char_names[i], char_names[j]
                sim = self.compute_similarity(current_features[name_a], current_features[name_b])
                if sim > 0.8:
                    issues.append(
                        f"'{name_a}'和'{name_b}'的说话方式过于相似(相似度{sim:.0%})，"
                        f"建议赋予不同的语气/口癖/句式长度"
                    )
        
        # 检测2: 与历史特征偏离过大
        for char_name, features in current_features.items():
            if char_name in self._voice_db.get("characters", {}):
                history = self._voice_db["characters"][char_name].get("latest_features", {})
                if history:
                    drift = 1.0 - self.compute_similarity(features, history)
                    if drift > 0.5:
                        issues.append(
                            f"'{char_name}'本章说话风格与历史差异较大(偏移{drift:.0%})，"
                            f"请检查是否偏离人设"
                        )
        
        return issues
