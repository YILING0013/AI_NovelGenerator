#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
章节质量分析工具
8维度评分系统 - 支持关键词评分和LLM语义评分双模式
"""

import os
import re
import json
import logging
import statistics
import ast
import time
from pathlib import Path
from typing import Dict, List, Tuple, Any, Optional, Callable
from datetime import datetime

create_llm_adapter: Optional[Callable[..., Any]] = None
BaseLLMAdapter = Any
llm_available = False

# 尝试导入LLM适配器用于语义评分
try:
    from llm_adapters import BaseLLMAdapter, create_llm_adapter
    llm_available = True
except ImportError:
    logging.warning("LLM适配器不可用，将使用关键词评分模式")

# 🆕 8维度加权配置（S级网文标准版 - 侧重沉浸感和人物）
# 权重总和=1.0
DIMENSION_WEIGHTS = {
    "情感张力": 0.35,      # 核心！大幅提升，爽文根本
    "写作质量": 0.25,      # 核心！大幅提升，沉浸感
    "角色一致性": 0.20,    # 核心！人设不能崩
    "剧情连贯性": 0.05,    # 基础门槛 (由熔断机制保障，不占高分权重)
    "系统机制": 0.05,      # 辅助
    "设定遵循度": 0.05,    # 辅助
    "架构遵循度": 0.05,    # 基础门槛 (由熔断机制保障，不占高分权重)
    "字数达标率": 0.00     # (已废弃)
}


def calculate_weighted_score(scores: Dict[str, Any]) -> float:
    """根据维度权重计算加权综合分 (含一票否决权)"""
    
    # 1. 检查一票否决项 (Veto Power)
    # 只要这几项不及格 ( < 6.0 )，直接判定为废稿，强制重写。
    # 不再进行加权计算，直接返回不及格分数。
    veto_threshold = 6.0
    critical_dimensions = ["架构遵循度", "剧情连贯性", "角色一致性"]
    
    for dim in critical_dimensions:
        score = float(scores.get(dim, 7.0) or 7.0)
        if score < veto_threshold:
            logging.warning(f"⛔ 触发熔断: {dim} ({score}) 不及格，章节直接被打回。")
            # 直接返回该维度的低分，确保低于系统设定的重写阈值 (通常是 7.5 或 8.0)
            return min(score, 5.0) 

    # 2. 正常加权计算 (只计算通过门槛后的质量分)
    total = 0.0
    for dim, weight in DIMENSION_WEIGHTS.items():
        total += float(scores.get(dim, 7.0) or 7.0) * weight
    return round(total, 2)


# ============================================================
# 🆕 题材维度扩展器 - 根据小说题材动态加载额外评估维度
# ============================================================

class GenreDimensionExtender:
    """
    题材维度扩展器
    根据小说题材（如程序员穿越、系统流等）动态加载额外的质量评估维度
    """
    
    # 配置文件路径
    CONFIG_PATH = Path(__file__).parent / "config" / "genre_dimensions.json"
    
    def __init__(self, genre: Optional[str] = None):
        """
        初始化扩展器
        :param genre: 小说题材，如"程序员穿越"、"系统流"等
        """
        self.genre = genre
        self.config = self._load_config()
        self.genre_dimensions = self._get_genre_dimensions()
    
    def _load_config(self) -> Dict[str, Any]:
        """加载题材配置文件"""
        try:
            if self.CONFIG_PATH.exists():
                with open(self.CONFIG_PATH, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            logging.warning(f"加载题材配置失败: {e}")
        return {}
    
    def _get_genre_dimensions(self) -> Dict[str, Any]:
        """获取当前题材的维度配置"""
        if not self.genre or self.genre not in self.config:
            return {}
        return self.config.get(self.genre, {})
    
    def get_genre_scores(self, content: str) -> Dict[str, Dict[str, Any]]:
        """
        计算题材特定维度的评分
        :param content: 章节内容
        :return: {维度名: {"score": 分数, "weight": 权重, "details": 详情}}
        """
        if not self.genre_dimensions:
            return {}
        
        results = {}
        for dim_key, config in self.genre_dimensions.items():
            if not isinstance(config, dict) or "keywords" not in config and "names" not in config:
                continue
            
            score, details = self._calculate_dimension_score(content, config)
            results[dim_key] = {
                "name": config.get("name", dim_key),
                "score": score,
                "weight": config.get("weight", 0.05),
                "threshold": config.get("threshold", 0.5),
                "details": details,
                "improvement_hint": config.get("improvement_hint", "")
            }
        
        return results
    
    def _calculate_dimension_score(self, content: str, config: Dict[str, Any]) -> Tuple[float, str]:
        """计算单个维度的评分"""
        # 关键词检测
        keywords = config.get("keywords", [])
        names = config.get("names", [])
        min_count = config.get("min_count", config.get("min_mentions", 2))
        
        # 合并检测列表
        check_list = keywords + names
        
        if not check_list:
            return 1.0, "无检测项"
        
        # 统计出现次数
        total_count = sum(content.count(item) for item in check_list)
        
        # 评分：达到min_count则满分，否则按比例
        if total_count >= min_count * 2:
            score = 1.0
            details = f"检测到{total_count}处，超出预期"
        elif total_count >= min_count:
            score = 0.8 + 0.2 * (total_count - min_count) / min_count
            details = f"检测到{total_count}处，达到预期"
        elif total_count >= 1:
            score = 0.3 + 0.5 * total_count / min_count
            details = f"仅检测到{total_count}处，低于预期{min_count}处"
        else:
            score = 0.2
            details = f"未检测到相关内容"
        
        return round(score, 2), details
    
    def get_improvement_hints(self, scores: Dict[str, Dict[str, Any]]) -> List[str]:
        """获取低分维度的改进建议"""
        hints = []
        for dim_key, data in scores.items():
            if data["score"] < data["threshold"]:
                hint = data.get("improvement_hint", "")
                if hint:
                    hints.append(f"【{data['name']}】{hint}")
        return hints
    
    def calculate_genre_weighted_score(self, scores: Dict[str, Dict[str, Any]]) -> float:
        """计算题材维度的加权总分（0-10分制）"""
        if not scores:
            return 10.0  # 无题材维度时返回满分
        
        total_weight = sum(data["weight"] for data in scores.values())
        if total_weight == 0:
            return 10.0
        
        weighted_sum = sum(data["score"] * data["weight"] for data in scores.values())
        return round(weighted_sum / total_weight * 10, 2)
    
    @classmethod
    def detect_genre_from_architecture(cls, architecture_content: str) -> Optional[str]:
        """从架构文件自动检测小说题材"""
        # 题材关键词映射
        genre_keywords = {
            "程序员穿越": ["程序员", "代码", "穿越", "系统", "BUG", "调试"],
            "系统流": ["系统", "签到", "任务", "积分", "商城", "面板"],
            "都市修仙": ["都市", "现代", "修仙", "灵气复苏"],
            "玄幻": ["修炼", "境界", "功法", "灵力", "真元"]
        }
        
        best_genre = None
        best_score = 0
        
        for genre, keywords in genre_keywords.items():
            score = sum(1 for kw in keywords if kw in architecture_content)
            if score > best_score:
                best_score = score
                best_genre = genre
        
        return best_genre if best_score >= 2 else None


class LLMSemanticScorer:
    """LLM语义评分器 - 使用LLM进行深度语义评分"""
    
    # 8维度评分Prompt模板

    SCORING_PROMPT_WITH_CONTEXT = """你是一位资深网文主编（S级项目组），请结合【小说架构】和【本章大纲】，对以下章节进行"升维式"质量评分。

【核心参考资料】
=== 小说核心架构 (Architecture) ===
{architecture_context}

=== 本章设计大纲 (Blueprint) ===
{blueprint_context}

【章节内容 (Content)】
{content}

【评分维度说明 (S级标准)】
1. 剧情连贯性: 逻辑闭环，因果强关联，且必须符合本章大纲的剧情走向。
   已成立的后果、代价、未解问题、关系变化必须延续，禁止把已解决冲突当作全新冲突重炒。
2. 角色一致性: 必须符合架构中的人设标签，行为动机必须合理 (Allow合理的多视角，但必须服务于剧情)。
   若人物立场、关系亲疏、资源态度、伤势与代价发生变化，正文必须写出触发原因。
3. 写作质量: **信息密度与沉浸感**。拒绝水文，每一段描写都必须推进剧情或塑造人物；五感描写，Show Don't Tell。
4. 架构遵循度: 【一票否决项】必须严格执行本章大纲的核心事件，不得魔改结局或核心冲突。
   若正文选择延后某个大纲节点，必须能看出清晰的铺垫、阻力和后续回收方向。
5. 设定遵循度: 严密遵守架构中的力量体系与世界观，无设定冲突。
6. 字数达标率: 内容充实，节奏紧凑。
7. 情感张力: **冲突与期待感 (Hooks)**。极致张力，两难困境；**结尾必须有强有力的钩子（悬念/危机）**，让人迫不及待想看下一章。
8. 系统机制: 机制与剧情的化学反应，符合系统设定。

【评分标准】
- 9.0-10.0分 (神作预定)：完美还原大纲，节奏紧凑全程无尿点，结尾钩子极强。
- 8.0-8.9分 (精品/小爆)：故事完整，爽点清晰，未偏离大纲，有基本的期待感。
- 6.0-7.9分 (普通/及格)：逻辑通顺但平庸，信息密度低（有水文嫌疑），或钩子无力。
- 6.0分以下 (熔断/重写)：严重跑题 (魔改大纲)，人设崩坏 (OOC)，逻辑混乱，或全是废话水文。

【加分项 (Bonus)】
+0.5分：结尾的“断章”极其高明，制造了强烈的悬念。
+0.5分：在大纲基础上增加了精彩的细节发挥且无废话。

【扣分项 (Deductions)】
-2.0分：【严重】偏离本章大纲的核心事件 (如大纲说"赢了"，正文写"输了")。
-2.0分：【严重】核心人设崩坏 (如高智商主角突然降智)。
-1.0分：出现大量重复、无效的景物描写或心理活动（水文）。
-1.0分：结尾平淡如水，没有任何期待感。
-1.0分：前文已付出的伤势、代价、误会、关系变化在本章被无解释重置。
-0.5分：只制造新信息，不承接旧问题，导致章节像重开新剧情。

【输出格式】(严格按此JSON格式输出)
{{"剧情连贯性": 8.5, "角色一致性": 9.0, "写作质量": 9.2, "架构遵循度": 8.0, "设定遵循度": 8.5, "字数达标率": 9.0, "情感张力": 9.5, "系统机制": 8.5, "问题描述": "优点：战斗密度极高，结尾断在主角拔剑一刻，悬念拉满。不足：中间有一段关于云彩的描写略显冗余。", "修改建议": "请精简环境描写，直接进入战斗节奏。"}}

只允许输出一个JSON对象，禁止Markdown代码块、解释性前言、附加列表或任何额外文本。
所有评分字段必须是0-10之间的数字，可保留1位小数；`问题描述`与`修改建议`必须聚焦最关键的2-4个问题，优先给出最小修改成本的修复方向。

请开始评分："""

    SCORING_PROMPT = """你是一位资深网文主编（S级项目组），请对以下章节进行"升维式"质量评分。

【章节内容】
{content}

【评分维度说明 (S级标准)】
1. 剧情连贯性: 逻辑闭环（Logic），草蛇灰线，伏笔回收自然
   已成立的后果、代价、误会、关系变化需持续生效，禁止无解释重置。
2. 角色一致性: 立体演绎（Character），拒绝工具人，必须有潜台词和微表情
   人物行为必须由既有处境、欲望、压力源推动，不能只为推进情节强行行动。
3. 写作质量: **信息密度与沉浸感**。拒绝水文，追求“句句有干货”；五感描写，动态运镜。
4. 架构遵循度: 核心梗明确，推进主线
   即使未提供蓝图，也要检查本章是否承接前文遗留问题，而不是像新故事开局。
5. 设定遵循度: 世界观咬合严密，设定的视觉化呈现
6. 字数达标率: 内容充实，节奏紧凑
7. 情感张力: **冲突与期待感 (Hooks)**。极致张力，两难困境；**结尾必须有悬念（Hook）**。
8. 系统机制: 机制与剧情的化学反应，系统带来的压迫感/爽感

【评分标准】
- 9.0-10.0分 (神作预定)：全程无尿点，悬念设计大师级，文笔极具画面感。
- 8.0-8.9分 (精品/小爆)：故事完整，爽点清晰，描写合格。
- 6.0-7.9分 (普通/及格)：流水账，有水文嫌疑，钩子一般。
- 6.0分以下 (需重炼)：逻辑混乱，全是水词，毫无期待感。

【加分项 (Bonus)】(发现以下亮点请加分！)
+0.5分：结尾的“钩子”让人抓心挠肝，极其想看下一章。
+0.5分：极高的信息密度，没有一句废话。

【扣分项 (Deductions)】(只针对真正的低级错误)
-1.0分：逻辑硬伤。
-1.0分：大量无效的环境描写或重复的心理活动（水文）。
-0.5分：结尾平淡，不仅没有解决旧问题，也没抛出新问题。
-1.0分：前文已确认的代价、关系变化、资源归属或伤势状态被无解释推翻。
-0.5分：章节只堆新设定、不处理旧问题，导致连续性断裂。

【特别注意】
❌ **不要误判**：紧凑的节奏不代表不能写环境，但环境描写必须服务于氛围渲染！
❌ **不要死板**：钩子不一定是危机，也可以是即将到来的爽点（期待感）。

【输出格式】(严格按此JSON格式输出)
{{"剧情连贯性": 8.5, "角色一致性": 9.0, "写作质量": 9.2, "架构遵循度": 8.0, "设定遵循度": 8.5, "字数达标率": 9.0, "情感张力": 9.5, "系统机制": 8.5, "问题描述": "优点：节奏紧凑，结尾留白引人遐想。不足：前段对话略显拖沓。", "修改建议": "删减前段30%的无意义寒暄。"}}

只允许输出一个JSON对象，禁止Markdown代码块、前后解释、标题、列表或任何额外文本。
所有评分字段必须是0-10之间的数字，可保留1位小数；`问题描述`与`修改建议`必须简短、具体、可执行，优先指出最关键的2-4个问题。

请开始评分："""

    def __init__(self, llm_config: Optional[Dict[str, Any]], parse_failure_callback=None):
        """
        初始化LLM评分器
        :param llm_config: LLM配置字典，包含api_key, base_url, model_name等
        """
        self.llm_config = llm_config
        self.llm_adapter = None
        self.parse_failure_callback = parse_failure_callback
        self.last_parse_failure: Optional[Dict[str, Any]] = None
        
        adapter_factory = create_llm_adapter
        if llm_available and llm_config and adapter_factory is not None:
            try:
                self.llm_adapter = adapter_factory(
                    interface_format=str(llm_config.get('interface_format') or 'openai'),
                    api_key=str(llm_config.get('api_key') or ''),
                    base_url=str(llm_config.get('base_url') or ''),
                    model_name=str(llm_config.get('model_name') or ''),
                    temperature=0.3,  # 低温度以获得稳定评分
                    max_tokens=500,
                    timeout=int(llm_config.get('timeout') or 60)
                )
                logging.info("LLM语义评分器初始化成功")
            except Exception as e:
                logging.warning(f"LLM语义评分器初始化失败: {e}")
                self.llm_adapter = None
    
    def score_content(
        self,
        content: str,
        architecture_context: Optional[str] = None,
        blueprint_context: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        使用LLM对内容进行语义评分
        :param content: 章节内容
        :param architecture_context: 小说架构上下文（可选）
        :param blueprint_context: 本章大纲上下文（可选）
        :return: 8维度评分字典，失败返回None
        """
        if not self.llm_adapter:
            return None
        
        self.last_parse_failure = None
        try:
            # 分段抽样而非只看开头，避免忽略中后段和结尾钩子质量
            sampled_content = self._build_scoring_sample(content)
            
            prompt = ""
            if architecture_context or blueprint_context:
                prompt = self.SCORING_PROMPT_WITH_CONTEXT.format(
                    architecture_context=architecture_context or "（未提供架构信息）",
                    blueprint_context=blueprint_context or "（未提供本章大纲）",
                    content=sampled_content
                )
            else:
                prompt = self.SCORING_PROMPT.format(content=sampled_content)
            
            response = self.llm_adapter.invoke(prompt)
            
            if not response:
                logging.warning("LLM评分返回空响应")
                return None
            
            # 解析JSON响应
            scores = self._parse_scores(response)
            if scores:
                logging.debug(f"LLM语义评分成功: {scores}")
                return scores
            else:
                logging.warning(f"LLM评分解析失败: {response[:200]}")
                self._record_parse_failure(
                    reason="score_json_parse_failed",
                    raw_response=response,
                    prompt_preview=prompt[:800],
                )
                return None
                
        except Exception as e:
            logging.warning(f"LLM语义评分异常: {e}")
            self._record_parse_failure(
                reason=f"score_exception:{type(e).__name__}",
                raw_response=str(e),
                prompt_preview=content[:400],
            )
            return None

    def _record_parse_failure(self, reason: str, raw_response: str, prompt_preview: str = "") -> None:
        llm_config: Dict[str, Any] = self.llm_config or {}
        detail = {
            "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
            "reason": reason,
            "model_name": llm_config.get("model_name", ""),
            "interface_format": llm_config.get("interface_format", ""),
            "raw_response_preview": (raw_response or "")[:2000],
            "prompt_preview": (prompt_preview or "")[:1200],
        }
        self.last_parse_failure = detail
        if callable(self.parse_failure_callback):
            try:
                self.parse_failure_callback(detail)
            except Exception:
                pass
    
    def _parse_scores(self, response: str) -> Optional[Dict[str, float]]:
        """解析LLM返回的评分JSON"""
        candidates = self._extract_json_candidates(response)
        for candidate in candidates:
            parsed = self._try_parse_candidate(candidate)
            if parsed is not None:
                return parsed
        regex_parsed = self._fallback_parse_scores_by_regex(response)
        if regex_parsed is not None:
            logging.warning("评分JSON解析失败，已使用正则兜底提取维度分数。")
            return regex_parsed
        logging.warning(f"评分JSON解析错误: 无有效JSON | Raw: {response[:120]}...")
        return None

    def _build_scoring_sample(self, content: str, max_chars: int = 9000) -> str:
        """构建用于评分的分段样本，覆盖开头/中段/结尾。"""
        if not content:
            return ""
        if len(content) <= max_chars:
            return content

        seg = max_chars // 3
        mid_start = max(0, (len(content) // 2) - (seg // 2))
        mid_end = min(len(content), mid_start + seg)
        return (
            "【开头片段】\n"
            + content[:seg]
            + "\n\n【中段片段】\n"
            + content[mid_start:mid_end]
            + "\n\n【结尾片段】\n"
            + content[-seg:]
        )

    def _extract_json_candidates(self, response: str) -> List[str]:
        candidates: List[str] = []
        if not response:
            return candidates

        if '{' in response and '}' in response:
            candidates.append(response[response.find('{'):response.rfind('}') + 1])

        fence_pattern = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.IGNORECASE)
        for block in fence_pattern.findall(response):
            block = block.strip()
            if '{' in block and '}' in block:
                candidates.append(block[block.find('{'):block.rfind('}') + 1])

        return candidates

    def _sanitize_json_like(self, text: str) -> str:
        fixed = text.strip()
        fixed = fixed.replace('【', '"').replace('】', '"')
        fixed = fixed.replace('“', '"').replace('”', '"')
        fixed = fixed.replace('，', ',').replace('：', ':')
        fixed = re.sub(r",\s*([}\]])", r"\1", fixed)
        return fixed

    def _try_parse_candidate(self, candidate: str) -> Optional[Dict[str, float]]:
        for parser in (json.loads, ast.literal_eval):
            try:
                obj = parser(candidate)
                if isinstance(obj, dict):
                    return self._validate_and_normalize_scores(obj)
            except Exception:
                pass

        sanitized = self._sanitize_json_like(candidate)
        for parser in (json.loads, ast.literal_eval):
            try:
                obj = parser(sanitized)
                if isinstance(obj, dict):
                    return self._validate_and_normalize_scores(obj)
            except Exception:
                pass
        return None

    def _fallback_parse_scores_by_regex(self, response: str) -> Optional[Dict[str, float]]:
        """当JSON解析失败时，尝试从文本中提取8维分数。"""
        if not response:
            return None
        required_dims = ["剧情连贯性", "角色一致性", "写作质量", "架构遵循度",
                         "设定遵循度", "字数达标率", "情感张力", "系统机制"]

        extracted: Dict[str, float] = {}
        for dim in required_dims:
            pattern = rf"{re.escape(dim)}\s*['\"]?\s*[:：]\s*([0-9]+(?:\.[0-9]+)?)"
            match = re.search(pattern, response)
            if match:
                try:
                    extracted[dim] = float(match.group(1))
                except Exception:
                    continue

        if len(extracted) < 6:
            return None
        return self._validate_and_normalize_scores(extracted)

    def _validate_and_normalize_scores(self, scores: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """验证并标准化分数"""
        try:
            # 验证所有维度都存在
            required_dims = ["剧情连贯性", "角色一致性", "写作质量", "架构遵循度", 
                           "设定遵循度", "字数达标率", "情感张力", "系统机制"]
            
            # 兼容性处理：如果缺失某些维度，赋予默认值7.0
            for dim in required_dims:
                if dim not in scores:
                    scores[dim] = 7.0
            
            # 确保分数在1-10范围内
            result: Dict[str, Any] = {}
            for dim in required_dims:
                val = float(scores.get(dim, 7.0) or 7.0)
                result[dim] = max(1.0, min(10.0, val))
                
            # 保留非数值字段（如建议和描述）
            for k, v in scores.items():
                if k not in required_dims:
                    result[k] = v
                    
            return result
        except Exception as e:
            logging.warning(f"分数验证失败: {e}")
            return None


class ChapterQualityAnalyzer:
    def __init__(self, novel_path: str, llm_config: Optional[Dict[str, Any]] = None, genre: Optional[str] = None):
        self.novel_path = Path(novel_path)
        self.chapters_path = self.novel_path / "chapters"
        self.architecture_file = self.novel_path / "Novel_architecture.txt"
        self.directory_file = self.novel_path / "Novel_directory.txt"

        # 加载架构和目录信息
        self.architecture_content = self._load_file(self.architecture_file)
        self.directory_content = self._load_file(self.directory_file)

        # 从架构文件动态提取角色名（如果可能）
        self.main_characters = self._extract_characters_from_architecture()

        # 从架构文件动态提取设定
        self.core_concepts = self._extract_concepts_from_architecture()
        self.cultivation_ranks = self._extract_cultivation_ranks()

        # LLM语义评分器（可选）
        self.llm_scorer = None
        self._parse_failure_log_file = self.novel_path / "llm_logs" / "quality_score_parse_failures.jsonl"
        if llm_config:
            self.llm_scorer = LLMSemanticScorer(
                llm_config,
                parse_failure_callback=self._log_llm_parse_failure
            )
        
        # 是否启用LLM评分
        self.use_llm_scoring = llm_config is not None and self.llm_scorer and self.llm_scorer.llm_adapter

        # 🆕 题材维度扩展器
        # 如果未指定题材，尝试从架构文件自动检测
        if genre is None and self.architecture_content:
            genre = GenreDimensionExtender.detect_genre_from_architecture(self.architecture_content)
            if genre:
                logging.info(f"自动检测到小说题材: {genre}")
        
        self.genre = genre
        self.genre_extender = GenreDimensionExtender(genre) if genre else None

        # 评分统计
        self.scores = {}

    def _log_llm_parse_failure(self, detail: Dict[str, Any]) -> None:
        """记录评分解析失败详情，便于排查模型输出格式问题。"""
        try:
            self._parse_failure_log_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self._parse_failure_log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(detail, ensure_ascii=False) + "\n")
            logging.warning(
                "⚠️ 评分解析失败已记录: %s",
                str(self._parse_failure_log_file)
            )
        except Exception as e:
            logging.debug(f"写入评分解析失败日志异常: {e}")

    def _load_file(self, file_path: Path) -> str:
        """安全加载文件内容"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception as e:
            print(f"加载文件失败 {file_path}: {e}")
            return ""

    def _extract_characters_from_architecture(self) -> List[str]:
        """从架构文件中动态提取角色名"""
        characters = []
        
        if not self.architecture_content:
            return characters
        
        # 尝试匹配常见的角色定义模式
        patterns = [
            r'主角[：:]\s*([^\s（(—-]+)',  # 匹配 "主角：张三"
            r'姓名[：:]\s*([^\s（(—-]+)',  # 匹配 "姓名：张三"
            r'【主角】\s*([^\s（(—-]+)',  # 匹配 "【主角】张三"
            r'protagonist[：:]\s*([^\s（(—-]+)',
            r'角色[一二三四五0-9]+[：:]\s*([^\s（(—-]+)', # 匹配 "角色一：张三"
            r'\*\*姓名[：:]\*\*\s*([^\s（(—-]+)', # 匹配 "**姓名：** 张三"
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, self.architecture_content)
            # 清理提取的名字
            clean_matches = [m.strip(" *").split()[0] for m in matches if m.strip()]
            characters.extend(clean_matches)
        
        # 去重并限制数量
        # 过滤掉一些明显不是名字的词
        exclude_words = {'无', '待定', '男', '女', '未知'}
        characters = [c for c in list(set(characters)) if c not in exclude_words and len(c) > 1][:10]
        
        if not characters:
            # 如果没有提取到，返回空列表
            logging.debug("未从架构文件提取到角色名")
        else:
            logging.info(f"从架构文件提取到角色: {characters}")
            
        return characters

    def _extract_concepts_from_architecture(self) -> List[str]:
        """从架构文件动态提取核心概念"""
        default_concepts = [
            '修炼', '灵力', '境界', '功法', '金丹', '元婴', '化神',
            '灵气', '修真', '仙法', '道法', '法术', '真元', '经脉', '丹田',
            '突破', '晋级', '渡劫', '飞升', '神通', '法宝', '丹药'
        ]
        
        if not self.architecture_content:
            return default_concepts

        extracted = []
        # 提取核心设定要素中的关键词
        if "**核心设定要素**" in self.architecture_content:
            section = self.architecture_content.split("**核心设定要素**")[1].split("#===")[0]
            # 提取加粗的词
            matches = re.findall(r'\*\*([^\*]+)\*\*', section)
            extracted.extend(matches)
            
        # 提取五脉名称
        wumai = ['道脉', '巫脉', '魔脉', '释脉', '儒脉']
        extracted.extend(wumai)
        
        combined = list(set(default_concepts + extracted))
        logging.info(f"动态加载核心概念: {len(combined)} 个")
        return combined

    def _extract_cultivation_ranks(self) -> List[str]:
        """从架构文件动态提取修炼境界"""
        default_ranks = ['练气', '筑基', '金丹', '元婴', '化神', '炼虚', '合体', '大乘', '渡劫']
        
        if not self.architecture_content:
            return default_ranks
            
        extracted = []
        # 查找类似 "专用境界：道童 → 练气..." 的行
        matches = re.findall(r'专用境界[:：]\s*(.+)', self.architecture_content)
        for match in matches:
            ranks = [r.strip() for r in re.split(r'[→->]', match) if r.strip()]
            extracted.extend(ranks)
            
        # 查找类似 "九境修仙体系" 的段落
        matches_nums = re.findall(r'\d+\.\s*\*\*([^\*]+)\*\*（Vol', self.architecture_content)
        # 提取 "炼气期" 中的 "炼气"
        cleaned_nums = [m.replace('期', '') for m in matches_nums]
        extracted.extend(cleaned_nums)

        if not extracted:
            return default_ranks
            
        combined = list(set(default_ranks + extracted))
        logging.info(f"动态加载修炼境界: {combined}")
        return combined

    def analyze_plot_coherence(self, content: str) -> float:
        """分析剧情连贯性 (1-10分)"""
        score = 5.0

        # 检查核心概念出现频率
        concept_count = sum(1 for concept in self.core_concepts if concept in content)
        score += min(concept_count * 0.3, 3.0)  # 最多+3分

        # 检查逻辑连接词
        logic_indicators = ['因为', '所以', '于是', '接着', '随后', '突然', '然而', '不过']
        logic_density = sum(content.count(indicator) for indicator in logic_indicators)
        score += min(logic_density * 0.05, 2.0)  # 最多+2分

        return min(score, 10.0)

    def analyze_character_consistency(self, content: str) -> float:
        """分析角色一致性 (1-10分)"""
        score = 5.0

        # 检查主角出现频率和行为
        for character in self.main_characters:
            if character in content:
                # 基础分：角色出现
                score += 0.5

                # 检查角色相关动作和对话
                action_indicators = ['说', '道', '想', '看', '走', '来', '去', '施展', '运起']
                action_count = sum(content.count(f"{character}{indicator}") for indicator in action_indicators)
                score += min(action_count * 0.1, 1.0)

        return min(score, 10.0)

    def analyze_writing_quality(self, content: str) -> float:
        """分析写作质量 (1-10分)"""
        if not content.strip():
            return 1.0

        score = 5.0

        # 字数评估
        word_count = len(content)
        if word_count >= 1000:
            score += 2.0
        elif word_count >= 500:
            score += 1.0
        elif word_count >= 200:
            score += 0.5

        # 段落结构
        paragraphs = [p.strip() for p in content.split('\n') if p.strip()]
        if len(paragraphs) >= 5:
            score += 1.0
        elif len(paragraphs) >= 3:
            score += 0.5

        # Expanded descriptive lexicon
        description_words = [
            '美丽', '壮观', '震撼', '恐怖', '温暖', '冰冷', '耀眼', '昏暗', 
            '璀璨', '漆黑', '狰狞', '圣洁', '诡异', '宏大', '细腻', '深邃',
            '苍凉', '炽热', '阴森', '磅礴', '绚丽', '破败', '晶莹', '浑浊'
        ]
        desc_count = sum(content.count(word) for word in description_words)
        score += min(desc_count * 0.2, 2.0)

        return min(score, 10.0)

    def analyze_architecture_adherence(self, content: str) -> float:
        """分析架构遵循度 (1-10分)"""
        score = 5.0

        if not self.architecture_content:
            return score

        # 1. 检查核心概念 (Dynamic)
        if hasattr(self, 'core_concepts') and self.core_concepts:
            concept_hits = sum(1 for c in self.core_concepts if c in content)
            # Cap at 3.0 points for concepts
            score += min(concept_hits * 0.2, 3.0)
            
        # 2. 检查主要角色 (Dynamic)
        if hasattr(self, 'main_characters') and self.main_characters:
            char_hits = sum(1 for c in self.main_characters if c in content)
            score += min(char_hits * 0.5, 2.0)
            
        return min(score, 10.0)

    def analyze_setting_adherence(self, content: str) -> float:
        """分析设定遵循度 (1-10分)"""
        score = 5.0

        # 1. Check WorldView/Core Concepts (Dynamic)
        # Use dynamically loaded core concepts if available
        if hasattr(self, 'core_concepts') and self.core_concepts:
            concept_hits = sum(1 for c in self.core_concepts if c in content)
            score += min(concept_hits * 0.3, 3.0)
        else:
             # Fallback to generic terms
            world_concepts = ['修真界', '门派', '师傅', '弟子', '师兄', '师姐', '灵石', '法宝']
            concept_count = sum(1 for concept in world_concepts if concept in content)
            score += min(concept_count * 0.4, 3.0)

        # 2. Check Cultivation System (Dynamic)
        cultivation_terms = self.cultivation_ranks
        cultivation_count = sum(content.count(term) for term in cultivation_terms)
        score += min(cultivation_count * 0.2, 2.0)

        return min(score, 10.0)

    def analyze_word_count_achievement(self, content: str, target_word_count: int = 3000) -> float:
        """分析字数达标率 (1-10分)"""
        word_count = len(content)
        
        # If target provided, score based on percentage of target
        if target_word_count > 0:
            ratio = word_count / target_word_count
            if ratio >= 1.0:
                return 10.0
            elif ratio >= 0.9:
                return 9.0 + (ratio - 0.9) * 10
            elif ratio >= 0.8:
                return 8.0 + (ratio - 0.8) * 10
            elif ratio >= 0.6:
                return 6.0 + (ratio - 0.6) * 10
            else:
                return max(1.0, ratio * 10)
        
        # Fallback to default hardcoded constraints if no target
        if word_count >= 3000:
            return 10.0
        elif word_count >= 2500:
            return 9.0 + (word_count - 2500) / 500
        elif word_count >= 2000:
            return 8.0 + (word_count - 2000) / 500
        elif word_count >= 1500:
            return 7.0 + (word_count - 1500) / 500
        elif word_count >= 1000:
            return 6.0 + (word_count - 1000) / 500
        elif word_count >= 800:
            return 5.0
        else:
            return max(1.0, word_count / 200)

    def analyze_emotional_tension(self, content: str) -> float:
        """分析情感张力 (1-10分)"""
        score = 5.0

        # Expanded Conflict Lexicon
        conflict_words = [
            '战斗', '争斗', '冲突', '危险', '生死', '仇恨', '愤怒', '恐惧', '绝望',
            '杀意', '威压', '对峙', '危机', '紧迫', '爆发', '毁灭', '重创', '濒死'
        ]
        conflict_count = sum(content.count(word) for word in conflict_words)
        score += min(conflict_count * 0.3, 3.0)

        # Expanded Emotion Lexicon
        emotion_words = [
            '激动', '感动', '悲伤', '高兴', '惊讶', '紧张', '放松', '狂喜', 
            '绝望', '憧憬', '懊悔', '不甘', '冷漠', '戏谑', '贪婪', '敬畏'
        ]
        emotion_count = sum(content.count(word) for word in emotion_words)
        score += min(emotion_count * 0.2, 2.0)

        return min(score, 10.0)

    def analyze_system_mechanism(self, content: str) -> float:
        """分析系统机制 (1-10分)"""
        score = 5.0

        # Dynamic System/Magic Terms check
        # Prefer dynamically loaded concepts, fallback to defaults if empty
        if hasattr(self, 'core_concepts') and self.core_concepts:
            # Filter for terms that likely represent system/magic mechanics
            # (Assuming core_concepts contains a mix, we use all of them broadly for mechanism adherence)
            mech_hits = sum(1 for c in self.core_concepts if c in content)
            score += min(mech_hits * 0.3, 4.0)
        else:
             # Fallback if no dynamic concepts found
            system_terms = ['灵力', '真元', '法力', '功法', '武技', '法术', '神通', '领域']
            system_count = sum(content.count(term) for term in system_terms)
            score += min(system_count * 0.4, 3.0)

        # Dynamic Element/Attribute check (if part of architecture)
        # Scan content for common elemental words effectively
        common_elements = ['金', '木', '水', '火', '土', '风', '雷', '光', '暗', '阴', '阳']
        element_count = sum(content.count(element) for element in common_elements)
        score += min(element_count * 0.2, 1.0) # Lower weight for generic elements

        return min(score, 10.0)

    def analyze_content(
        self,
        content: str,
        use_llm: Optional[bool] = None,
        target_word_count: int = 3000,
        chapter_num: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        直接分析文本内容（无需保存文件）
        :param content: 章节内容
        :param use_llm: 是否使用LLM评分（None表示使用默认设置）
        :param target_word_count: 目标字数（默认3000）
        :param chapter_num: 章节号（用于获取大纲上下文）
        :return: 8维度评分字典，失败返回None
        """
        if not content:
            return {dimension: 1.0 for dimension in self.get_dimension_names()}

        # 决定是否使用LLM评分
        should_use_llm = use_llm if use_llm is not None else self.use_llm_scoring
        
        # 🆕 优先尝试LLM语义评分
        llm_parse_failed = False
        if should_use_llm and self.llm_scorer:
            # 获取上下文
            architecture_context = self.architecture_content[:2000] if self.architecture_content else None # 截取前2000字概览
            blueprint_context = self._get_chapter_blueprint(chapter_num) if chapter_num else None

            llm_scores = self.llm_scorer.score_content(content, architecture_context, blueprint_context)
            if llm_scores:
                # LLM评分成功，添加字数和综合评分（使用加权计算）
                scores: Dict[str, Any] = llm_scores.copy()
                scores["字数"] = len(content)
                scores["综合评分"] = calculate_weighted_score(scores)
                scores["评分模式"] = "LLM语义评分（加权）"
                scores["_llm_parse_failed"] = False
                logging.info(f"使用LLM语义评分，综合分: {scores['综合评分']}")
                return scores
            else:
                logging.warning("LLM评分失败，回退到关键词评分")
                llm_parse_failed = True
                last_failure = getattr(self.llm_scorer, "last_parse_failure", None)
                if isinstance(last_failure, dict):
                    logging.warning(
                        "LLM评分解析失败详情: reason=%s, model=%s, raw=%s",
                        last_failure.get("reason", ""),
                        last_failure.get("model_name", ""),
                        str(last_failure.get("raw_response_preview", ""))[:180],
                    )

        # 关键词评分（作为默认）+ 启发式修正（LLM失败回退）
        scores: Dict[str, Any] = {
            "剧情连贯性": self.analyze_plot_coherence(content),
            "角色一致性": self.analyze_character_consistency(content),
            "写作质量": self.analyze_writing_quality(content),
            "架构遵循度": self.analyze_architecture_adherence(content),
            "设定遵循度": self.analyze_setting_adherence(content),
            "字数达标率": self.analyze_word_count_achievement(content, target_word_count),
            "情感张力": self.analyze_emotional_tension(content),
            "系统机制": self.analyze_system_mechanism(content)
        }

        # 添加字数统计
        scores["字数"] = len(content)

        # 启发式回退修正：纳入结尾钩子/重复惩罚，降低关键词堆砌欺骗性
        self._apply_heuristic_adjustments(scores, content)

        # 使用加权计算综合评分（情感张力权重最高）
        scores["综合评分"] = calculate_weighted_score(scores)
        scores["评分模式"] = "混合启发式评分（LLM回退）" if should_use_llm else "关键词评分（加权）"
        scores["_llm_parse_failed"] = bool(llm_parse_failed)
        
        # 🆕 题材维度扩展评分
        if self.genre_extender:
            genre_scores = self.genre_extender.get_genre_scores(content)
            if genre_scores:
                scores["题材维度"] = genre_scores
                scores["题材综合分"] = self.genre_extender.calculate_genre_weighted_score(genre_scores)
                scores["检测题材"] = self.genre
                
                # 获取改进建议
                improvement_hints = self.genre_extender.get_improvement_hints(genre_scores)
                if improvement_hints:
                    scores["题材改进建议"] = improvement_hints

        return scores

    def _apply_heuristic_adjustments(self, scores: Dict[str, Any], content: str) -> None:
        """在LLM不可用时增加轻量启发式修正，提升评分稳定性。"""
        if not content:
            return

        tail = content[-800:]
        hook_keywords = ["悬念", "危机", "未完", "然而", "却在", "下一刻", "忽然", "骤然", "？", "……"]
        hook_hits = sum(1 for k in hook_keywords if k in tail)
        if hook_hits == 0:
            scores["情感张力"] = max(1.0, float(scores.get("情感张力", 7.0)) - 1.0)
        elif hook_hits >= 3:
            scores["情感张力"] = min(10.0, float(scores.get("情感张力", 7.0)) + 0.5)

        paragraphs = [p.strip() for p in re.split(r"\n{2,}", content) if p.strip()]
        if paragraphs:
            seen = set()
            dup = 0
            for p in paragraphs:
                key = p[:80]
                if key in seen:
                    dup += 1
                else:
                    seen.add(key)
            dup_ratio = dup / max(1, len(paragraphs))
            if dup_ratio > 0.12:
                scores["写作质量"] = max(1.0, float(scores.get("写作质量", 7.0)) - 1.0)
                scores["剧情连贯性"] = max(1.0, float(scores.get("剧情连贯性", 7.0)) - 0.5)

    def analyze_chapter(self, chapter_num: int, target_word_count: int = 3000) -> Dict[str, float]:
        """分析单个章节"""
        chapter_file = self.chapters_path / f"chapter_{chapter_num}.txt"

        try:
            with open(chapter_file, 'r', encoding='utf-8') as f:
                content = f.read().strip()
        except Exception as e:
            print(f"读取章节 {chapter_num} 失败: {e}")
            # 返回最低分
            return {dimension: 1.0 for dimension in self.get_dimension_names()}

        return self.analyze_content(content, target_word_count=target_word_count, chapter_num=chapter_num)

    def _get_chapter_blueprint(self, chapter_num: int) -> str:
        """从目录文件中提取特定章节的大纲"""
        if not self.directory_content:
            return ""
        
        try:
            # 简单正则匹配：查找 "第X章" 到下一章或文件结束之间的内容
            # 模式支持：第1章、第 1 章、Chapter 1
            pattern = re.compile(rf"(第\s*{chapter_num}\s*章|Chapter\s*{chapter_num})[:\s](.+?)(?=(第\s*\d+\s*章|Chapter\s*\d+|$))", re.DOTALL | re.IGNORECASE)
            match = pattern.search(self.directory_content)
            if match:
                return match.group(0).strip()
        except Exception as e:
            logging.warning(f"提取章节 {chapter_num} 大纲失败: {e}")
        
        return ""

    def get_dimension_names(self) -> List[str]:
        """获取评分维度名称"""
        return [
            "剧情连贯性", "角色一致性", "写作质量", "架构遵循度",
            "设定遵循度", "字数达标率", "情感张力", "系统机制"
        ]

    def analyze_all_chapters(self, max_chapters: int = 400) -> Dict[int, Dict[str, float]]:
        """批量分析所有章节"""
        print(f"开始分析 {max_chapters} 章...")

        all_scores = {}

        for i in range(1, max_chapters + 1):
            if i % 50 == 0:
                print(f"进度: {i}/{max_chapters}")

            scores = self.analyze_chapter(i)
            all_scores[i] = scores

            # 保存中间结果
            if i % 100 == 0:
                self.save_intermediate_results(all_scores, f"temp_results_chapter_{i}.json")

        print("分析完成!")
        self.scores = all_scores
        return all_scores

    def save_intermediate_results(self, scores: Dict[Any, Any], filename: str) -> None:
        """保存中间结果"""
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(scores, f, ensure_ascii=False, indent=2)
            print(f"中间结果已保存: {filename}")
        except Exception as e:
            print(f"保存中间结果失败: {e}")

    def generate_markdown_report(self, scores: Dict[int, Dict[str, float]]) -> str:
        """生成Markdown报告"""
        dimensions = self.get_dimension_names()

        # 计算统计数据
        dimension_stats = {}
        for dimension in dimensions:
            values = [scores[chap][dimension] for chap in scores.keys()]
            dimension_stats[dimension] = {
                "平均": round(statistics.mean(values), 2),
                "最高": round(max(values), 2),
                "最低": round(min(values), 2),
                "中位数": round(statistics.median(values), 2)
            }

        # 综合评分统计
        overall_scores = [scores[chap]["综合评分"] for chap in scores.keys()]
        overall_stats = {
            "平均": round(statistics.mean(overall_scores), 2),
            "最高": round(max(overall_scores), 2),
            "最低": round(min(overall_scores), 2),
            "中位数": round(statistics.median(overall_scores), 2)
        }

        # 找出最高分和最低分章节
        highest_chapter = max(scores.keys(), key=lambda x: scores[x]["综合评分"])
        lowest_chapter = min(scores.keys(), key=lambda x: scores[x]["综合评分"])

        # 生成报告
        report = f"""# 小说质量分析报告

**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
**分析章节**: {len(scores)} 章
**评分维度**: {len(dimensions)} 个维度

## 总体质量概览

| 指标 | 分数 | 章节 |
|------|------|------|
| 平均分 | {overall_stats['平均']}/10 | - |
| 最高分 | {overall_stats['最高']}/10 | 第{highest_chapter}章 |
| 最低分 | {overall_stats['最低']}/10 | 第{lowest_chapter}章 |
| 中位数 | {overall_stats['中位数']}/10 | - |

## 8维度评分统计

| 维度 | 平均分 | 最高分 | 最低分 | 中位数 |
|------|--------|--------|--------|--------|"""

        for dimension in dimensions:
            stats = dimension_stats[dimension]
            report += f"\n| {dimension} | {stats['平均']}/10 | {stats['最高']}/10 | {stats['最低']}/10 | {stats['中位数']}/10 |"

        report += f"""

## 质量分布分析

### 优秀章节 (8.5分以上)
"""

        excellent_chapters = [chap for chap in scores.keys() if scores[chap]["综合评分"] >= 8.5]
        if excellent_chapters:
            report += f"共 {len(excellent_chapters)} 章: {', '.join(map(str, excellent_chapters[:10]))}"
            if len(excellent_chapters) > 10:
                report += f" 等{len(excellent_chapters)}章"
        else:
            report += "无"

        report += f"""

### 良好章节 (7.0-8.4分)
"""

        good_chapters = [chap for chap in scores.keys() if 7.0 <= scores[chap]["综合评分"] < 8.5]
        report += f"共 {len(good_chapters)} 章: {len(good_chapters)/len(scores)*100:.1f}%"

        report += f"""

### 需改进章节 (6.0分以下)
"""

        poor_chapters = [chap for chap in scores.keys() if scores[chap]["综合评分"] < 6.0]
        if poor_chapters:
            report += f"共 {len(poor_chapters)} 章: {', '.join(map(str, poor_chapters[:10]))}"
            if len(poor_chapters) > 10:
                report += f" 等{len(poor_chapters)}章"
        else:
            report += "无"

        report += f"""

## 详细章节评分表

| 章节 | 剧情连贯性 | 角色一致性 | 写作质量 | 架构遵循度 | 设定遵循度 | 字数达标率 | 情感张力 | 系统机制 | 综合评分 |
|------|-----------|-----------|---------|-----------|-----------|-----------|---------|---------|---------|"""

        # 按章节号排序
        sorted_chapters = sorted(scores.keys())
        for chapter in sorted_chapters:
            chap_scores = scores[chapter]
            report += f"\n| {chapter} | "
            report += " | ".join([f"{chap_scores[dim]:.1f}" for dim in dimensions])
            report += f" | {chap_scores['综合评分']:.1f} |"

        report += f"""

## 分析结论

1. **整体质量**: {overall_stats['平均']}/10分，{'表现优秀' if overall_stats['平均'] >= 8 else '表现良好' if overall_stats['平均'] >= 7 else '需要改进'}
2. **最强维度**: {max(dimension_stats.keys(), key=lambda x: dimension_stats[x]['平均'])} (平均{max(dimension_stats.values(), key=lambda x: x['平均'])['平均']}分)
3. **最弱维度**: {min(dimension_stats.keys(), key=lambda x: dimension_stats[x]['平均'])} (平均{min(dimension_stats.values(), key=lambda x: x['平均'])['平均']}分)
4. **优秀章节比例**: {len(excellent_chapters)/len(scores)*100:.1f}%
5. **需改进章节比例**: {len(poor_chapters)/len(scores)*100:.1f}%

## 改进建议

### 针对{min(dimension_stats.keys(), key=lambda x: dimension_stats[x]['平均'])}维度的建议:
- 加强该维度的相关内容设计
- 提高该要素在章节中的比重和表现力
- 参考高分章节的优秀做法

### 针对低分章节的建议:
- 重点分析第{', '.join(map(str, poor_chapters[:5]))}章等问题章节
- 补充缺失的核心要素
- 加强剧情连贯性和角色刻画

---
*报告生成完成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*
"""

        return report

def main():
    """主函数"""
    import sys
    
    if len(sys.argv) > 1:
        novel_path = sys.argv[1]
    else:
        print("Usage: python chapter_quality_analyzer.py <novel_folder_path>")
        print("Example: python chapter_quality_analyzer.py wxhyj")
        sys.exit(1)

    print(f"🚀 启动小说质量分析: {novel_path}")

    # 创建分析器
    analyzer = ChapterQualityAnalyzer(novel_path)

    # 分析所有章节
    scores = analyzer.analyze_all_chapters(400)

    # 保存详细结果
    result_file = f"{novel_path}/chapter_analysis_results.json"
    analyzer.save_intermediate_results(scores, result_file)

    # 生成报告
    report = analyzer.generate_markdown_report(scores)

    # 保存报告
    report_file = f"{novel_path}/chapter_quality_report.md"
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write(report)

    print(f"✅ 分析完成！报告已保存至: {report_file}")
    print(f"📊 详细数据已保存至: {result_file}")

if __name__ == "__main__":
    main()
