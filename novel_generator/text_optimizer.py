
import json
import logging
import re
from pathlib import Path
from typing import Optional, Dict, Any

from chapter_quality_analyzer import ChapterQualityAnalyzer
from llm_adapters import create_llm_adapter

# Configure logging if not already configured
if not logging.getLogger().handlers:
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class ChapterTextOptimizer:
    def __init__(self, novel_path: str, config_path: str = "config.json"):
        self.novel_path = Path(novel_path)
        self.analyzer = ChapterQualityAnalyzer(novel_path)
        self.config = self._load_config(config_path)
        self.llm = self._init_llm()

    def _load_config(self, config_path: str) -> dict:
        # Assuming config is in the project root or passed as full path
        # If running from library, we might need to find project root or use a config manager
        # For now, simplistic approach compatible with previous script
        if os.path.isabs(config_path):
             path = Path(config_path)
        else:
             # Try to find config relative to CWD first, then project root
             path = Path(config_path)
             if not path.exists():
                 # Fallback: try 2 levels up from this file (assuming strict structure)
                 path = Path(__file__).parent.parent / config_path
        
        if path.exists():
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {} 

    def _init_llm(self):
        # Determine which config to use (defaulting to final_chapter_llm)
        llm_choice = self.config.get("choose_configs", {}).get("final_chapter_llm", "")
        if not llm_choice:
            # Fallback to first available
            llm_configs = self.config.get("llm_configs", {})
            if llm_configs:
                llm_choice = list(llm_configs.keys())[0]
            else:
                # raise ValueError("No LLM configs found")
                logging.warning("No LLM configs found, optimizer might fail.")
                return None
        
        llm_config = self.config["llm_configs"][llm_choice]
        logging.info(f"Optimizer using LLM: {llm_choice}")
        
        return create_llm_adapter(
            interface_format=llm_config.get("interface_format", "OpenAI"),
            base_url=llm_config.get("base_url", ""),
            model_name=llm_config.get("model_name", ""),
            api_key=llm_config.get("api_key", ""),
            temperature=0.7, # Slightly creative but controlled
            max_tokens=llm_config.get("max_tokens", 4000),
            timeout=llm_config.get("timeout", 600)
        )

    def _get_chapter_path(self, chapter_num: int) -> Optional[Path]:
        # Scan chapters directory for the file
        chapters_dir = self.novel_path / "chapters"
        if not chapters_dir.exists():
            return None
            
        for file in chapters_dir.iterdir():
            if file.name.startswith(f"chapter_{chapter_num}_") or file.name == f"chapter_{chapter_num}.txt":
                return file
        return None

    def optimize_content(self, content: str, chapter_num: int, target_score: float = 8.5, target_word_count: int = 3000) -> str:
        """
        Directly optimize content string without reading/writing files.
        Returns optimized content or original content if no optimization needed/failed.
        """
        logging.info(f"Optimizing content for Chapter {chapter_num}... (Target Words: {target_word_count})")
        
        # 1. Analyze current state (Using analyze_content directly)
        original_scores = self.analyzer.analyze_content(content, target_word_count=target_word_count)
        overall_score = original_scores.get('综合评分', 0)
        logging.info(f"Current Overall Score: {overall_score:.2f}")
        
        if overall_score >= target_score:
            logging.info(f"Chapter {chapter_num} exceeds target score ({target_score}). No optimization needed.")
            return content

        try:
            # 2. Identify weakest link
            dimensions = {k: v for k, v in original_scores.items() if isinstance(v, (int, float)) and k not in ['综合评分', 'chapter_number', '字数', '题材综合分']}
            
            if '题材维度' in original_scores:
                genre_scores = original_scores['题材维度']
                if isinstance(genre_scores, dict):
                    for k, v in genre_scores.items():
                         if isinstance(v, (int, float)):
                             dimensions[f"题材_{k}"] = v
            
            if not dimensions:
                logging.warning("No valid dimensions found for optimization.")
                return content

            weakest_dim = min(dimensions, key=dimensions.get)
            weakest_score = dimensions[weakest_dim]
            logging.info(f"Weakest Dimension: {weakest_dim} ({weakest_score})")

        except Exception as e:
            logging.error(f"Error identifying weakest dimension: {e}")
            return content

        # 3. Construct Prompt
        prompt = self._construct_optimization_prompt(content, weakest_dim, original_scores)
        
        # 4. Generate Optimized Content
        logging.info("Requesting optimization from LLM...")
        if not self.llm:
             logging.error("LLM not initialized.")
             return content
             
        optimized_content = self.llm.invoke(prompt)
        
        if not optimized_content:
            logging.warning("LLM returned empty content. Optimization failed.")
            return content

        # Clean up markdown code blocks if any
        optimized_content = self._clean_llm_output(optimized_content)
        
        return optimized_content

    def optimize_chapter_file(self, chapter_num: int, target_score: float = 7.5):
        """
        Legacy method to optimize a file on disk.
        """
        chapter_path = self._get_chapter_path(chapter_num)
        if not chapter_path:
            logging.error(f"Chapter file not found for number {chapter_num}")
            return
        
        with open(chapter_path, 'r', encoding='utf-8') as f:
            content = f.read()
            
        optimized_content = self.optimize_content(content, chapter_num, target_score)
        
        if optimized_content != content:
            # Save backup
            backup_path = chapter_path.with_suffix('.txt.bak')
            with open(backup_path, 'w', encoding='utf-8') as f:
                f.write(content)
            logging.info(f"Original backed up to {backup_path.name}")
            
            # Save new content
            with open(chapter_path, 'w', encoding='utf-8') as f:
                f.write(optimized_content)
            logging.info(f"Optimized content saved to {chapter_path.name}")
            
            # Re-evaluate
            new_scores = self.analyzer.analyze_chapter(chapter_num)
            logging.info(f"New Overall Score: {new_scores.get('综合评分', 0):.2f}")

    def _construct_optimization_prompt(self, content: str, dimension: str, all_scores: dict = None) -> str:
        base_instruction = f"""
你是一位专业的网文编辑和作家。你的任务是重写以下小说章节，专门提升其【{dimension}】维度的质量。

当前章节在【{dimension}】维度评分偏低，需要针对性优化。
"""
        # 中文版优化指令（针对爽文特点）
        specific_instructions = {
            "剧情连贯性": """【优化要点】
1. 检查场景过渡是否自然，补充"因此"、"于是"等因果连接词
2. 删除跳跃式叙述，确保读者不会"掉线"
3. 如有时间/空间跳跃，需加入过渡段落
4. 确保人物行动有明确动机""",

            "角色一致性": """【优化要点】
1. 强化主角的核心人设特征（如冷静、腹黑、热血等）
2. 增加主角的内心独白，展现其思考方式
3. 确保配角言行符合其身份设定
4. 避免"工具人"表现，给重要配角独立动机""",

            "写作质量": """【优化要点】
1. 使用更丰富的修辞：比喻、拟人、排比
2. 变换句式长短，紧张时用短句，抒情时用长句
3. 增加感官描写：视觉、听觉、触觉、嗅觉
4. 删除口语化/网络用语，提升文学性""",

            "情感张力": """【优化要点】⭐核心维度
1. 增加冲突对抗感：正反双方拉扯
2. 用感官细节描绘紧张氛围（如"心跳如擂鼓"）
3. 关键时刻用短句加速节奏
4. 增加"爽点"密度：打脸、逆转、获得、震惊众人
5. 结尾设置钩子，吊读者胃口""",

            "架构遵循度": """【优化要点】
1. 确保本章事件符合总体剧情线
2. 检查是否遗漏了该章应有的关键情节点
3. 调整节奏与全书规划一致""",

            "设定遵循度": """【优化要点】
1. 补充修仙等级/功法名称等专有名词
2. 确保世界观规则前后一致
3. 增加设定细节的自然融入""",

            "系统机制": """【优化要点】
1. 增加系统提示/面板展示
2. 展示金手指对剧情的实际影响
3. 保持系统设定的一致性""",

            "题材_爽点": """【优化要点】⭐爽感核心
1. 强化打脸场景：让看不起主角的人吃瘪
2. 强化获得场景：主角获得资源/能力时的震撼感
3. 强化逆转场景：从绝境到翻盘的反差
4. 增加"众人震惊"的反应描写""",

            "题材_期待感": """【优化要点】
1. 埋下伏笔，暗示后续发展
2. 结尾设置悬念或钩子
3. 制造信息差：读者知道主角不知道，或反过来""",

            "题材_代入感": """【优化要点】
1. 增加主角的即时感受描写
2. 用第一人称视角的感官体验
3. 让读者产生"这就是我"的感觉""",

            "题材_节奏": """【优化要点】
1. 战斗场景用短句，加快节奏
2. 情感场景适当放缓但不拖沓
3. 避免大段无聊的说明性文字"""
        }

        instruction = specific_instructions.get(dimension, "提升叙事质量，增加情感冲击力和阅读爽感。")
        
        # Add improvement hints if available
        hints = all_scores.get('题材改进建议', []) if all_scores else []
        if hints:
            instruction += "\n\nAdditional Hints:\n" + "\n".join(f"- {h}" for h in hints)

        prompt = f"""
{base_instruction}

{instruction}

【重写规则】
1. 不要概括总结，必须重写完整章节正文
2. 保留原有剧情核心和事件，只提升表现力
3. 保持原有章节标题和序号
4. 只输出小说正文，不要任何前言后语、解释说明
5. 禁止使用Markdown符号（如**、##等）

【原章节内容】
{content}
"""
        return prompt

    def _clean_llm_output(self, text: str) -> str:
        # Remove ```markdown or ``` wrapper
        text = re.sub(r"^```\w*\n", "", text)
        text = re.sub(r"\n```$", "", text)
        return text.strip()
import os
