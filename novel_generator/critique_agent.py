#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
毒舌读者评论员 (Critic Agent - "键盘侠"版)
专门负责在生成后进行"情绪价值"和"阅读体验"的极限压力测试。
v3.1: 增强独立性 — 反共识策略防止自评偏见 (Fix 1.3)
"""

import logging
import json
import re
from typing import Dict, Any, Optional
from llm_adapters import create_llm_adapter
from novel_generator.common import write_llm_interaction_log, set_llm_log_context

# 🆕 Fix 1.3: 反共识前缀 — 当用同一LLM时注入，强制对抗性思维
ANTI_CONSENSUS_PREFIX = """【⚠️ 独立评审模式】
你的角色是"反对派"。你的任务是找茬，而非认可。请遵守以下原则：
1. **假设这章是烂稿**：请带着"这章大概率是赶工之作"的偏见开始阅读
2. **反向推理**：如果你的第一反应是"还行"，请重新审视——你可能被洗脑了
3. **对标最高标准**：用你读过的最好的仙侠/玄幻扛鼎之作来比较，而非平均水平
4. **拒绝"虽然...但是..."句式**：不要先夸再贬，直击要害

"""

class PoisonousReaderAgent:
    """
    毒舌读者 Agent
    人设：S级网文老书虫，挑剔，毒舌，没耐心。
    职责：
    1. 喷水文：如果觉得注水，直接开喷。
    2. 找逻辑硬伤：反派降智？主角圣母？直接喷。
    3. 测爽点：看完这一章，如果没有"追更"的冲动，就是失败。
    """
    
    # 毒舌 Prompt
    CRITIC_PROMPT = """你是一位拥有20年书龄的【资深网文老书虫】。你阅书无数，眼光极高，嘴巴极毒。你最讨厌三件事：1. 剧情注水（骗钱）；2. 逻辑弱智（侮辱智商）；3. 仙侠文里冒出"数据流"（出戏）。

现在，请你试读以下这章新出的网文。请完全抛弃客套，用最犀利、最直白、甚至带点攻击性的语言（贴吧/书评区风格）进行点评。

【阅读内容】
{content}

【点评维度】
1. **期待感 (Hook)**：看完这章，我是否迫不及待想看下一章？如果我内心毫无波澜，甚至想弃书，请直说。
2. **信息密度 (Density)**：有没有废话？有没有为了凑字数而写的景物描写？有没有车轱辘话？
3. **逻辑智商 (Logic)**：角色是不是弱智？反派是不是无脑嘲讽？主角是不是圣母？
4. **爽点 (Cool Factor)**：这章爽不爽？憋屈不憋屈？
5. **沉浸感 (Immersion)**：⚠️严格检查【双轨叙事】执行情况！
   - **违规**：旁白或土著对话中出现科技词汇（如：系统、数据、下载、服务器、Bug、CPU、能量槽）。
   - **允许**：仅限【主角内心独白】或【系统面板】中出现上述词汇。
   - 判定：一旦在旁白中发现违规词，直接【拒收】并痛骂作者出戏！

【判定标准】
- **收货 (Pass)**：虽然有小毛病，但总体好看，我会追更。
- **拒收 (Reject)**：垃圾，退钱！我不看了。（注水、逻辑硬伤、或严重出戏）

【输出格式】(JSON)
{{
    "rating": "Pass/Reject",  // 只有这两个选项
    "score": 7.5, // 0-10分，低于6.0分建议直接切书
    "toxic_comment": "这章写的什么玩意？旁白居然说'下载功法'？在修仙界搞宽带呢？", // 毒舌短评
    "improvement_demand": "把所有出戏的科技词汇全部替换为仙侠术语（如'推演'、'传承'）！" // 修改要求
}}

请开始你的表演（点评）："""

    def __init__(self, llm_config: Dict[str, Any], is_independent: bool = False):
        """
        初始化毒舌读者
        :param llm_config: LLM配置
        :param is_independent: 是否使用独立LLM（非生成用同一模型）
        """
        self.llm_config = llm_config
        self.is_independent = is_independent
        self.llm_adapter = None
        if llm_config:
            try:
                self.llm_adapter = create_llm_adapter(
                    interface_format=llm_config.get('interface_format', 'openai'),
                    api_key=llm_config.get('api_key', ''),
                    base_url=llm_config.get('base_url', ''),
                    model_name=llm_config.get('model_name', ''),
                    temperature=0.8,  # 🆕 提高temperature增加评判多样性
                    max_tokens=500,
                    timeout=llm_config.get('timeout', 60)
                )
                mode_label = "独立模式" if is_independent else "共用模式(含反共识策略)"
                logging.info(f"😠 毒舌读者(Critic Agent) 已上线 [{mode_label}]，随时准备开喷。")
            except (RuntimeError, ValueError, TypeError, OSError) as e:
                logging.warning(f"毒舌读者初始化失败: {e}")

    def critique_chapter(
        self,
        content: str,
        *,
        chapter_num: Optional[int] = None,
        project_path: Optional[str] = None,
        stage: str = "critic_agent",
        iteration: Optional[int] = None,
    ) -> Dict[str, Any]:
        """对章节进行毒舌点评"""
        if not self.llm_adapter:
            return {
                "rating": "Pass",
                "score": 7.0,
                "toxic_comment": "（评论员未上线，默认好评）",
                "parse_failed": False,
            }

        try:
            if chapter_num is not None or project_path:
                set_llm_log_context(
                    project_path=project_path if project_path else None,
                    chapter_num=chapter_num if chapter_num is not None else None,
                    model_name=self.llm_config.get("model_name", ""),
                    interface_format=self.llm_config.get("interface_format", ""),
                )

            # 截取前3500字（避免超出上下文，一般一章也就3000字）
            truncated_content = content[:3500]
            prompt = self.CRITIC_PROMPT.format(content=truncated_content)
            
            # 🆕 Fix 1.3: 非独立模式时注入反共识前缀
            if not self.is_independent:
                prompt = ANTI_CONSENSUS_PREFIX + prompt
            
            response = self.llm_adapter.invoke(prompt)
            
            # 解析 JSON
            result = self._parse_json(response)
            if result:
                result = self._normalize_result(result)
                log_meta = {
                    "critic_mode": "independent" if self.is_independent else "shared_with_anti_consensus",
                    "rating": result.get("rating"),
                    "score": result.get("score"),
                    "parse_failed": bool(result.get("parse_failed", False)),
                }
                if iteration is not None:
                    log_meta["iteration"] = int(iteration)
                write_llm_interaction_log(
                    prompt=prompt,
                    response=str(response or ""),
                    stage=stage,
                    extra_meta=log_meta,
                )
                logging.info(f"😠 读者评价: [{result.get('rating')}] {result.get('toxic_comment')}")
                return result
            else:
                log_meta = {
                    "critic_mode": "independent" if self.is_independent else "shared_with_anti_consensus",
                    "rating": "Pass",
                    "score": 8.0,
                    "parse_failed": True,
                }
                if iteration is not None:
                    log_meta["iteration"] = int(iteration)
                write_llm_interaction_log(
                    prompt=prompt,
                    response=str(response or ""),
                    stage=stage,
                    extra_meta=log_meta,
                )
                logging.warning("毒舌读者输出解析失败，跳过本轮毒舌门控")
                return {
                    "rating": "Pass",
                    "score": 8.0,
                    "toxic_comment": "评审输出格式异常，已跳过本轮毒舌门控。",
                    "improvement_demand": "",
                    "parse_failed": True,
                }
                
        except (RuntimeError, ValueError, TypeError, OSError) as e:
            logging.error(f"毒舌点评出错: {e}")
            return {
                "rating": "Pass",
                "score": 8.0,
                "toxic_comment": f"点评系统出错，已跳过本轮毒舌门控: {e}",
                "improvement_demand": "",
                "parse_failed": True,
            }

    def _parse_json(self, text: str) -> Optional[Dict]:
        """鲁棒 JSON 提取：支持 markdown code block、单引号 JSON、行内噪声。"""
        try:
            if not text:
                return None

            raw = text.strip()

            # 优先提取 ```json ... ``` 或 ``` ... ``` 代码块
            block_match = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", raw, flags=re.IGNORECASE)
            if block_match:
                raw = block_match.group(1).strip()

            # 退化到首尾大括号切片
            if not raw.startswith("{") or not raw.endswith("}"):
                start = raw.find('{')
                end = raw.rfind('}')
                if start != -1 and end != -1 and start < end:
                    raw = raw[start:end + 1]

            # 先尝试标准 JSON
            try:
                parsed = json.loads(raw)
                return parsed if isinstance(parsed, dict) else None
            except json.JSONDecodeError:
                pass

            # 回退：将单引号键值对替换为双引号（保守替换）
            normalized = re.sub(r"(?<=\{|,)\s*'([^']+)'\s*:", r' "\1":', raw)
            normalized = re.sub(r":\s*'([^']*)'", r': "\1"', normalized)
            parsed = json.loads(normalized)
            return parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            pass
        return None

    def _normalize_result(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """归一化评分结果，避免异常值影响门控。"""
        data = dict(result or {})
        rating = str(data.get("rating", "Pass")).strip()
        if rating.lower() not in ("pass", "reject"):
            rating = "Pass"
        else:
            rating = "Reject" if rating.lower() == "reject" else "Pass"
        data["rating"] = rating

        try:
            score = float(data.get("score", 7.5))
        except (ValueError, TypeError):
            score = 7.5
        data["score"] = max(0.0, min(10.0, score))
        data["toxic_comment"] = str(data.get("toxic_comment", "")).strip()
        data["improvement_demand"] = str(data.get("improvement_demand", "")).strip()
        data["parse_failed"] = False
        return data
