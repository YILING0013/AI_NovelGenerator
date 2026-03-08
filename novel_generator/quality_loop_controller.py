#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
单章闭环迭代控制器 (QualityLoopController)
实现 生成 -> 校验 -> 评分 -> 优化 的螺旋上升闭环
"""

import logging
import time
import os
import datetime
import random
import json
import re
from dataclasses import dataclass
from typing import Dict, Any, Optional, List, Set, Tuple

from chapter_quality_analyzer import ChapterQualityAnalyzer
from llm_adapters import BaseLLMAdapter, create_llm_adapter
from utils import save_string_to_txt, resolve_architecture_file
from novel_generator.common import clean_llm_output, set_llm_log_context, extract_revised_text_payload
from novel_generator.wordcount_utils import count_chapter_words
from novel_generator.architecture_runtime_slice import (
    build_runtime_architecture_context,
)

# 导入学习机制
try:
    from novel_generator.problem_learner import get_problem_learner
    PROBLEM_LEARNER_AVAILABLE = True
except ImportError:
    PROBLEM_LEARNER_AVAILABLE = False

# 🆕 导入毒舌读者 Agent
try:
    from novel_generator.critique_agent import PoisonousReaderAgent
    CRITIC_AGENT_AVAILABLE = True
except ImportError:
    CRITIC_AGENT_AVAILABLE = False

# 导入根目录的 Prompt 定义 (用于获取 S 级文笔范例)
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    from prompt_definitions import LITERARY_STYLE_GUIDE, SUBTEXT_GUIDE, TWO_TRACK_NARRATIVE_RULE, CULTURAL_DEPTH_GUIDE
except ImportError:
    logging.warning("Failed to import prompt_definitions. Using default style guides.")
    LITERARY_STYLE_GUIDE = ""
    SUBTEXT_GUIDE = ""

# 导入一致性检查器
try:
    from novel_generator.consistency_checker import get_consistency_checker
    CONSISTENCY_CHECKER_AVAILABLE = True
except ImportError:
    CONSISTENCY_CHECKER_AVAILABLE = False

try:
    from novel_generator.consistency_review import (
        check_consistency as llm_check_consistency,
        has_obvious_conflict,
        extract_conflict_items,
    )
    LLM_CONSISTENCY_REVIEW_AVAILABLE = True
except ImportError:
    LLM_CONSISTENCY_REVIEW_AVAILABLE = False

try:
    from novel_generator.timeline_manager import TimelineManager
    TIMELINE_MANAGER_AVAILABLE = True
except ImportError:
    TIMELINE_MANAGER_AVAILABLE = False

# 🆕 导入节奏指令验证
try:
    from novel_generator.pacing_agent import PacingAgent
    PACING_AGENT_AVAILABLE = True
except ImportError:
    PACING_AGENT_AVAILABLE = False

# 🆕 导入角色声音追踪器
try:
    from novel_generator.character_voice_tracker import CharacterVoiceTracker
    VOICE_TRACKER_AVAILABLE = True
except ImportError:
    VOICE_TRACKER_AVAILABLE = False

# 🆕 导入悬念追踪器
try:
    from novel_generator.hook_tracker import HookTracker
    HOOK_TRACKER_AVAILABLE = True
except ImportError:
    HOOK_TRACKER_AVAILABLE = False

# 🆕 导入信息密度检测器
try:
    from novel_generator.density_checker import DensityChecker
    DENSITY_CHECKER_AVAILABLE = True
except ImportError:
    DENSITY_CHECKER_AVAILABLE = False

# 🆕 导入敏感内容过滤器
try:
    from novel_generator.content_safety import ContentSafetyFilter
    SAFETY_FILTER_AVAILABLE = True
except ImportError:
    SAFETY_FILTER_AVAILABLE = False

# 🆕 导入叙事模式检测器
try:
    from novel_generator.pattern_detector import NarrativePatternDetector
    PATTERN_DETECTOR_AVAILABLE = True
except ImportError:
    PATTERN_DETECTOR_AVAILABLE = False

# 🆕 导入叙事线程追踪器
try:
    from novel_generator.narrative_threads import NarrativeThreadTracker
    THREAD_TRACKER_AVAILABLE = True
except ImportError:
    THREAD_TRACKER_AVAILABLE = False

# 🆕 导入生成统计监控器
try:
    from novel_generator.generation_stats import GenerationStatsMonitor
    STATS_MONITOR_AVAILABLE = True
except ImportError:
    STATS_MONITOR_AVAILABLE = False

# 默认质量阈值 (可配置)
DEFAULT_QUALITY_THRESHOLD = 9
MAX_ITERATIONS = 10

# Auto-compression config
MAX_WORD_COUNT_BEFORE_COMPRESS = 6000
TARGET_WORD_COUNT_AFTER_COMPRESS = 4000

# Auto-expansion config
MIN_WORD_COUNT_BEFORE_EXPAND = 3500  
TARGET_WORD_COUNT_AFTER_EXPAND = 4000  

LLM_LOG_PROMPT_CHAR_LIMIT = 20000
LLM_LOG_RESPONSE_CHAR_LIMIT = 5000

# Tolerance
WORD_COUNT_ADJUST_SCORE_TOLERANCE = 0.5

# Grading thresholds
SEVERE_THRESHOLD_OFFSET = 2.0

# Post-finalize tolerance
POST_FINALIZE_TOLERANCE = 0.5

# Stagnation detection（放宽限制，多尝试几次）
STAGNATION_THRESHOLD = 0.05  # 从0.1降到0.05，更敏感
STAGNATION_COUNT_LIMIT = 5   # 从3增加到5，多尝试
PARSE_FAILURE_STREAK_LIMIT = 3

# Quality Dimensions
QUALITY_DIMENSIONS = {
    "plot_tension": {"weight": 0.25, "threshold": 7.5},
    "character_depth": {"weight": 0.20, "threshold": 7.5},
    "writing_style": {"weight": 0.20, "threshold": 7.5},
    "originality": {"weight": 0.20, "threshold": 7.0},
    "consistency": {"weight": 0.15, "threshold": 8.0}
}


@dataclass
class QualityLoopPolicy:
    """质量闭环策略配置（支持由 llm_config['quality_policy'] 覆盖默认值）。"""
    default_quality_threshold: float = DEFAULT_QUALITY_THRESHOLD
    max_iterations: int = MAX_ITERATIONS
    min_word_count_before_expand: int = MIN_WORD_COUNT_BEFORE_EXPAND
    target_word_count_after_expand: int = TARGET_WORD_COUNT_AFTER_EXPAND
    word_count_adjust_score_tolerance: float = WORD_COUNT_ADJUST_SCORE_TOLERANCE
    severe_threshold_offset: float = SEVERE_THRESHOLD_OFFSET
    stagnation_threshold: float = STAGNATION_THRESHOLD
    stagnation_count_limit: int = STAGNATION_COUNT_LIMIT
    enable_llm_consistency_check: bool = True
    consistency_hard_gate: bool = True
    enable_timeline_check: bool = True
    timeline_hard_gate: bool = True
    enable_compression: bool = False
    force_critic_logging_each_iteration: bool = False
    parse_failure_streak_limit: int = PARSE_FAILURE_STREAK_LIMIT


def _safe_cast(raw: Any, caster, default):
    try:
        return caster(raw)
    except (TypeError, ValueError):
        return default


def _safe_bool(raw: Any, default: bool = False) -> bool:
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, (int, float)):
        return raw != 0
    if isinstance(raw, str):
        normalized = raw.strip().lower()
        if normalized in {"1", "true", "yes", "y", "on", "enabled", "t"}:
            return True
        if normalized in {"0", "false", "no", "n", "off", "disabled", "f", ""}:
            return False
    return default


def _normalize_quality_loop_inputs(
    threshold: Any,
    min_word_count: Any,
    target_word_count: Any,
    policy: QualityLoopPolicy,
) -> tuple[float, int, int]:
    normalized_threshold = _safe_cast(threshold, float, policy.default_quality_threshold)
    if normalized_threshold <= 0:
        normalized_threshold = policy.default_quality_threshold
    if normalized_threshold > 10.0:
        normalized_threshold = 10.0

    normalized_min = _safe_cast(min_word_count, int, policy.min_word_count_before_expand)
    if normalized_min <= 0:
        normalized_min = policy.min_word_count_before_expand

    normalized_target = _safe_cast(target_word_count, int, policy.target_word_count_after_expand)
    if normalized_target <= 0:
        normalized_target = policy.target_word_count_after_expand
    if normalized_target < normalized_min:
        normalized_target = normalized_min

    return normalized_threshold, normalized_min, normalized_target


def _normalize_initial_content(initial_content: Any) -> str:
    return str(initial_content or "").strip()


_PRIMARY_SCORE_DIMENSIONS = (
    "剧情连贯性",
    "角色一致性",
    "写作质量",
    "架构遵循度",
    "设定遵循度",
    "情感张力",
    "系统机制",
)


def _resolve_overall_score(scores: Dict[str, Any]) -> float:
    """优先读取综合评分；若缺失/异常则退化为维度均值，确保闭环评分可用。"""
    score = _safe_cast(scores.get("综合评分"), float, float("nan"))
    if isinstance(score, float) and score == score:
        return max(0.0, min(10.0, score))

    dimension_values: List[float] = []
    for dim in _PRIMARY_SCORE_DIMENSIONS:
        dim_score = _safe_cast(scores.get(dim), float, float("nan"))
        if isinstance(dim_score, float) and dim_score == dim_score:
            dimension_values.append(max(0.0, min(10.0, dim_score)))
    if dimension_values:
        avg_score = round(sum(dimension_values) / len(dimension_values), 2)
        return max(0.0, min(10.0, avg_score))
    return 0.0

# 🆕 扣分规则文本（与评分器同步，让优化器知道评分器在检查什么）
# 🆕 正面质量标准（Elevation Standards - 取代扣分规则，告诉 LLM 什么是"好"）
POSITIVE_QUALITY_STANDARDS = """
【S级网文质量标准 - 请以此为目标进行升维】

1. ⚡ **极致张力 (Tension)**：
   - **两难困境**：主角必须面临"不做会死，做了会痛"的选择，拒绝轻松破局。
   - **信息差**：利用"读者知道但角色不知道"（或反之）制造期待感或焦虑感。
   - **节奏控制**：高潮段落使用短句（5-10字）加速，情感段落使用长句铺陈。

2. 🎨 **沉浸画面 (Immersion)**：
   - **通感描写**：不要只写看到的，要写听到的（耳膜震动）、闻到的（铁锈味）、触到的（静电刺痛）。
   - **动态运镜**：拒绝静态说明，使用"特写->全景->特写"的镜头切换语言。
   - **环境叙事**：环境必须映射角色的心境（如：心烦时听到的是噪音，恐惧时看到的是阴影）。

3. 🎭 **立体演绎 (Character)**：
   - **潜台词**：对话必须包含弦外之音。强者不说狠话但有压迫感，弱者不说废话但有求生欲。
   - **微表情**：在高冲突对话间隙，插入角色的无意识动作（手指痉挛、瞳孔收缩）。
   - **智商在线**：反派必须有逻辑闭环，主角必须靠洞察力而非蛮力破局。

4. 🕸️ **逻辑闭环 (Logic)**：
   - **草蛇灰线**：伏笔埋设要自然，回收要震撼。
   - **世界观咬合**：所用招式、物品必须符合该世界的底层规则（如五行、数据流）。
5. ☯️ **双轨叙事 (Dual-Track)**：
   - **严格分层**：主角内心可做理性分析，但**对外交流**及**旁白描写**必须使用本书术语（如三轨九术、天书残页、灵机/炁），禁用“系统/精神力/灵气”等通用词，严禁“出戏”。

"""

class QualityLoopController:
    def __init__(self, novel_path: str, llm_config: Dict[str, Any], critic_llm_config: Optional[Dict[str, Any]] = None):
        self.novel_path = novel_path
        # 传入LLM配置以启用语义评分
        self.analyzer = ChapterQualityAnalyzer(novel_path, llm_config=llm_config)
        self.llm_config = llm_config
        self.llm_adapter = self._create_llm_adapter(llm_config)
        self.policy = self._load_policy(llm_config)
        self.architecture_context_max_chars = min(
            120000,
            max(
                4000,
                _safe_cast(llm_config.get("architecture_context_max_chars"), int, 16000),
            ),
        )
        self.architecture_context_ignore_budget = _safe_bool(
            llm_config.get("architecture_context_ignore_budget"),
            default=True,
        )
        
        # 初始化学习机制
        self.problem_learner = None
        if PROBLEM_LEARNER_AVAILABLE:
            try:
                self.problem_learner = get_problem_learner(novel_path)
            except (RuntimeError, ValueError, TypeError, OSError) as e:
                logging.warning(f"学习机制初始化失败: {e}")
        
        # 初始化一致性检查器
        self.consistency_checker = None
        if CONSISTENCY_CHECKER_AVAILABLE:
            try:
                self.consistency_checker = get_consistency_checker(novel_path)
            except (RuntimeError, ValueError, TypeError, OSError) as e:
                logging.warning(f"一致性检查器初始化失败: {e}")

        self.enable_llm_consistency_check = bool(self.policy.enable_llm_consistency_check)
        self.consistency_hard_gate = bool(self.policy.consistency_hard_gate)
        self.enable_timeline_check = bool(self.policy.enable_timeline_check)
        self.timeline_hard_gate = bool(self.policy.timeline_hard_gate)
        raw_review_config = llm_config.get("consistency_review_config", {})
        if not isinstance(raw_review_config, dict):
            raw_review_config = {}
        self.consistency_review_config = {
            "api_key": raw_review_config.get("api_key", llm_config.get("api_key", "")),
            "base_url": raw_review_config.get("base_url", llm_config.get("base_url", "")),
            "model_name": raw_review_config.get("model_name", llm_config.get("model_name", "")),
            "interface_format": raw_review_config.get("interface_format", llm_config.get("interface_format", "openai")),
            "temperature": raw_review_config.get("temperature", 0.2),
            "max_tokens": raw_review_config.get("max_tokens", llm_config.get("max_tokens", 4096)),
            "timeout": raw_review_config.get("timeout", llm_config.get("timeout", 600)),
        }

        self.timeline_manager = None
        if TIMELINE_MANAGER_AVAILABLE:
            try:
                self.timeline_manager = TimelineManager(novel_path)
            except (RuntimeError, ValueError, TypeError, OSError) as e:
                logging.warning(f"时间线管理器初始化失败: {e}")
        
        # 记录迭代日志
        self.iteration_logs = []
        
        # 🆕 LLM对话记录文件夹
        self.llm_log_dir = os.path.join(novel_path, "llm_logs")
        os.makedirs(self.llm_log_dir, exist_ok=True)
        self._canonical_system_term = self._load_canonical_system_term()

        # 🆕 初始化毒舌读者 Agent
        self.critic_agent = None
        if CRITIC_AGENT_AVAILABLE:
            try:
                # 优先使用独立的毒舌LLM配置，如果没有则使用主配置
                agent_config = critic_llm_config if critic_llm_config else llm_config
                self.critic_agent = PoisonousReaderAgent(agent_config)
                logging.info(f"Critic Agent initialized with config: {agent_config.get('model_name', 'Unknown')}")
            except (RuntimeError, ValueError, TypeError, OSError) as e:
                logging.warning(f"毒舌读者初始化失败: {e}")
        
        # 🆕 Fix 1.4: 已尝试优化的维度列表（回退后差异化策略）
        self._tried_dimensions: List[str] = []
        self._retry_temperature_boost = 0.0
        
        # 🆕 初始化角色声音追踪器
        self.voice_tracker = None
        if VOICE_TRACKER_AVAILABLE:
            try:
                self.voice_tracker = CharacterVoiceTracker(novel_path)
                logging.info("🎙️ 角色声音追踪器已就位")
            except Exception as e:
                logging.warning(f"角色声音追踪器初始化失败: {e}")
        
        # 🆕 初始化悬念追踪器
        self.hook_tracker = None
        if HOOK_TRACKER_AVAILABLE:
            try:
                self.hook_tracker = HookTracker(novel_path)
                logging.info("🎣 悬念追踪器已就位")
            except Exception as e:
                logging.warning(f"悬念追踪器初始化失败: {e}")
        
        # 🆕 初始化信息密度检测器
        self.density_checker = None
        if DENSITY_CHECKER_AVAILABLE:
            try:
                self.density_checker = DensityChecker()
                logging.info("📊 信息密度检测器已就位")
            except Exception as e:
                logging.warning(f"信息密度检测器初始化失败: {e}")
        
        # 🆕 初始化敏感内容过滤器
        self.safety_filter = None
        if SAFETY_FILTER_AVAILABLE:
            try:
                self.safety_filter = ContentSafetyFilter()
                logging.info("🛡️ 敏感内容过滤器已就位")
            except Exception as e:
                logging.warning(f"敏感内容过滤器初始化失败: {e}")
        
        # 🆕 初始化叙事模式检测器
        self.pattern_detector = None
        if PATTERN_DETECTOR_AVAILABLE:
            try:
                self.pattern_detector = NarrativePatternDetector(novel_path)
                logging.info("🔄 叙事模式检测器已就位")
            except Exception as e:
                logging.warning(f"叙事模式检测器初始化失败: {e}")
        
        # 🆕 初始化叙事线程追踪器
        self.thread_tracker = None
        if THREAD_TRACKER_AVAILABLE:
            try:
                self.thread_tracker = NarrativeThreadTracker(novel_path)
                logging.info("🧵 叙事线程追踪器已就位")
            except Exception as e:
                logging.warning(f"叙事线程追踪器初始化失败: {e}")
        
        # 🆕 初始化生成统计监控器
        self.stats_monitor = None
        if STATS_MONITOR_AVAILABLE:
            try:
                self.stats_monitor = GenerationStatsMonitor(novel_path)
                logging.info("📈 生成统计监控器已就位")
            except Exception as e:
                logging.warning(f"生成统计监控器初始化失败: {e}")
    
    def _log_llm_conversation(self, chapter_num: int, iteration: int, stage: str, prompt: str, response: str):
        """记录LLM对话到文件"""
        try:
            chapter_log_dir = os.path.join(self.llm_log_dir, f"chapter_{chapter_num}")
            os.makedirs(chapter_log_dir, exist_ok=True)
            
            timestamp = datetime.datetime.now().strftime("%H%M%S")
            log_file = os.path.join(chapter_log_dir, f"iter{iteration}_{stage}_{timestamp}.md")
            
            with open(log_file, 'w', encoding='utf-8') as f:
                f.write(f"# Chapter {chapter_num} - Iteration {iteration} - {stage}\n\n")
                f.write(f"**Time**: {datetime.datetime.now().isoformat()}\n\n")
                f.write("## Prompt\n\n```\n")
                f.write(
                    prompt[:LLM_LOG_PROMPT_CHAR_LIMIT]
                    + ("..." if len(prompt) > LLM_LOG_PROMPT_CHAR_LIMIT else "")
                )
                f.write("\n```\n\n")
                f.write("## Response\n\n```\n")
                f.write(
                    response[:LLM_LOG_RESPONSE_CHAR_LIMIT]
                    + ("..." if len(response) > LLM_LOG_RESPONSE_CHAR_LIMIT else "")
                )
                f.write("\n```\n")
        except Exception as e:
            logging.warning(f"记录LLM对话失败: {e}")

    def _create_llm_adapter(self, config: Dict) -> BaseLLMAdapter:
        """创建LLM适配器"""
        return create_llm_adapter(
            interface_format=config.get('interface_format', 'openai'),
            api_key=config.get('api_key', ''),
            base_url=config.get('base_url', ''),
            model_name=config.get('model_name', ''),
            temperature=config.get('temperature', 0.7),
            max_tokens=config.get('max_tokens', 4000),
            timeout=config.get('timeout', 60)
        )
    
    def _emit_progress(self, progress_callback, step_name: str, progress: float, payload: Optional[Dict[str, Any]] = None):
        """兼容旧回调签名 callback(step, progress) 与新签名 callback(step, progress, payload)。"""
        if not progress_callback:
            return
        try:
            progress_callback(step_name, progress, payload)
        except TypeError:
            progress_callback(step_name, progress)

    def _read_project_text(self, file_name: str) -> str:
        if file_name == "Novel_architecture.txt":
            file_path = resolve_architecture_file(self.novel_path)
        else:
            file_path = os.path.join(self.novel_path, file_name)
        if not os.path.exists(file_path):
            return ""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                text = f.read()
            if file_name == "Novel_architecture.txt":
                sliced = build_runtime_architecture_context(
                    text,
                    max_chars=self.architecture_context_max_chars,
                    section_numbers_hint=(0, 88, 136),
                    ignore_budget=self.architecture_context_ignore_budget,
                )
                return sliced or text
            return text
        except (OSError, UnicodeError):
            return ""

    def _run_llm_consistency_review(self, content: str) -> str:
        if not self.enable_llm_consistency_check or not LLM_CONSISTENCY_REVIEW_AVAILABLE:
            return ""
        try:
            review = llm_check_consistency(
                novel_setting=self._read_project_text("Novel_architecture.txt"),
                character_state=self._read_project_text("character_state.txt"),
                global_summary=self._read_project_text("global_summary.txt"),
                chapter_text=content,
                api_key=self.consistency_review_config.get("api_key", ""),
                base_url=self.consistency_review_config.get("base_url", ""),
                model_name=self.consistency_review_config.get("model_name", ""),
                temperature=float(self.consistency_review_config.get("temperature", 0.2)),
                interface_format=self.consistency_review_config.get("interface_format", "openai"),
                max_tokens=int(self.consistency_review_config.get("max_tokens", 4096)),
                timeout=int(self.consistency_review_config.get("timeout", 600)),
            )
            return (review or "").strip()
        except (RuntimeError, ValueError, TypeError, OSError) as e:
            logging.warning(f"LLM一致性检查异常: {e}")
            return ""

    def _detect_external_track_tech_terms(self, content: str) -> List[str]:
        """
        检测外轨中高风险科技词。为避免误杀，尽量排除常见“系统面板”行。
        返回命中的违规词列表（去重）。
        """
        banned_terms = [
            "CPU", "GPU", "Bug", "DEBUG", "SQL", "API", "SDK",
            "服务器", "客户端", "下载", "上传", "数据包", "脚本", "编译",
            "加载中", "进度%", "检测到", "正在扫描", "初始化模块",
        ]
        violations: List[str] = []
        lines = (content or "").splitlines()
        panel_prefixes = ("【系统", "[系统", "系统提示", "叮", "提示：")

        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            # 系统面板行放宽；其余视作外轨文本严格检测。
            if stripped.startswith(panel_prefixes):
                continue
            for term in banned_terms:
                if term in stripped and term not in violations:
                    violations.append(term)

        return violations
    
    def _load_policy(self, llm_config: Dict[str, Any]) -> QualityLoopPolicy:
        """从 llm_config 中加载质量策略配置。"""
        raw = llm_config.get("quality_policy", {}) if isinstance(llm_config, dict) else {}
        if not isinstance(raw, dict):
            raw = {}

        policy = QualityLoopPolicy(
            default_quality_threshold=_safe_cast(
                raw.get("default_quality_threshold", llm_config.get("quality_threshold", DEFAULT_QUALITY_THRESHOLD)),
                float,
                DEFAULT_QUALITY_THRESHOLD,
            ),
            max_iterations=max(1, min(50, _safe_cast(raw.get("max_iterations", MAX_ITERATIONS), int, MAX_ITERATIONS))),
            min_word_count_before_expand=max(
                100,
                _safe_cast(raw.get("min_word_count_before_expand", MIN_WORD_COUNT_BEFORE_EXPAND), int, MIN_WORD_COUNT_BEFORE_EXPAND),
            ),
            target_word_count_after_expand=max(
                100,
                _safe_cast(raw.get("target_word_count_after_expand", TARGET_WORD_COUNT_AFTER_EXPAND), int, TARGET_WORD_COUNT_AFTER_EXPAND),
            ),
            word_count_adjust_score_tolerance=max(
                0.0,
                _safe_cast(raw.get("word_count_adjust_score_tolerance", WORD_COUNT_ADJUST_SCORE_TOLERANCE), float, WORD_COUNT_ADJUST_SCORE_TOLERANCE),
            ),
            severe_threshold_offset=max(
                0.0,
                _safe_cast(raw.get("severe_threshold_offset", SEVERE_THRESHOLD_OFFSET), float, SEVERE_THRESHOLD_OFFSET),
            ),
            stagnation_threshold=max(
                0.0,
                _safe_cast(raw.get("stagnation_threshold", STAGNATION_THRESHOLD), float, STAGNATION_THRESHOLD),
            ),
            stagnation_count_limit=max(
                1,
                _safe_cast(raw.get("stagnation_count_limit", STAGNATION_COUNT_LIMIT), int, STAGNATION_COUNT_LIMIT),
            ),
            enable_llm_consistency_check=_safe_bool(
                raw.get("enable_llm_consistency_check"),
                default=_safe_bool(llm_config.get("enable_llm_consistency_check"), default=True),
            ),
            consistency_hard_gate=_safe_bool(
                raw.get("consistency_hard_gate"),
                default=_safe_bool(llm_config.get("consistency_hard_gate"), default=True),
            ),
            enable_timeline_check=_safe_bool(
                raw.get("enable_timeline_check"),
                default=_safe_bool(llm_config.get("enable_timeline_check"), default=True),
            ),
            timeline_hard_gate=_safe_bool(
                raw.get("timeline_hard_gate"),
                default=_safe_bool(llm_config.get("timeline_hard_gate"), default=True),
            ),
            enable_compression=_safe_bool(
                raw.get("enable_compression"),
                default=_safe_bool(llm_config.get("enable_compression"), default=False),
            ),
            force_critic_logging_each_iteration=_safe_bool(
                raw.get("force_critic_logging_each_iteration"),
                default=_safe_bool(llm_config.get("force_critic_logging_each_iteration"), default=False),
            ),
            parse_failure_streak_limit=max(
                1,
                _safe_cast(
                    raw.get("parse_failure_streak_limit", PARSE_FAILURE_STREAK_LIMIT),
                    int,
                    PARSE_FAILURE_STREAK_LIMIT,
                ),
            ),
        )
        if policy.target_word_count_after_expand < policy.min_word_count_before_expand:
            policy.target_word_count_after_expand = policy.min_word_count_before_expand
        return policy

    def _should_invoke_critic(self, overall_score: float, threshold: float) -> bool:
        """是否调用毒舌评审（支持阈值外的强制日志模式）。"""
        if not self.critic_agent:
            return False
        if overall_score >= threshold:
            return True
        return bool(self.policy.force_critic_logging_each_iteration)

    def execute_quality_loop(self, 
                           initial_content: str, 
                           chapter_num: int,
                           threshold: float = DEFAULT_QUALITY_THRESHOLD,
                           progress_callback = None,
                           skip_expand: bool = False,
                           min_word_count: int = MIN_WORD_COUNT_BEFORE_EXPAND,
                           target_word_count: int = TARGET_WORD_COUNT_AFTER_EXPAND,
                           max_iterations_override: Optional[int] = None) -> Dict[str, Any]:
        """
        :param progress_callback: 进度回调函数 callback(step_name, progress_0_to_1)
        :param skip_expand: 跳过扩写（用于重新闭环时防止内容膨胀）
        :param min_word_count: 最低字数要求 (低于此值触发扩写)
        :param target_word_count: 目标字数要求 (扩写/压缩的目标值)
        :return: 最终内容及元数据
        """
        raw_threshold = threshold
        raw_min_word_count = min_word_count
        raw_target_word_count = target_word_count
        threshold, min_word_count, target_word_count = _normalize_quality_loop_inputs(
            threshold=threshold,
            min_word_count=min_word_count,
            target_word_count=target_word_count,
            policy=self.policy,
        )

        if threshold != raw_threshold:
            logging.info(
                "QualityLoop 输入阈值已归一化: %s -> %.2f",
                raw_threshold,
                threshold,
            )
        if min_word_count != raw_min_word_count or target_word_count != raw_target_word_count:
            logging.info(
                "QualityLoop 字数约束已归一化: min=%s->%s, target=%s->%s",
                raw_min_word_count,
                min_word_count,
                raw_target_word_count,
                target_word_count,
            )

        override_iterations = _safe_cast(max_iterations_override, int, 0)
        if override_iterations > 0:
            max_iterations = min(50, override_iterations)
        else:
            max_iterations = self.policy.max_iterations
        set_llm_log_context(project_path=self.novel_path, chapter_num=chapter_num)

        normalized_initial_content = _normalize_initial_content(initial_content)
        if not normalized_initial_content:
            logging.warning(
                "QualityLoop 输入为空，跳过闭环（chapter=%s）",
                chapter_num,
            )
            return {
                "content": "",
                "final_score": 0.0,
                "iterations": 0,
                "status": "invalid_input",
                "hard_gate_blocked": False,
                "parse_failure_guard_engaged": False,
                "logs": [],
            }

        # Calculate thresholds based on dynamic parameters
        expand_threshold = min_word_count
        compress_threshold = int(target_word_count * 1.25) # 允许超出目标25%
        
        logging.info(f"📏 Chapter {chapter_num} Constraints: Min {expand_threshold}, Target {target_word_count}, Compress Limit {compress_threshold}")
        current_content = normalized_initial_content
        best_content = normalized_initial_content
        best_score = 0.0
        best_scores = {}  # Track details of the best version
        final_content = normalized_initial_content  # 🆕 初始化，防止 UnboundLocalError
        final_score = 0.0  # 🆕 初始化
        
        iteration = 0
        self.iteration_logs = []
        
        # 🆕 用于子方法记录日志
        self._current_chapter = chapter_num
        self._current_iteration = 0
        
        # 🆕 Fix 1.4: 重置差异化策略状态
        self._tried_dimensions = []
        self._retry_temperature_boost = 0.0
        
        # 🆕 存储当前章节的节奏指令（Fix 2.2: 情感曲线执行验证）
        self._current_pacing_directive = None
        self._last_round_score_info = {}
        
        # Stagnation variables
        previous_score = 0.0
        stagnation_count = 0
        regression_count = 0 # Count consecutive regressions from the same peak
        low_score_rewrite_count = 0  # 连续低分全量重写计数，避免陷入重写震荡
        parse_failure_streak = 0
        parse_failure_guard_engaged = False
        weakest_dim_last = None
        weakest_dim_streak = 0
        force_targeted_recovery = False

        logging.info(f"🔄 Starting Chapter {chapter_num} Quality Loop (Target: {threshold}, Max Iter: {max_iterations})")
        self._emit_progress(progress_callback, f"Chapter {chapter_num}: Starting Quality Loop (T={threshold})", 0.1)

        persistent_feedback = {}

        while iteration <= max_iterations:
            normalized_content, canonical_term, replaced_count = self._normalize_system_terms(current_content)
            if replaced_count > 0:
                current_content = normalized_content
                logging.info(
                    f"  [Iter {iteration}] 🔧 系统术语统一完成: 统一为'{canonical_term}', 替换{replaced_count}处。"
                )
                self._emit_progress(
                    progress_callback,
                    f"Chapter {chapter_num}: 术语统一->{canonical_term}",
                    0.18 + (iteration * 0.05)
                )
            cleaned_content, tech_replace_count = self._sanitize_external_track_terms(current_content)
            if tech_replace_count > 0:
                current_content = cleaned_content
                logging.info(
                    f"  [Iter {iteration}] 🔧 外轨术语清洗完成: 替换{tech_replace_count}处科技词。"
                )
                self._emit_progress(
                    progress_callback,
                    f"Chapter {chapter_num}: 外轨术语清洗({tech_replace_count})",
                    0.19 + (iteration * 0.05)
                )

            # 1. Quality Scoring
            self._emit_progress(
                progress_callback,
                f"Chapter {chapter_num}: Assessing Quality (Iter {iteration+1})",
                0.2 + (iteration * 0.05)
            )
            
            # If we just rolled back, don't re-eval, use cached scores
            if iteration > 0 and current_content == best_content and best_scores:
                scores = best_scores.copy()
                logging.info(f"  [Iter {iteration}] Using cached scores for best content.")
            else:
                scores = self.analyzer.analyze_content(current_content, chapter_num=chapter_num)

            if persistent_feedback:
                scores.update(persistent_feedback)
            
            overall_score = _resolve_overall_score(scores)
            llm_parse_failed = bool(scores.get("_llm_parse_failed", False))
            if llm_parse_failed:
                parse_failure_streak += 1
            else:
                parse_failure_streak = 0

            if parse_failure_streak >= self.policy.parse_failure_streak_limit:
                force_targeted_recovery = True
                if not parse_failure_guard_engaged:
                    parse_failure_guard_engaged = True
                    logging.warning(
                        "⚠️ Chapter %s 评分器解析连续失败(%s轮)，启用定向修复保护模式。",
                        chapter_num,
                        parse_failure_streak,
                    )

            # 前置规则：外轨科技词违规直接降分并强制进入整改
            dual_track_violations = self._detect_external_track_tech_terms(current_content)
            if dual_track_violations:
                scores['_dual_track_violations'] = dual_track_violations
                persistent_feedback['_dual_track_violations'] = dual_track_violations
                # 仅在明显出戏（>=3个违规词）时触发硬降分，减少误杀
                if len(dual_track_violations) >= 3:
                    overall_score = min(overall_score, 6.0)
            else:
                scores.pop('_dual_track_violations', None)
                persistent_feedback.pop('_dual_track_violations', None)

            logic_guard_issues = self._check_logic_guard_issues(current_content)
            if logic_guard_issues:
                scores['_logic_guard_issues'] = logic_guard_issues
                persistent_feedback['_logic_guard_issues'] = logic_guard_issues
                # 逻辑硬伤存在时，先压制得分进入修复回合
                overall_score = min(overall_score, 6.0)
            else:
                scores.pop('_logic_guard_issues', None)
                persistent_feedback.pop('_logic_guard_issues', None)

            # Critic gate is applied before best-version update to avoid keeping rejected versions.
            critic_pass = True
            critic_feedback = ""
            critic_score = None
            raw_score = overall_score
            critic_gate_reason = ""
            critic_should_invoke = self._should_invoke_critic(overall_score, threshold)
            critic_should_gate = overall_score >= threshold
            if critic_should_invoke:
                if critic_should_gate:
                    logging.info(f"  [Iter {iteration}] 🗳️ Technical Pass ({overall_score}). Consulting Critic Agent...")
                    self._emit_progress(progress_callback, f"Chapter {chapter_num}: 毒舌鉴赏中...", 0.85)
                else:
                    logging.info(
                        f"  [Iter {iteration}] 🧪 Critic logging forced below threshold "
                        f"({overall_score:.2f}<{threshold:.2f})."
                    )
                critic_result = self.critic_agent.critique_chapter(
                    current_content,
                    chapter_num=chapter_num,
                    project_path=self.novel_path,
                    stage=f"critic_agent_iter_{iteration + 1}",
                    iteration=iteration + 1,
                )
                critic_rating = critic_result.get('rating', 'Pass')
                parse_failed = bool(critic_result.get("parse_failed", False))
                try:
                    critic_score = float(critic_result.get('score', 7.5))
                except (TypeError, ValueError):
                    critic_score = 7.5

                if critic_should_gate:
                    if parse_failed:
                        logging.warning("⚠️ Critic 输出解析失败，本轮跳过毒舌门控，不触发拒收。")
                    elif critic_rating == 'Reject' or critic_score < threshold:
                        critic_pass = False
                        critic_feedback = (
                            f"【毒舌读者拒收】评分{critic_score}(<阈值{threshold})。毒评：{critic_result.get('toxic_comment')}。"
                            f"整改要求：{critic_result.get('improvement_demand')}"
                        )
                        logging.warning(f"⛔ Critic Rejected! Score: {critic_score}. Reason: {critic_feedback}")
                        scores['毒舌反馈'] = critic_feedback
                        persistent_feedback['毒舌反馈'] = critic_feedback
                        overall_score = 6.0
                    else:
                        logging.info(f"✨ Critic Approved! Score: {critic_score}. Comment: {critic_result.get('toxic_comment')}")
                        persistent_feedback.pop('毒舌反馈', None)
                        self._emit_progress(progress_callback, f"✨ 毒舌认可: {critic_score}分", 0.9)
                else:
                    if parse_failed:
                        logging.warning("⚠️ Critic 输出解析失败（强制日志模式）。")
                    else:
                        logging.info(
                            f"📝 Critic 已记录（强制日志模式），评分={critic_score}，判定={critic_rating}。"
                        )
                    critic_gate_reason = f"critic_forced_logging_only({overall_score:.2f}<{threshold:.2f})"
            else:
                if not self.critic_agent:
                    critic_gate_reason = "critic_agent_unavailable"
                elif overall_score < threshold:
                    critic_gate_reason = f"critic_skipped_below_threshold({overall_score:.2f}<{threshold:.2f})"

            logging.info(
                f"  [Iter {iteration}] Score: {overall_score} (raw={raw_score}, Length={scores.get('字数', 0)})"
            )

            trigger_reasons = []
            if overall_score < threshold:
                trigger_reasons.append("score_below_threshold")
            if llm_parse_failed:
                trigger_reasons.append("llm_score_parse_failed")
            if parse_failure_streak >= self.policy.parse_failure_streak_limit:
                trigger_reasons.append(f"llm_parse_failure_streak:{parse_failure_streak}")
            if dual_track_violations:
                trigger_reasons.append(f"dual_track_tech_terms:{len(dual_track_violations)}")
            if not critic_pass:
                trigger_reasons.append("critic_reject")
            if logic_guard_issues:
                trigger_reasons.append(f"logic_guard_issues:{len(logic_guard_issues)}")
            if critic_gate_reason:
                trigger_reasons.append(critic_gate_reason)

            unresolved_conflicts = []
            if self.consistency_checker:
                unresolved_conflicts = self.consistency_checker.check_consistency(current_content, chapter_num)
                if unresolved_conflicts:
                    scores['_unresolved_conflicts'] = unresolved_conflicts
                    persistent_feedback['_unresolved_conflicts'] = unresolved_conflicts
                    trigger_reasons.append(f"unresolved_conflicts:{len(unresolved_conflicts)}")
                    if self.consistency_hard_gate and any(c.get("severity") == "high" for c in unresolved_conflicts):
                        trigger_reasons.append("hard_gate_rule_conflict")
                else:
                    scores.pop('_unresolved_conflicts', None)
                    persistent_feedback.pop('_unresolved_conflicts', None)

            llm_consistency_review = ""
            if self.enable_llm_consistency_check:
                llm_consistency_review = self._run_llm_consistency_review(current_content)
                if llm_consistency_review and has_obvious_conflict(llm_consistency_review):
                    conflict_items = extract_conflict_items(llm_consistency_review, limit=3)
                    if conflict_items:
                        scores['_llm_conflict_items'] = conflict_items
                        persistent_feedback['_llm_conflict_items'] = conflict_items
                        scores['_llm_consistency_review'] = llm_consistency_review
                        persistent_feedback['_llm_consistency_review'] = llm_consistency_review
                        trigger_reasons.append("llm_consistency_conflict")
                        if self.consistency_hard_gate:
                            trigger_reasons.append("hard_gate_llm_consistency")
                    else:
                        # 仅有抽象/建议性风险时，不触发硬阻断，避免误杀。
                        scores.pop('_llm_conflict_items', None)
                        persistent_feedback.pop('_llm_conflict_items', None)
                        scores.pop('_llm_consistency_review', None)
                        persistent_feedback.pop('_llm_consistency_review', None)
                        logging.info("LLM一致性审校未给出可验证冲突条目，降级为提示")
                else:
                    scores.pop('_llm_conflict_items', None)
                    persistent_feedback.pop('_llm_conflict_items', None)
                    scores.pop('_llm_consistency_review', None)
                    persistent_feedback.pop('_llm_consistency_review', None)

            timeline_conflicts = []
            if self.enable_timeline_check and self.timeline_manager:
                timeline_conflicts = self.timeline_manager.check_timeline_consistency(current_content, chapter_num)
                if timeline_conflicts:
                    scores['_timeline_conflicts'] = timeline_conflicts
                    persistent_feedback['_timeline_conflicts'] = timeline_conflicts
                    trigger_reasons.append(f"timeline_conflicts:{len(timeline_conflicts)}")
                    if self.timeline_hard_gate and any(c.get("severity") == "high" for c in timeline_conflicts):
                        trigger_reasons.append("hard_gate_timeline_conflict")
                else:
                    scores.pop('_timeline_conflicts', None)
                    persistent_feedback.pop('_timeline_conflicts', None)

            safety_issues = persistent_feedback.get('_safety_issues') or []
            if safety_issues:
                trigger_reasons.append(f"safety_issues:{len(safety_issues)}")
            pattern_issues = persistent_feedback.get('_pattern_issues') or []
            if pattern_issues:
                trigger_reasons.append(f"pattern_issues:{len(pattern_issues)}")
            if not trigger_reasons:
                trigger_reasons.append("pass")

            guard_feedback_parts: List[str] = []
            if dual_track_violations:
                guard_feedback_parts.append(
                    f"外轨术语: 命中{len(dual_track_violations)}处({', '.join(dual_track_violations[:3])})"
                )
            if logic_guard_issues:
                guard_feedback_parts.append(
                    f"逻辑硬规则: {'；'.join(logic_guard_issues[:2])}"
                )
            llm_conflict_items = scores.get('_llm_conflict_items', []) or []
            if llm_conflict_items:
                guard_feedback_parts.append(
                    f"LLM冲突: {'；'.join([str(x) for x in llm_conflict_items[:2]])}"
                )
            guard_feedback = " | ".join(guard_feedback_parts)
            pass_reasons: List[str] = []
            if overall_score >= threshold:
                pass_reasons.append(f"分数达标({overall_score:.2f}>={threshold:.2f})")
                if not dual_track_violations:
                    pass_reasons.append("外轨术语检查通过")
                if not logic_guard_issues:
                    pass_reasons.append("逻辑硬规则检查通过")
                if not unresolved_conflicts:
                    pass_reasons.append("规则一致性检查通过")
                if not llm_conflict_items:
                    pass_reasons.append("LLM一致性检查通过")
                if not timeline_conflicts:
                    pass_reasons.append("时间线检查通过")
                if self.critic_agent:
                    if critic_pass and isinstance(critic_score, (int, float)):
                        pass_reasons.append(f"毒舌认可({float(critic_score):.2f})")
                else:
                    pass_reasons.append("毒舌门控未启用")

            score_event = {
                "event_type": "score_round",
                "chapter": chapter_num,
                "iteration": iteration,
                "raw_score": raw_score,
                "critic_score": critic_score,
                "final_score": overall_score,
                "threshold": threshold,
                "trigger_reasons": trigger_reasons,
                "critic_feedback": critic_feedback if critic_feedback else "",
                "guard_feedback": guard_feedback,
                "pass_reasons": pass_reasons,
                "llm_parse_failed": llm_parse_failed,
                "parse_failure_streak": parse_failure_streak,
            }
            self._last_round_score_info = {
                "chapter_num": chapter_num,
                "iteration": iteration,
                "raw_score": raw_score,
                "final_score": overall_score,
                "threshold": threshold,
                "trigger_reasons": trigger_reasons,
                "critic_feedback": critic_feedback if critic_feedback else "",
                "guard_feedback": guard_feedback,
                "pass_reasons": pass_reasons,
                "llm_parse_failed": llm_parse_failed,
                "parse_failure_streak": parse_failure_streak,
            }
            self._emit_progress(
                progress_callback,
                f"Chapter {chapter_num}: 评分轮次 {iteration + 1}",
                0.22 + (iteration * 0.05),
                score_event
            )
            
            self.iteration_logs.append({
                "iteration": iteration,
                "score": overall_score,
                "details": scores,
                "raw_score": raw_score,
                "critic_score": critic_score,
                "final_score": overall_score,
                "trigger_reasons": trigger_reasons,
                "critic_feedback": critic_feedback if critic_feedback else "",
                "guard_feedback": guard_feedback,
                "llm_parse_failed": llm_parse_failed,
                "parse_failure_streak": parse_failure_streak,
            })

            # Record low scores for learning
            if self.problem_learner and overall_score < threshold:
                self.problem_learner.record_low_score(chapter_num, scores, threshold=threshold - 1)

            # Update Best Version
            if overall_score > best_score:
                best_score = overall_score
                best_content = current_content
                best_scores = scores
                regression_count = 0 # Reset regression count on new peak
            elif iteration > 0 and overall_score < best_score - 0.3:
                # Regression Detected
                regression_count += 1
                logging.warning(f"  [Iter {iteration}] Regression detected ({overall_score} < {best_score}). Reverting to best version.")
                
                # Rollback to best
                current_content = best_content
                
                # 🆕 Fix 1.4: 差异化重试策略
                # 提升temperature增加探索空间
                self._retry_temperature_boost = min(0.3, self._retry_temperature_boost + 0.1)
                logging.info(f"  [Iter {iteration}] 🎲 差异化策略: temperature_boost={self._retry_temperature_boost:.1f}, tried_dims={self._tried_dimensions}")
                
                if regression_count >= 3:
                     logging.warning(f"🛑 Stuck at local maximum ({best_score}) for 3 tries. Stopping early.")
                     break
                
                # Skip the rest of this loop to "restart" from best state (effectively next iter)
                # But we need to increment iteration to avoid infinite loop
                iteration += 1
                continue

            # Stagnation Check (Small changes)
            if iteration > 0:
                score_delta = abs(overall_score - previous_score)
                if score_delta < self.policy.stagnation_threshold:
                    stagnation_count += 1
                    logging.info(f"  [Iter {iteration}] ⚠️ Stagnation (Delta: {score_delta:.2f}, Count: {stagnation_count})")
                    if stagnation_count >= self.policy.stagnation_count_limit:
                        logging.info(f"🛑 Stagnation limit reached. Stopping. (Current: {overall_score})")
                        break
                else:
                    stagnation_count = 0
            
            previous_score = overall_score

            # 2. Check Success
            if overall_score >= threshold:
                hard_gate_blocked = self.consistency_hard_gate and (
                    "hard_gate_rule_conflict" in trigger_reasons or
                    "hard_gate_llm_consistency" in trigger_reasons
                )
                hard_gate_blocked = hard_gate_blocked or (
                    self.timeline_hard_gate and "hard_gate_timeline_conflict" in trigger_reasons
                )
                if hard_gate_blocked:
                    logging.warning(
                        f"⛔ Chapter {chapter_num} 分数达标但触发一致性硬阻断，继续优化。"
                    )
                else:
                    if critic_pass:
                        logging.info(f"✅ Chapter {chapter_num} reached quality standard ({overall_score} >= {threshold})")
                        self._emit_progress(progress_callback, f"Chapter {chapter_num}: Quality Met ({overall_score})", 0.9)

                        final_content = current_content
                    final_score = overall_score
                    # Use Chinese char count for logic
                    content_len = count_chapter_words(current_content)['chinese_chars']
                
                    # Check Length - Compression（默认关闭，避免压缩引起评分下滑）
                    if self.policy.enable_compression and content_len > compress_threshold:
                        self._emit_progress(progress_callback, f"📦 Compressing: {content_len}->{target_word_count}...", 0.95)
                        logging.info(f"📦 Chapter {chapter_num} too long ({content_len} > {compress_threshold}), compressing to ~{target_word_count}...")
                        compressed = self._compress_content(current_content, chapter_num, target_word_count, progress_callback)
                        compressed_len = count_chapter_words(compressed)['chinese_chars'] if compressed else 0

                        if compressed and compressed_len < content_len:
                            compressed_scores = self.analyzer.analyze_content(compressed, chapter_num=chapter_num)
                            compressed_score = _resolve_overall_score(compressed_scores)
                            if compressed_score >= overall_score - self.policy.word_count_adjust_score_tolerance - 0.5:  # 扩宽容忍度 (+0.5)
                                final_content = compressed
                                final_score = compressed_score
                                logging.info(f"✅ Compression success: {content_len} -> {compressed_len} (Score: {overall_score} -> {compressed_score})")
                                self._emit_progress(progress_callback, f"✅ Compressed: {content_len}->{compressed_len} (Sc:{overall_score}->{compressed_score})", 0.98)

                                # 🆕 P2 修复：压缩后字数仍低于下限，触发再扩写
                                if compressed_len < expand_threshold and not skip_expand:
                                    logging.warning(f"⚠️ Compressed content ({compressed_len}) still below min ({expand_threshold}). Re-expanding...")
                                    self._emit_progress(progress_callback, f"📝 Re-Expanding: {compressed_len}->{target_word_count}...", 0.96)
                                    re_expanded = self._expand_content(final_content, chapter_num, target_word_count, progress_callback)
                                    re_expanded_len = count_chapter_words(re_expanded)['chinese_chars'] if re_expanded else 0
                                    if re_expanded and re_expanded_len >= expand_threshold:
                                        re_expanded_scores = self.analyzer.analyze_content(re_expanded, chapter_num=chapter_num)
                                        re_expanded_score = _resolve_overall_score(re_expanded_scores)
                                        if re_expanded_score >= final_score - self.policy.word_count_adjust_score_tolerance:
                                            final_content = re_expanded
                                            final_score = re_expanded_score
                                            logging.info(f"✅ Re-Expansion success: {compressed_len} -> {re_expanded_len}")
                                            self._emit_progress(progress_callback, f"✅ Re-Expanded: {compressed_len}->{re_expanded_len}", 0.99)
                            else:
                                logging.warning(f"⚠️ Compression degraded score too much, keeping original.")
                                self._emit_progress(progress_callback, f"⚠️ Comp Rejected: Score dropped {overall_score}->{compressed_score}", 0.98)
                        else:
                            logging.warning(f"⚠️ Compression failed, keeping original.")

                    # Check Length - Expansion（重新闘环时跳过，防止内容膨胀）
                    elif content_len < expand_threshold and not skip_expand:
                        self._emit_progress(progress_callback, f"📝 Expanding: {content_len}->{target_word_count}...", 0.95)
                        logging.info(f"📝 Chapter {chapter_num} too short ({content_len} < {expand_threshold}), expanding to ~{target_word_count}...")
                        expanded = self._expand_content(current_content, chapter_num, target_word_count, progress_callback)
                        expanded_len = count_chapter_words(expanded)['chinese_chars'] if expanded else 0

                        if expanded and expanded_len > content_len:
                            expanded_scores = self.analyzer.analyze_content(expanded, chapter_num=chapter_num)
                            expanded_score = _resolve_overall_score(expanded_scores)
                            if expanded_score >= overall_score - self.policy.word_count_adjust_score_tolerance:
                                final_content = expanded
                                final_score = expanded_score
                                logging.info(f"✅ Expansion success: {content_len} -> {expanded_len} (Score: {overall_score} -> {expanded_score})")
                                self._emit_progress(progress_callback, f"✅ Expanded: {content_len}->{expanded_len} (Sc:{overall_score}->{expanded_score})", 0.98)
                            else:
                                logging.warning(f"⚠️ Expansion degraded score too much, keeping original.")
                                self._emit_progress(progress_callback, f"⚠️ Exp Rejected: Score dropped {overall_score}->{expanded_score}", 0.98)
                        else:
                            logging.warning(f"⚠️ Expansion failed, keeping original.")
                
                    self._post_loop_updates(final_content, chapter_num, final_score, best_scores, iteration)
                    return {
                        "content": final_content,
                        "final_score": final_score,
                        "iterations": iteration,
                        "status": "success",
                        "hard_gate_blocked": False,
                        "parse_failure_guard_engaged": bool(parse_failure_guard_engaged),
                        "logs": self.iteration_logs
                    }
            
            if iteration >= max_iterations:
                logging.warning(f"⚠️ Chapter {chapter_num} reached max iterations ({max_iterations}). Returning best version ({best_score}).")
                break

            # 3. Generate Improvement Plan
            improvement_plan = self._generate_improvement_plan(scores, current_content, chapter_num)
            
            # 🆕 显示最弱维度（帮助诊断优化焦点）
            dims_to_check = ["剧情连贯性", "角色一致性", "写作质量", "情感张力", "系统机制", "架构遵循度", "设定遵循度"]
            weak_dims = {d: scores.get(d, 10) for d in dims_to_check if isinstance(scores.get(d), (int, float)) and scores.get(d, 10) < 8.0}
            weakest = None
            if weak_dims and progress_callback:
                weakest = min(weak_dims, key=weak_dims.get)
                self._emit_progress(
                    progress_callback,
                    f"Chapter {chapter_num}: 弱项={weakest}({weak_dims[weakest]:.1f})",
                    0.28 + (iteration * 0.05)
                )

            # 停滞熔断：同一最弱维度连续3轮不变时，禁止继续全量重写，改为定向修复
            if weakest is not None:
                if weakest == weakest_dim_last:
                    weakest_dim_streak += 1
                else:
                    weakest_dim_last = weakest
                    weakest_dim_streak = 1
                if weakest_dim_streak >= 3:
                    force_targeted_recovery = True
                    logging.info(
                        f"  [Iter {iteration}] 🛑 弱项停滞熔断触发: '{weakest}' 连续{weakest_dim_streak}轮，切换到定向修复模式。"
                    )
                    self._emit_progress(
                        progress_callback,
                        f"Chapter {chapter_num}: 停滞熔断(弱项={weakest})",
                        0.29 + (iteration * 0.05)
                    )
            
            # 4. Graded Optimization Strategy
            severe_threshold = threshold - self.policy.severe_threshold_offset
            
            if overall_score < severe_threshold:
                low_score_rewrite_count += 1
            else:
                low_score_rewrite_count = 0

            if (
                overall_score < severe_threshold
                and low_score_rewrite_count <= 2
                and not llm_parse_failed
                and not force_targeted_recovery
            ):
                # Severe Issue -> Full Rewrite（仅前两次，后续改定向修复避免震荡）
                logging.info(f"  [Iter {iteration}] Score Low ({overall_score}<{severe_threshold}), executing **Full Rewrite**...")
                self._emit_progress(
                    progress_callback,
                    f"Chapter {chapter_num}: Low Score ({overall_score}), Rewriting...",
                    0.3 + (iteration * 0.05)
                )
                new_content = self._rewrite_chapter(current_content, improvement_plan, min_word_count, target_word_count, compress_threshold)
            else:
                # Moderate Issue -> Targeted Optimization + Polishing
                if overall_score < severe_threshold and llm_parse_failed:
                    logging.warning(
                        f"  [Iter {iteration}] LLM评分解析失败回退，避免误杀：跳过 Full Rewrite，改为 Targeted Recovery。"
                    )
                    self._emit_progress(
                        progress_callback,
                        f"Chapter {chapter_num}: 评分回退，改定向修复...",
                        0.3 + (iteration * 0.05)
                    )
                elif overall_score < severe_threshold:
                    logging.info(
                        f"  [Iter {iteration}] Low-score stagnation detected (count={low_score_rewrite_count}), "
                        f"switching to **Targeted Recovery**."
                    )
                    self._emit_progress(
                        progress_callback,
                        f"Chapter {chapter_num}: Low Score Stagnating, Targeted Recovery...",
                        0.3 + (iteration * 0.05)
                    )
                logging.info(f"  [Iter {iteration}] Score Okay ({overall_score}>={severe_threshold}), executing **Targeted Optimization**...")
                self._emit_progress(
                    progress_callback,
                    f"Chapter {chapter_num}: Optimizing ({overall_score})...",
                    0.3 + (iteration * 0.05)
                )
                
                weak_dimensions = []
                for dim in ["剧情连贯性", "角色一致性", "写作质量", "情感张力", "系统机制", "架构遵循度", "设定遵循度"]:
                    dim_value = scores.get(dim)
                    if dim_value is not None and isinstance(dim_value, (int, float)):
                        if float(dim_value) < 7.5:
                            weak_dimensions.append(dim)
                
                genre_hints = scores.get("题材改进建议", [])
                if isinstance(genre_hints, list):
                    for hint in genre_hints:
                        if isinstance(hint, str) and "【" in hint and "】" in hint:
                            try:
                                dim_name = hint.split("【")[1].split("】")[0]
                                weak_dimensions.append(dim_name)
                            except:
                                pass
                
                optimized_content = self._targeted_optimize(current_content, improvement_plan, weak_dimensions)
                
                logging.info(f"  [Iter {iteration}] Polishing content...")
                new_content = self._polish_content(optimized_content)
            
            # Sanity Check
            if len(new_content) < len(current_content) * 0.7:
                logging.warning(f"  [Iter {iteration}] Content length dropped suspicious amount, discarding change.")
                # We revert to current_content (which is best_content if we just rolled back, or prev content)
                # Effectively we waste an iteration but save quality.
            else:
                # 🆕 内容变化检测（同时输出到控制台和UI）
                content_changed = new_content != current_content
                if not content_changed:
                    logging.warning(f"  [Iter {iteration}] ⚠️ 优化后内容无变化！")
                    self._emit_progress(
                        progress_callback,
                        f"Chapter {chapter_num}: ⚠️ 内容无变化",
                        0.35 + (iteration * 0.05)
                    )
                else:
                    # 计算变化率
                    change_ratio = 1 - (sum(1 for a, b in zip(new_content[:1000], current_content[:1000]) if a == b) / min(len(new_content[:1000]), len(current_content[:1000]), 1000))
                    logging.info(f"  [Iter {iteration}] 内容变化率: {change_ratio:.1%}")
                    self._emit_progress(
                        progress_callback,
                        f"Chapter {chapter_num}: 变化率 {change_ratio:.0%}",
                        0.35 + (iteration * 0.05)
                    )
                current_content = new_content
            
            # 🆕 Fix 1.1: 一致性修复效果二次验证
            if self.consistency_checker:
                remaining_conflicts = self.consistency_checker.check_consistency(current_content, chapter_num)
                if remaining_conflicts:
                    conflict_msgs = [c['message'] for c in remaining_conflicts[:3]]
                    logging.warning(f"  [Iter {iteration}] ⚠️ 优化后仍存在 {len(remaining_conflicts)} 个一致性问题: {conflict_msgs}")
                    # 将未解决的矛盾注入到 scores 中，确保下一轮优化重点关注
                    scores['_unresolved_conflicts'] = remaining_conflicts
                    persistent_feedback['_unresolved_conflicts'] = remaining_conflicts
                else:
                    scores.pop('_unresolved_conflicts', None)
                    persistent_feedback.pop('_unresolved_conflicts', None)
                    logging.info(f"  [Iter {iteration}] ✅ 一致性问题已全部修正")
            
            # 🆕 敏感内容过滤检查
            if self.safety_filter:
                safety_result = self.safety_filter.check_content(current_content)
                if safety_result.get('risk_level', 'safe') == 'high':
                    logging.warning(f"  [Iter {iteration}] 🛡️ 检测到高风险内容: {safety_result.get('issues', [])[:3]}")
                    scores['_safety_issues'] = safety_result.get('issues', [])
                    persistent_feedback['_safety_issues'] = safety_result.get('issues', [])
                else:
                    persistent_feedback.pop('_safety_issues', None)
            
            # 🆕 叙事模式重复检测（每轮检查，但仅记录警告，不阻塞）
            if self.pattern_detector and iteration == 0:  # 仅首次迭代检查，避免重复告警
                try:
                    pattern_issues = self.pattern_detector.check_pattern_repetition(current_content, chapter_num)
                    if pattern_issues:
                        scores['_pattern_issues'] = pattern_issues
                        persistent_feedback['_pattern_issues'] = pattern_issues
                        for pi in pattern_issues[:2]:
                            logging.warning(f"  [Iter {iteration}] 🔄 叙事模式告警: {pi}")
                    else:
                        persistent_feedback.pop('_pattern_issues', None)
                except (RuntimeError, ValueError, TypeError) as e:
                    logging.debug(f"叙事模式检测异常: {e}")
            
            iteration += 1
            self._current_iteration = iteration  # 🆕 更新迭代跟踪

        # Return Best Content
        final_content = best_content
        final_score = best_score
        content_len = count_chapter_words(best_content)['chinese_chars']
        
        # Final Compression Check on Best Content（默认关闭）
        if self.policy.enable_compression and content_len > compress_threshold:
             self._emit_progress(progress_callback, f"📦 Final Compress: {content_len}->{target_word_count}", 1.0)
             logging.info(f"📦 Final check: Chapter {chapter_num} too long ({content_len}), compressing...")
             compressed = self._compress_content(best_content, chapter_num, target_word_count, progress_callback)
             compressed_len = count_chapter_words(compressed)['chinese_chars'] if compressed else 0
             
             if compressed and compressed_len < content_len:
                compressed_scores = self.analyzer.analyze_content(compressed, chapter_num=chapter_num)
                compressed_score = _resolve_overall_score(compressed_scores)
                if compressed_score >= best_score - self.policy.word_count_adjust_score_tolerance:
                    final_content = compressed
                    final_score = compressed_score
                    logging.info(f"✅ Final compression success: {content_len} -> {compressed_len}")
                    self._emit_progress(progress_callback, f"✅ Compressed: {content_len}->{compressed_len} (Sc:{best_score}->{compressed_score})", 1.0)
                else:
                    logging.warning(f"⚠️ Final compression degraded score too much, keeping original best.")
                    self._emit_progress(progress_callback, f"⚠️ Comp Rejected: Score dropped {best_score}->{compressed_score}", 1.0)
             else:
                logging.warning(f"⚠️ Final compression failed, keeping original best.")
        # Final Expansion Check on Best Content（重新闘环时跳过，防止内容膨胀）
        elif content_len < expand_threshold and not skip_expand:
            self._emit_progress(progress_callback, f"📝 Final Expand: {content_len}->{target_word_count}", 1.0)
            logging.info(f"📝 Final check: Chapter {chapter_num} too short ({content_len}), expanding...")
            expanded = self._expand_content(best_content, chapter_num, target_word_count, progress_callback)
            expanded_len = count_chapter_words(expanded)['chinese_chars'] if expanded else 0
            
            if expanded and expanded_len > content_len:
                expanded_scores = self.analyzer.analyze_content(expanded, chapter_num=chapter_num)
                expanded_score = _resolve_overall_score(expanded_scores)
                
                if expanded_score >= best_score - self.policy.word_count_adjust_score_tolerance:
                    final_content = expanded
                    final_score = expanded_score
                    logging.info(f"✅ Final expansion success: {content_len} -> {expanded_len}")
                    self._emit_progress(progress_callback, f"✅ Expanded: {content_len}->{expanded_len} (Sc:{best_score}->{expanded_score})", 1.0)
                else:
                    logging.warning(f"⚠️ 扩写后评分下降过多({best_score} -> {expanded_score})，保留原版")
                    self._emit_progress(progress_callback, f"⚠️ Exp Rejected: Score dropped {best_score}->{expanded_score}", 1.0)
            else:
                logging.warning(f"⚠️ 扩写失败或无效，保留原版")
        elif content_len < expand_threshold and skip_expand:
            logging.info(f"⏭️ Final check: 跳过扩写（skip_expand=True）")

        # 🆕 闭环结束后：更新所有追踪器 & 记录统计
        self._post_loop_updates(final_content, chapter_num, final_score, best_scores, iteration)
        last_reasons = []
        if self.iteration_logs:
            last_reasons = self.iteration_logs[-1].get("trigger_reasons", []) or []
        hard_gate_blocked = any(
            r in (
                "hard_gate_rule_conflict",
                "hard_gate_llm_consistency",
                "hard_gate_timeline_conflict",
            )
            for r in last_reasons
        )
        final_status = "hard_gate_blocked" if hard_gate_blocked else "max_iterations_reached"
        
        return {
            "content": final_content,
            "final_score": final_score,
            "iterations": iteration,
            "status": final_status,
            "hard_gate_blocked": hard_gate_blocked,
            "parse_failure_guard_engaged": bool(parse_failure_guard_engaged),
            "logs": self.iteration_logs
        }

    def _load_canonical_system_term(self) -> Optional[str]:
        """从架构文件抽取首选系统术语，用于闭环内一致性强制对齐。"""
        arch_text = self._read_project_text("Novel_architecture.txt")
        if not arch_text:
            return None

        terms = re.findall(
            r"(?<![A-Za-z0-9\u4e00-\u9fa5])([A-Za-z0-9\u4e00-\u9fa5·\-]{2,10}系统)(?![A-Za-z0-9\u4e00-\u9fa5])",
            arch_text,
        )
        ordered = []
        for t in terms:
            if t not in ordered and self._is_valid_system_term(t):
                ordered.append(t)
        if not ordered:
            return None
        for t in ordered:
            if t != "系统":
                return t
        return ordered[0]

    def _normalize_system_terms(self, content: str) -> Tuple[str, Optional[str], int]:
        """统一同章多系统命名，避免“金手指/系统命名不一致”硬闸。"""
        if not content:
            return content, None, 0
        terms = re.findall(
            r"(?<![A-Za-z0-9\u4e00-\u9fa5])([A-Za-z0-9\u4e00-\u9fa5·\-]{2,10}系统)(?![A-Za-z0-9\u4e00-\u9fa5])",
            content,
        )
        ordered = []
        for t in terms:
            if t not in ordered and self._is_valid_system_term(t):
                ordered.append(t)
        if len(ordered) <= 1:
            return content, ordered[0] if ordered else None, 0

        canonical = self._canonical_system_term
        if not canonical or canonical not in ordered:
            non_generic = [t for t in ordered if t != "系统"]
            canonical = non_generic[0] if non_generic else ordered[0]

        replaced = 0
        fixed = content
        for term in ordered:
            if term == canonical:
                continue
            cnt = len(re.findall(re.escape(term), fixed))
            if cnt > 0:
                fixed = re.sub(re.escape(term), canonical, fixed)
                replaced += cnt
        return fixed, canonical, replaced

    @staticmethod
    def _is_valid_system_term(term: str) -> bool:
        """过滤误提取的长短语，保留真正的“术语级系统名”"""
        if not term or "系统" not in term:
            return False
        t = term.strip()
        if len(t) < 2 or len(t) > 10:
            return False
        invalid_parts = ("直接", "构建", "循环", "经脉", "灵气", "一个", "在", "点击", "小型", "大型")
        if any(p in t for p in invalid_parts):
            return False
        return True

    @staticmethod
    def _sanitize_external_track_terms(content: str) -> Tuple[str, int]:
        """清洗明显出戏的科技词，统一替换为仙侠语境术语。"""
        if not content:
            return content, 0
        replacements = [
            (r"检测", "感应"),
            (r"校正", "梳理"),
            (r"程序", "法门"),
            (r"功德点", "功德"),
            (r"面板", "识海示现"),
            (r"下载", "承接"),
            (r"\bBug\b|\bbug\b", "隐患"),
            (r"CPU", "灵台"),
            (r"服务器", "阵枢"),
        ]
        fixed = content
        total = 0
        for pat, rep in replacements:
            fixed, cnt = re.subn(pat, rep, fixed)
            total += cnt
        return fixed, total

    @staticmethod
    def _check_logic_guard_issues(content: str) -> List[str]:
        """硬规则：重伤逻辑/反派行为可信度，未满足则强制进入修复。"""
        if not content:
            return []

        issues: List[str] = []
        # 1) 重伤逻辑：若出现严重伤势设定，必须体现痛感或行动受限
        severe_injury_markers = ("经脉寸断", "丹田破碎", "重伤", "半死", "废了修为")
        injury_context = any(m in content for m in severe_injury_markers)
        if injury_context:
            pain_markers = ("剧痛", "刺痛", "咳血", "冷汗", "痛得", "痉挛")
            limited_action_markers = ("踉跄", "站不稳", "扶墙", "跪地", "几乎站立不住", "气息紊乱")
            if not any(m in content for m in pain_markers) or not any(m in content for m in limited_action_markers):
                issues.append("重伤表现不足：缺少痛感/行动受限描写，伤势可信度不足")

        # 2) 反派行为：若反派已出场并冲突成立，至少要有实际动作/施压行为
        # 简化判定：出现“嘲讽+冲突”时，必须出现动作动词之一
        taunt_markers = ("废物", "找死", "认罪", "跪下", "嘲讽")
        conflict_hint = any(m in content for m in taunt_markers)
        action_markers = ("出手", "掐", "踢", "挥", "斩", "抓", "叫人", "传讯", "按住", "封锁")
        if conflict_hint and not any(m in content for m in action_markers):
            issues.append("反派行为过弱：仅嘴炮缺少实际动作，冲突压迫感不足")

        return issues

    def _post_loop_updates(self, final_content: str, chapter_num: int,
                           final_score: float, best_scores: Dict, iterations: int):
        """闭环结束后更新所有追踪器并记录统计"""

        # 0. 更新规则事实库（供跨章一致性检查使用）
        if self.consistency_checker:
            try:
                self.consistency_checker.update_facts(final_content, chapter_num)
            except (OSError, json.JSONDecodeError, RuntimeError, ValueError, TypeError) as e:
                logging.debug(f"一致性事实库更新异常: {e}")

        if self.timeline_manager:
            try:
                self.timeline_manager.update_timeline(final_content, chapter_num)
            except (OSError, json.JSONDecodeError, RuntimeError, ValueError, TypeError) as e:
                logging.debug(f"时间线账本更新异常: {e}")
        
        # 1. 记录生成统计 + 异常检测
        if self.stats_monitor:
            try:
                self.stats_monitor.record_chapter_stats(
                    chapter_num, best_scores, iterations, 
                    "success" if final_score >= self.policy.default_quality_threshold else "best_effort"
                )
                anomalies = self.stats_monitor.detect_anomalies(chapter_num)
                for warning in anomalies:
                    logging.warning(f"📈 {warning}")
            except (OSError, json.JSONDecodeError, RuntimeError, ValueError, TypeError) as e:
                logging.debug(f"生成统计记录异常: {e}")
        
        # 2. 注册悬念 + 检测回收
        if self.hook_tracker:
            try:
                self.hook_tracker.register_hooks(final_content, chapter_num)
                resolved = self.hook_tracker.check_resolutions(final_content, chapter_num)
                stats = self.hook_tracker.get_stats()
                logging.info(f"🎣 悬念状态: 开放{stats.get('open', 0)}, "
                             f"本章回收{resolved}, 回收率{stats.get('resolution_rate', 0):.0%}")
            except (OSError, json.JSONDecodeError, RuntimeError, ValueError, TypeError) as e:
                logging.debug(f"悬念追踪更新异常: {e}")
        
        # 3. 更新叙事线程
        if self.thread_tracker:
            try:
                self.thread_tracker.update_threads(final_content, chapter_num)
                dormant = self.thread_tracker.get_dormant_threads(chapter_num)
                if dormant:
                    logging.info(f"🧵 {len(dormant)}条叙事线休眠: "
                                 f"{', '.join(d['name'] for d in dormant[:3])}")
            except Exception as e:
                logging.debug(f"叙事线程更新异常: {e}")
        
        # 4. 记录叙事模式
        if self.pattern_detector:
            try:
                self.pattern_detector.record_chapter_pattern(final_content, chapter_num)
            except Exception as e:
                logging.debug(f"叙事模式记录异常: {e}")
        
        # 5. 更新角色声音指纹
        if self.voice_tracker:
            try:
                self.voice_tracker.update_voice_db(final_content, chapter_num)
            except Exception as e:
                logging.debug(f"角色声音指纹更新异常: {e}")


    def _generate_improvement_plan(self, scores: Dict, content: str, chapter_num: int = 0) -> str:
        """Generate specific improvement plan based on weak dimensions."""
        
        # 找出最低的维度（只专注1个）
        # 🔧 过滤掉非数值类型的维度
        exclude_keys = ['字数', '综合评分', '评分模式', '题材维度', '题材综合分', '检测题材', '题材改进建议',
                        '_unresolved_conflicts', '_safety_issues', '_pattern_issues', '_timeline_conflicts', '毒舌反馈']
        dimensions = []
        for k, v in scores.items():
            if k not in exclude_keys and isinstance(v, (int, float)):
                dimensions.append(k)
        
        # 安全的排序：确保值是数值类型
        def safe_get_score(dim):
            val = scores.get(dim, 10)
            if isinstance(val, (int, float)):
                return float(val)
            return 10.0
        
        sorted_dims = sorted(dimensions, key=safe_get_score)
        
        # 🆕 Fix 1.4: 差异化重试 — 回退后避免重复优化同一维度
        weakest_dim = sorted_dims[0] if sorted_dims else "写作质量"
        if self._tried_dimensions and weakest_dim in self._tried_dimensions:
            # 尝试选择下一个未尝试过的弱维度
            for dim in sorted_dims:
                if dim not in self._tried_dimensions:
                    logging.info(f"  🎲 差异化策略: 跳过已尝试维度'{weakest_dim}', 切换到'{dim}'")
                    weakest_dim = dim
                    break
        self._tried_dimensions.append(weakest_dim)
        weakest_score = safe_get_score(weakest_dim)
        
        # 🆕 优先处理毒舌反馈 (Highest Priority)
        toxic_feedback = scores.get('毒舌反馈', '')
        if toxic_feedback:
            # 如果有毒舌反馈，直接覆盖最弱维度逻辑，因为这是S级门槛
            specific_instruction = (
                f"【🔥 S级紧急修正令】\n"
                f"毒舌读者已拒收本章！请立即针对以下批评进行整改（优先级最高）：\n"
                f"{toxic_feedback}\n\n"
                f"请无视其他次要问题，全力解决上述让读者'弃书'的毒点。如果说的是逻辑硬伤，必须修逻辑；如果说是水，必须删。"
            )
            weakest_dim = "读者体验(Critic)" # 虚拟维度
        else:
            # 正常逻辑：量化优化指令映射
            quantified_instructions = {
                "剧情连贯性": (
                    "1. **蒙太奇转场**：取消生硬的'然后'、'接着'。尝试用声音（如钟声、爆炸声）或视觉焦点（如飘落的叶子）作为场景切换的锚点。\n"
                    "2. **因果强关联**：主角的每一个行动必须是对前一个危机的直接反应。检查并强化'危机->决策->行动->新危机'的链条。\n"
                    "3. **悬念前置**：在段落开头就抛出异常点（如'但他没料到...'），抓住读者注意力后再解释原因。"
                ),
                "角色一致性": (
                    "1. **高光反派**：给反派增加一个'合理的动机'或'独特的坚持'，让他看起来不只是个靶子。让他在被击败前给主角造成实质性麻烦（肉体或精神）。\n"
                    "2. **女性弧光**：让女性角色展现出'非依附性'的一面。在危机中，让她发现一个主角没注意到的细节，或提供一个独特的视角。\n"
                    "3. **非对称对话**：通过对话长度和掌控权的争夺来体现地位差。尝试让强者用反问句，弱者用陈述句。"
                ),
                "写作质量": (
                    "1. **动态隐喻**：将静态比喻（'像...'）转化为动态动作（'撕裂了...'、'吞噬了...'）。参考 S 级范例中的'动作流'描写。\n"
                    "2. **感官特写**：选取一个极小的细节（如'指甲缝里的泥'、'剑刃的缺口'）进行显微镜式的特写，以此映射整体氛围。\n"
                    "3. **去形容词化**：尝试删掉 50% 的形容词，改用动词和名词来承载力量。例如将'愤怒的眼神'改为'眼眶崩裂流出血泪'。"
                ),
                "架构遵循度": "1. **命运回响**：在对话或独白中，隐晦地呼应全书的核心主题（如'代价'、'轮回'、'打破规则'）。\n2. **推进感**：确保本章不仅是'发生了什么'，而是'改变了什么'（人物关系改变、能力改变、局势改变）。",
                "设定遵循度": "1. **设定视觉化**：不要解说设定，要'演示'设定。不要说'他发动了火球术'，要写'空气中的燃素被强行聚合，每一个氧分子都在欢呼雀跃...'。\n2. **文明底色**：在环境描写中融入世界观的独特元素（如古代宗门建筑的'岁月斑驳'、秘境遗迹的'沧桑道韵'）。",
                "字数达标率": "1. **扩展博弈**：将一招制敌扩写为'试探->博弈->反转->绝杀'的过程。\n2. **心理时空**：在关键的一秒钟内，拉长主角的心理时间，描写他脑海中闪过的千万种计算和权衡。",
                "情感张力": (
                    "1. **绝境升维**：如果主角现在的处境是'困难'，请将其升级为'绝望'。堵死所有常规出路，逼迫他进行非常规操作。\n"
                    "2. **情绪过山车**：先给读者一个虚假的希望，然后无情打破它，最后在绝望中爆发真正的转机。\n"
                    "3. **无声爆发**：最深沉的愤怒不需要咆哮。尝试描写暴风雨前的宁静，用环境的压抑来衬托角色的爆发。"
                ),
                "系统机制": "1. **系统的压迫感/诱惑感**：系统不应只是工具，它应该有性格（冷漠、贪婪、狡极其）。描写系统提示音出现时的生理反应（耳鸣、剧痛、快感）。\n2. **非常规操作**：主角对系统的利用不应是照说明书操作，而是寻找规则漏洞、另辟蹊径（仅限主角内心独白中使用程序员术语）。"
            }
            
            specific_instruction = quantified_instructions.get(weakest_dim, "请针对该维度进行深度优化，拒绝表面功夫。")

        score_info = self._last_round_score_info or {}
        trigger_reasons = score_info.get("trigger_reasons", []) or ["score_below_threshold"]
        must_fix = []
        if weakest_dim and weakest_dim != "读者体验(Critic)":
            must_fix.append(f"{weakest_dim}必须提升到8.5以上")
        for dim_name, min_target in [("剧情连贯性", 8.0), ("角色一致性", 8.0), ("写作质量", 8.0), ("情感张力", 8.0)]:
            dim_score = safe_get_score(dim_name)
            if dim_score < min_target:
                must_fix.append(f"{dim_name}当前{dim_score:.1f}，需提升到{min_target}+")
        if not must_fix:
            must_fix.append("保持已达标维度不回退，并提升叙事张力")
        must_fix_text = "\n".join([f"- {item}" for item in must_fix[:6]])

        reason_text = ", ".join([str(r) for r in trigger_reasons]) if trigger_reasons else "score_below_threshold"
        critic_feedback_text = score_info.get("critic_feedback", "")
        raw_score_val = _safe_cast(score_info.get("raw_score", 0), float, 0.0)
        final_score_val = _safe_cast(score_info.get("final_score", 0), float, 0.0)
        threshold_val = _safe_cast(score_info.get("threshold", 0), float, 0.0)
        iter_val = _safe_cast(score_info.get("iteration", 0), int, 0) + 1
        score_card = f"""
### 整改指令卡（必须逐条落实）
- 章节: 第{chapter_num}章
- 当前轮次: Iter {iter_val}
- 分数: raw={raw_score_val:.2f}, final={final_score_val:.2f}, target={threshold_val:.2f}
- 触发原因: {reason_text}
{f"- Critic反馈: {critic_feedback_text}" if critic_feedback_text else ""}

#### Must Fix 清单
{must_fix_text}

#### 禁改项
- 不得改变章节核心事件结论
- 不得破坏角色既有人设
- 不得删除关键伏笔/系统机制
"""

        # 【黄金三章·特权指令】Ch 1-3 必须执行的最高优先级优化
        
        # 检查一致性问题 (Fix 1.1: 含二次验证中残留的矛盾)
        consistency_warning = ""
        unresolved = scores.get('_unresolved_conflicts', [])
        if unresolved:
            conflict_msgs = [f"- ⚠️【未修正】{c['message']}" for c in unresolved[:3]]
            consistency_warning = f"\n\n【🔴 一致性问题·二次验证未通过】以下矛盾在上一轮优化后仍然存在，本轮必须优先修正：\n" + "\n".join(conflict_msgs)
        elif self.consistency_checker:
            conflicts = self.consistency_checker.check_consistency(content, chapter_num)
            if conflicts:
                conflict_msgs = [f"- {c['message']}" for c in conflicts[:3]]
                consistency_warning = f"\n\n【一致性问题】发现以下矛盾，必须修正：\n" + "\n".join(conflict_msgs)
        
        # 🆕 敏感内容警告
        safety_warning = ""
        safety_issues = scores.get('_safety_issues', [])
        if safety_issues:
            safety_msgs = [f"- 🛡️ {issue}" for issue in safety_issues[:3]]
            safety_warning = f"\n\n【敏感内容警告】以下内容需要修改或软化：\n" + "\n".join(safety_msgs)
        
        # 🆕 信息密度警告
        density_warning = ""
        if self.density_checker:
            density_result = self.density_checker.analyze(content)
            if density_result.get('filler_ratio', 0) > 0.2:
                filler_segments = density_result.get('filler_segments', [])[:3]
                density_msgs = [f"- 📝 {seg}" for seg in filler_segments]
                density_warning = f"\n\n【注水检测】信息密度偏低({density_result.get('filler_ratio', 0):.0%}为填充内容)，请精简以下段落：\n" + "\n".join(density_msgs)
        
        # 🆕 角色声音一致性警告
        voice_warning = ""
        if self.voice_tracker:
            voice_issues = self.voice_tracker.check_voice_consistency(content, chapter_num)
            if voice_issues:
                voice_msgs = [f"- 🎙️ {issue}" for issue in voice_issues[:3]]
                voice_warning = f"\n\n【角色声音问题】以下角色的说话方式过于相似或偏离人设：\n" + "\n".join(voice_msgs)

        # 🆕 LLM 深度一致性审校警告
        llm_consistency_warning = ""
        llm_consistency_review = scores.get('_llm_consistency_review', '')
        if isinstance(llm_consistency_review, str) and llm_consistency_review.strip():
            lines = [line.strip() for line in llm_consistency_review.splitlines() if line.strip()]
            preview = "\n".join([f"- 🧠 {line}" for line in lines[:4]])
            llm_consistency_warning = (
                "\n\n【LLM深度一致性审校】模型发现以下潜在跨章冲突，请优先修复：\n"
                + preview
            )

        timeline_warning = ""
        timeline_conflicts = scores.get('_timeline_conflicts', [])
        if timeline_conflicts:
            timeline_msgs = [f"- 🕒 {c.get('message', '')}" for c in timeline_conflicts[:3]]
            timeline_warning = (
                "\n\n【时间线冲突】检测到时序问题，请修正章节时间锚点并保持单调前进：\n"
                + "\n".join(timeline_msgs)
            )

        logic_warning = ""
        logic_issues = scores.get('_logic_guard_issues', [])
        if logic_issues:
            logic_msgs = [f"- ⚖️ {msg}" for msg in logic_issues[:3]]
            logic_warning = (
                "\n\n【逻辑硬规则】以下问题不修复将持续触发拒收：\n"
                + "\n".join(logic_msgs)
            )
        
        # 🆕 悬念提醒（来自 hook_tracker）
        hook_reminder = ""
        if self.hook_tracker:
            try:
                hook_reminder = self.hook_tracker.generate_reminder_prompt(chapter_num)
            except Exception as e:
                logging.debug(f"悬念提醒生成异常: {e}")
        
        # 🆕 叙事线程平衡提醒（来自 thread_tracker）
        thread_reminder = ""
        if self.thread_tracker:
            try:
                thread_reminder = self.thread_tracker.generate_balance_prompt(chapter_num)
            except Exception as e:
                logging.debug(f"叙事线程提醒生成异常: {e}")
        
        # 🆕 叙事模式重复警告（来自本轮评分中的检测结果）
        pattern_warning = ""
        pattern_issues = scores.get('_pattern_issues', [])
        if pattern_issues:
            pattern_msgs = [f"- 🔄 {pi}" for pi in pattern_issues[:2]]
            pattern_warning = f"\n\n【叙事模式重复警告】本章叙事结构与近期章节过于相似：\n" + "\n".join(pattern_msgs)
        
        # 获取评分返回的具体问题描述和建议
        problem_desc = scores.get("问题描述", "")
        fix_suggestion = scores.get("修改建议", "")
        
        problem_section = ""
        if problem_desc or fix_suggestion:
            problem_section = f"""
### Detect Problems
{problem_desc if problem_desc else "None"}

### Upgrade Suggestions
{fix_suggestion if fix_suggestion else "None"}
"""
        
        # 题材维度改进建议
        genre_hints_section = ""
        genre_hints = scores.get("题材改进建议", [])
        if genre_hints:
            hints_text = "\n".join(f"- {hint}" for hint in genre_hints)
            genre_hints_section = f"""

### Genre Enhancements (Genre: {scores.get('检测题材', 'Unknown')})
{hints_text}
"""
        
        prompt = f"""你是一位资深小说编辑。请对本章进行【精准优化诊断】。

### 最弱维度
{weakest_dim}（当前{weakest_score}分，目标8+分）

### 具体优化指令
{specific_instruction}
{score_card}
{problem_section}
{consistency_warning}
{llm_consistency_warning}
{timeline_warning}
{logic_warning}
{safety_warning}
{density_warning}
{voice_warning}
{hook_reminder}
{thread_reminder}
{pattern_warning}
{genre_hints_section}

### 章节片段
{content[:1000]}...

### 输出要求
请提供具体的修改建议，包括：
1. 在哪里添加什么内容
2. 哪些对话或描写需要修改
3. 避免模糊笼统的建议，必须具体到段落和句子

请开始诊断："""
        result = self.llm_adapter.invoke(prompt)
        return clean_llm_output(result)

    def _extract_revised_text(self, response: str) -> str:
        """从结构化回包中提取 revised_text；失败时回退清洗文本。"""
        cleaned = clean_llm_output(response)
        if not cleaned:
            return cleaned

        extracted = extract_revised_text_payload(response)
        if isinstance(extracted, str) and len(extracted.strip()) > 100:
            return clean_llm_output(extracted).strip()

        extracted_from_cleaned = extract_revised_text_payload(cleaned)
        if isinstance(extracted_from_cleaned, str) and len(extracted_from_cleaned.strip()) > 100:
            return clean_llm_output(extracted_from_cleaned).strip()

        candidates = []
        if '{' in cleaned and '}' in cleaned:
            candidates.append(cleaned[cleaned.find('{'):cleaned.rfind('}') + 1])
        fence_pattern = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.IGNORECASE)
        for block in fence_pattern.findall(cleaned):
            block = block.strip()
            if '{' in block and '}' in block:
                candidates.append(block[block.find('{'):block.rfind('}') + 1])

        for candidate in candidates:
            try:
                obj = json.loads(candidate)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict):
                revised = obj.get("revised_text")
                if isinstance(revised, str) and len(revised.strip()) > 100:
                    return revised.strip()

        for marker in ["### 最终章节正文", "### Final Chapter Content"]:
            if marker in cleaned:
                return cleaned.split(marker, 1)[1].strip()
        return cleaned

    def _rewrite_chapter(self, content: str, plan: str, min_limit: int, target: int, max_limit: int) -> str:
        """调用LLM根据优化方案重写章节"""
        
        current_len = count_chapter_words(content)['chinese_chars']
        # Dynamic word count target
        if current_len > max_limit:
            target_instruction = f"当前{current_len}字超出上限，请在优化的同时压缩到{target}字左右。"
        elif current_len < min_limit:
            target_instruction = f"当前{current_len}字偏短，建议适当扩充到{target}字左右。"
        else:
            target_instruction = f"当前{current_len}字合适，请控制在{min_limit}~{max_limit}字范围内。"
        
        prompt = (
            "你是一位金牌网文作家。请根据编辑反馈对本章进行【精准修改】。\n\n"
            "### 原章节\n"
            f"{content}\n\n"
            "### 修改反馈\n"
            f"{plan}\n\n"
            f"{POSITIVE_QUALITY_STANDARDS}\n\n"  # 🆕 注入正面质量标准
            f"{LITERARY_STYLE_GUIDE}\n\n"        # 🆕 注入 S 级文笔范例
            f"{SUBTEXT_GUIDE}\n\n"                # 🆕 注入潜台词指南
            f"{TWO_TRACK_NARRATIVE_RULE}\n\n"     # 🆕 注入双轨叙事规则
            f"{CULTURAL_DEPTH_GUIDE}\n\n"         # 🆕 注入文化深度指南
            "### 修改要求（升维模式）\n"
            "1. **严格保留原有剧情**：剧情走向必须一致，但表现手法要大幅升级。\n"
            "2. **展示而非讲述**：参考【文笔风格·动态范例】，彻底重写那些干瘪的叙述句。\n"
            f"3. **字数控制**：{target_instruction}\n"
            "4. **潜台词植入**：参考【潜台词指南】，确保每一句对话都有弦外之音。\n"
            "5. **输出格式**：必须返回 JSON 对象，字段为 revised_text/change_log/self_check。\n"
            "6. **🚨必须做出实质性/风格化修改**：不仅是改病句，而是要提升整章的文学质感！\n\n"
            "### 分步执行（High-Light Design）\n"
            "在输出最终文本前，请先设计本章的 3 个高光时刻：\n"
            "1. **视觉奇观点**（Visual Highlight）：设计一个极具冲击力的画面。\n"
            "2. **情感爆发点**（Emotional Highlight）：设计一个触动人心的瞬间。\n"
            "3. **逻辑反转点**（Logical Highlight）：设计一个意料之外情理之中的转折。\n\n"
            "请按以下JSON格式输出（不要额外解释）：\n"
            "{\n"
            "  \"change_log\": [\"改动1\", \"改动2\", \"改动3\"],\n"
            "  \"self_check\": [\n"
            "    \"must_fix#1是否解决：是/否 + 证据\",\n"
            "    \"must_fix#2是否解决：是/否 + 证据\"\n"
            "  ],\n"
            "  \"revised_text\": \"完整章节正文\"\n"
            "}\n\n"
            "请开始升维重写："
        )

        result = self.llm_adapter.invoke(prompt)
        
        # 🆕 记录LLM对话
        self._log_llm_conversation(self._current_chapter, self._current_iteration, "rewrite", prompt, result)
        
        return self._extract_revised_text(result)

    def _targeted_optimize(self, content: str, plan: str, weak_dimensions: list) -> str:
        """
        Targeted optimization for specific weak dimensions.
        :param content: Original content
        :param plan: Optimization plan
        :param weak_dimensions: List of weak dimensions
        :return: Optimized content
        """
        dims_text = "、".join(weak_dimensions) if weak_dimensions else "整体质量"
        
        prompt = f"""你是一位金牌小说编辑。请对本章进行【针对性局部优化】。

### 优化目标
专注提升以下维度：{dims_text}

### 修改反馈
{plan}

{POSITIVE_QUALITY_STANDARDS}

{LITERARY_STYLE_GUIDE}

{TWO_TRACK_NARRATIVE_RULE}

{CULTURAL_DEPTH_GUIDE}

### 原章节
{content}

### 优化要求
1. **外科手术式精准**：只修改特定薄弱区域，不要重写整章。
2. **无缝融入**：新增内容必须达到 S 级文笔标准，与 S 级范例对齐。
3. **展示而非讲述**：参考【文笔风格·动态范例】，强化感官细节。
4. **保持上下文**：不得改变剧情走向或角色性格。
5. **输出格式**：必须返回 JSON 对象，字段为 revised_text/change_log/self_check。
6. **🚨必须做出实质性修改**：禁止返回与原文相同的内容！你必须至少修改3处以上的句子或段落。

请按以下JSON格式输出（不要额外解释）：
{{
  "change_log": ["改动1", "改动2", "改动3"],
  "self_check": [
    "must_fix#1是否解决：是/否 + 证据",
    "must_fix#2是否解决：是/否 + 证据"
  ],
  "revised_text": "完整章节正文"
}}

请开始局部优化："""
        result = self.llm_adapter.invoke(prompt)
        
        # 🆕 记录LLM对话
        self._log_llm_conversation(self._current_chapter, self._current_iteration, "targeted_optimize", prompt, result)
        
        return self._extract_revised_text(result)

    def _polish_content(self, content: str) -> str:
        """
        Full text polishing to ensure consistency.
        :param content: Content to polish
        :return: Polished content
        """
        prompt = f"""你是一位金牌小说编辑。请对本章进行【终润定稿】。

### 润色目标
将文本提升至**出版级**水准。

### 原章节
{content}

{TWO_TRACK_NARRATIVE_RULE}

### 润色要求
1. **增强流畅度**：消除生硬表达，确保段落之间过渡自然。
2. **感官沉浸**：用生动的感官细节（视觉、听觉、触觉）增强描写。
3. **情感共鸣**：强化对话和内心独白的情感冲击力。
4. **一致性检查**：修正语气或格式上的细微不一致。
5. **保守编辑**：润色语言但**绝不改变剧情**。"""
        result = self.llm_adapter.invoke(prompt)
        return clean_llm_output(result)

    def _compress_content(self, content: str, chapter_num: int, target_length: int = TARGET_WORD_COUNT_AFTER_COMPRESS, progress_callback=None) -> str:
        """
        Compress content while maintaining quality.
        :param content: Original content
        :param chapter_num: Chapter number
        :param target_length: Target word count
        :param progress_callback: UI Callback
        :return: Compressed content
        """
        current_length = count_chapter_words(content)['chinese_chars']
        
        prompt = f"""你是一位金牌网文编辑。请对本章进行【高质量精简】。

### 压缩目标
- 当前字数：{current_length}字
- 目标字数：约{target_length}字
- 压缩比例：约{int(target_length/current_length*100)}%

### 核心要求：「更精炼，而非仅仅更短」
用户要求分数不能下降。为此你必须**提高信息密度**：
1. **合并而非删除**：将3句松散的话合并成1句有力的复合句。
2. **强化表达**：用更强烈的动词替代副词，让描写更短但更生动。
3. **节奏控制**：加快过渡节奏，但对高潮部分保持（甚至扩展）篇幅。

⚠️ **强制压缩指令**：
当前字数严重超标！必须删减至少30%的冗余描写（如过长的环境渲染、重复的心理活动）。
请保留核心骨架，像修剪盆景一样剪去多余枝叶。


### 原则
1. **保留核心剧情**：主线故事、关键对话、冲突场景、系统提示必须保留完整。
2. **保留精彩亮点**：生动的比喻、感官描写、角色表情必须保留。
3. **消除冗余**：删除"他想到..."、"他感到..."等过滤性表达。
4. **删除水分**：删除重复的内心独白或不必要的过渡。

### 严禁
- 不得删除对话场景
- 不得删除打斗/冲突场景
- 不得删除系统提示/面板
- 不得将场景概括为干巴巴的报告

### 原文内容
{content}

### 输出要求
直接输出压缩后的完整章节正文，不要任何前缀后缀。
        
请开始高质量精简："""

        try:
            compressed = self.llm_adapter.invoke(prompt)
            compressed = clean_llm_output(compressed)
            if compressed and len(compressed) > 500:  # 确保返回有效内容
                logging.info(f"[Compress] 第{chapter_num}章压缩完成: {current_length}字 -> {len(compressed)}字")
                if progress_callback: progress_callback(f"✅ Compressed: {current_length}->{len(compressed)}", 1.0)
                return compressed
            else:
                logging.warning(f"[Compress] 第{chapter_num}章压缩返回内容过短或无效")
                if progress_callback: progress_callback(f"⚠️ Compression Failed", 1.0)
                return None
        except Exception as e:
            logging.error(f"[Compress] 第{chapter_num}章压缩出错: {e}")
            return None

    def _expand_content(self, content: str, chapter_num: int, target_length: int = TARGET_WORD_COUNT_AFTER_EXPAND, progress_callback=None) -> str:
        """
        Expand content that is too short.
        :param content: Original content
        :param chapter_num: Chapter number
        :param target_length: Target word count
        :param progress_callback: UI Callback
        :return: Expanded content
        """
        current_length = count_chapter_words(content)['chinese_chars']
        
        prompt = f"""你是一位金牌网文作家。请对本章进行【高质量扩写】。

### 扩写目标
- 当前字数：{current_length}字
- 目标字数：约{target_length}字
- 需补充：约{target_length - current_length}字

### 扩写原则
1. **保留剧情**：不得改变主线故事或人物关系。
2. **增强感官细节**：扩展环境描写（视觉、听觉、嗅觉）、质感和氛围。
3. **深化人物**：增加微表情、肢体语言和内心独白。
4. **强化冲突**：扩展对话交锋和紧张感。
5. **文学手法**：使用比喻和拟人来丰富文笔。

### 重点扩展位置
- 环境氛围（沉浸式细节）
- 角色微表情和动作
- 内心独白和情绪变化
- 对话（推动剧情）

### 原文内容
{content}

### 输出要求
直接输出扩写后的完整章节正文，不要任何前缀后缀。

请开始扩写："""

        try:
            expanded = self.llm_adapter.invoke(prompt)
            expanded = clean_llm_output(expanded)
            if expanded and len(expanded) > current_length:
                logging.info(f"[Expand] 第{chapter_num}章扩写完成: {current_length}字 -> {len(expanded)}字")
                if progress_callback: progress_callback(f"✅ Expanded: {current_length}->{len(expanded)}", 1.0)
                return expanded
            else:
                logging.warning(f"[Expand] 第{chapter_num}章扩写返回内容未达预期或无效")
                if progress_callback: progress_callback(f"⚠️ Expansion Failed", 1.0)
                return None
        except Exception as e:
            logging.error(f"[Expand] 第{chapter_num}章扩写出错: {e}")
            return None
