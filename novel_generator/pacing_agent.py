# -*- coding: utf-8 -*-
"""
节奏大师 (Rhythm Agent)
负责宏观把控小说节奏，防止爽点疲劳或剧情拖沓。
"""

import logging
import json
from typing import List, Dict, Any, Optional
from llm_adapters import create_llm_adapter
from novel_generator.common import clean_llm_output

class PacingAgent:
    """
    节奏控制 Agent
    
    核心逻辑：
    1. 分析最近 N 章的"情绪曲线"（压抑/爆发/平淡）。
    2. 如果连续高潮 -> 强制冷却（日常/整理收获）。
    3. 如果连续低谷 -> 强制冲突（引入危机）。
    4. 如果剧情停滞 -> 强制推进（时间跳跃/突发事件）。
    """
    
    ANALYSIS_PROMPT = """你是一位资深网文主编，擅长把控长篇小说的阅读节奏。请分析以下最近 {num_chapters} 章的内容摘要，评估当前的剧情节奏。

【输入摘要】
{summaries}

【评估维度】(0-10分)
1. **紧张度 (Tension)**：主角面临的生存压力或紧迫感。 (0=极其悠闲, 10=生死一线)
2. **剧情推进速度 (Velocity)**：主线剧情的进展速度。 (0=原地踏步/水字数, 10=信息量爆炸/大跨度)
3. **爽感指数 (Satisfaction)**：读者获得的即时满足感。 (0=憋屈/平淡, 10=极度兴奋)

【输出要求的 JSON 格式】
请**仅**输出以下 JSON 格式，严禁包含任何 Markdown 标记（如 ```json）或额外文字：
{{
    "tension_score": 8.5,
    "velocity_score": 6.0,
    "satisfaction_score": 7.0,
    "current_tone": "Despair",
    "pacing_diagnosis": "诊断内容请简短，不要超过50字",
    "next_chapter_directive": "Release"
}}

注意：
- current_tone 可选值: Despair, Joy, Calm, Anger, Mystery
- next_chapter_directive 可选值: Release(释放), Conflict(冲突), Accelerate(加速), Maintain(保持)
"""

    def __init__(self, llm_config: Dict[str, Any]):
        self.llm_config = llm_config
        self.llm_adapter = None
        if llm_config:
            try:
                self.llm_adapter = create_llm_adapter(
                    interface_format=llm_config.get('interface_format', 'openai'),
                    api_key=llm_config.get('api_key', ''),
                    base_url=llm_config.get('base_url', ''),
                    model_name=llm_config.get('model_name', ''),
                    temperature=0.1, # 降低温度以保证格式稳定
                    max_tokens=500,
                    timeout=llm_config.get('timeout', 60)
                )
                logging.info("🎵 节奏大师(Rhythm Agent) 已就位。")
            except Exception as e:
                logging.warning(f"节奏大师初始化失败: {e}")

    def analyze_pacing(self, recent_chapters: List[str]) -> Dict[str, Any]:
        """
        分析最近章节的节奏
        :param recent_chapters: 最近章节的文本列表
        :return: 分析结果字典
        """
        if not self.llm_adapter or not recent_chapters:
            return {}

        try:
            # 简单的摘要提取（取每章前200字和后200字）以节省Token
            summaries = []
            for i, txt in enumerate(recent_chapters):
                # 预处理文本，去除可能的干扰字符
                curr_txt = txt.replace('"', "'").replace('\n', ' ')
                if len(curr_txt) > 500:
                    summary = f"Ch -{len(recent_chapters)-i}: {curr_txt[:200]} ... {curr_txt[-200:]}"
                else:
                    summary = f"Ch -{len(recent_chapters)-i}: {curr_txt}"
                summaries.append(summary)
            
            combined_summary = "\n\n".join(summaries)
            prompt = self.ANALYSIS_PROMPT.format(
                num_chapters=len(recent_chapters),
                summaries=combined_summary
            )
            
            response = self.llm_adapter.invoke(prompt)
            # print(f"DEBUG RAW RESPONSE:\n{response}\n") # DEBUG - REMOVED for prod
            
            # 尝试直接解析
            result = self._parse_json(response)
            if not result:
                # 如果直接解析失败，尝试清洗后再解析
                result = self._parse_json(clean_llm_output(response))
            
            if result:
                # 记录日志但不打印到控制台干扰
                logging.info(f"🎵 节奏分析: 紧张度={result.get('tension_score')}, 指令={result.get('next_chapter_directive')}")
                return result
            else:
                logging.warning(f"节奏分析解析失败。Raw: {response[:100]}...")
                return {}
                
        except Exception as e:
            logging.error(f"节奏分析出错: {e}")
            return {}

    # ... get_pacing_guidance unchanged ...
    
    def get_pacing_guidance(self, analysis_result: Dict[str, Any]) -> str:
        """根据分析结果生成给下一章的指导建议"""
        if not analysis_result:
            return ""
            
        directive = analysis_result.get("next_chapter_directive", "Maintain")
        tension = analysis_result.get("tension_score", 5.0)
        diagnosis = analysis_result.get("pacing_diagnosis", "")
        
        guidance = ""
        
        if directive == "Release":
            guidance = f"""
【🔔 节奏控制：强制冷却】
系统检测到前文连续高压（紧张度 {tension}），为防止读者疲劳，本章必须进行【节奏舒缓】。
⚠️ **最高优先级原则**：必须在**严格遵守蓝图（Blueprint）核心剧情**的前提下执行本指令。
1. **调整策略**：如果蓝图是战斗，请侧重描写战斗后的收获、轻松的碾压、或战斗中的幽默互动，而非删改战斗本身。
2. **氛围引导**：侧重盘点收获、日常互动、情感温存。
3. **禁止事项**：避免营造令人绝望压抑的氛围。
诊断：{diagnosis}
"""
        elif directive == "Conflict":
            guidance = f"""
【🔔 节奏控制：强制增压】
系统检测到前文较为平淡（紧张度 {tension}），为防止读者弃书，本章必须【引入强冲突】。
⚠️ **最高优先级原则**：必须在**严格遵守蓝图（Blueprint）核心剧情**的前提下执行本指令。
1. **调整策略**：如果蓝图是日常，请在日常中埋下恐怖的伏笔、突发的危机预警、或人际关系的暗流涌动。
2. **氛围引导**：侧重压抑、紧迫、惊悚、悬疑。
3. **目标**：打破舒适区，让主角感到棘手。
诊断：{diagnosis}
"""
        elif directive == "Accelerate":
            guidance = f"""
【🔔 节奏控制：剧情加速】
系统检测到剧情推进缓慢，本章建议【加快节奏】。
⚠️ **最高优先级原则**：必须在**严格遵守蓝图（Blueprint）核心剧情**的前提下执行本指令。
1. **调整策略**：使用蒙太奇手法快速略过蓝图中不重要的过渡环节，将笔墨集中在蓝图规划的核心冲突点上。
2. **手段**：使用时间跳跃（"三个月后..."）、省略繁琐过程、直接切入结果。
诊断：{diagnosis}
"""
        
        return guidance

    def _parse_json(self, text: str) -> Optional[Dict]:
        """增强版 JSON 提取"""
        import re
        try:
            # 1. 尝试直接加载
            return json.loads(text)
        except json.JSONDecodeError:
            pass
            
        try:
            # 2. 提取最外层 {}
            match = re.search(r'\{.*\}', text, re.DOTALL)
            if match:
                json_str = match.group(0)
                # 修复常见的 JSON 错误 (如 trailing commas)
                json_str = re.sub(r',\s*\}', '}', json_str)
                return json.loads(json_str)
        except Exception:
            pass
            
        return None
