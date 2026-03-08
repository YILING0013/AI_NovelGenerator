# novel_generator/chapter.py
# -*- coding: utf-8 -*-
"""
章节草稿生成及获取历史章节文本、当前章节摘要等
"""
import os
import json
import logging
import re  # 添加re模块导入
import datetime
import time
from typing import Any
from llm_adapters import create_llm_adapter
from novel_generator.state_manager import WorldStateManager # New Import
from novel_generator.timeline_manager import TimelineManager
from prompt_definitions import (
    first_chapter_draft_prompt,
    next_chapter_draft_prompt,
    summarize_recent_chapters_prompt,
    knowledge_filter_prompt,
    knowledge_search_prompt,
    ENDING_STYLES,
    # 新增：网文智能创作引擎核心配置
    BATTLE_STYLE_POOL,
    get_cultivation_constraint,
    VILLAIN_DIALOGUE_STYLES
)











from chapter_directory_parser import (
    load_chapter_info,
    get_chapter_info_from_blueprint as _legacy_get_chapter_info_from_blueprint,
)
from novel_generator.common import invoke_with_cleaning
from utils import read_file, clear_file_content, save_string_to_txt, resolve_architecture_file
from novel_generator.vectorstore_utils import (
    get_relevant_context_from_vector_store,
    load_vector_store  # 添加导入
)
from novel_generator.wordcount_utils import count_chapter_words
from novel_generator.pacing_agent import PacingAgent  # 🆕 导入节奏大师
from novel_generator.architecture_reader import ArchitectureReader
from novel_generator.architecture_runtime_slice import (
    build_runtime_architecture_view,
    build_runtime_architecture_context,
    contains_archive_sections,
    build_runtime_guardrail_brief,
)
from novel_generator.chapter_contract_guard import (
    build_chapter_contract,
    build_chapter_contract_prompt,
)
from novel_generator.generation_state_facade import GenerationStateFacade

RUNTIME_GUARDRAIL_MARKER = "【运行时硬约束摘要】"

# 兼容旧测试/旧调用：保留原函数名导出。
get_chapter_info_from_blueprint = _legacy_get_chapter_info_from_blueprint







logging.basicConfig(
    filename='app.log',      # 日志文件名
    filemode='a',            # 追加模式（'w' 会覆盖）
    level=logging.INFO,      # 记录 INFO 及以上级别的日志
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

_INVALID_LOCKED_VALUES = {
    "（未指定）",
    "未指定",
    "unknown",
    "Unknown",
    "null",
    "NULL",
    "None",
    "N/A",
    "主角",
    "主人公",
    "Protagonist",
}


def _sanitize_locked_field(value: str, fallback: str = "（未指定）", field_name: str = "字段") -> str:
    candidate = str(value or "").strip()
    candidate = re.sub(r'^[\"“”\'‘’]+|[\"“”\'‘’]+$', '', candidate)
    candidate = re.sub(r'[，,。；;、]+$', '', candidate).strip()
    if not candidate:
        return fallback
    if candidate in _INVALID_LOCKED_VALUES:
        return fallback
    if re.fullmatch(r'\d+(?:\.\d+)?', candidate):
        logging.warning(f"检测到非法{field_name}占位值: {candidate}，已回退为{fallback}")
        return fallback
    return candidate


def _normalize_protagonist_name(raw_value: str) -> str:
    candidate = str(raw_value or "").strip()
    candidate = re.sub(r'^[\-—*•\d\.\s]+', '', candidate)
    candidate = re.sub(r'[（(].*$', '', candidate).strip()
    candidate = re.split(r'[，,。；;、\s]', candidate, maxsplit=1)[0].strip()
    token_match = re.match(r'([A-Za-z\u4e00-\u9fff·]{2,12})', candidate)
    if token_match:
        candidate = token_match.group(1)
    return _sanitize_locked_field(candidate, fallback="（未指定）", field_name="主角姓名")


def _extract_first_valid_match(content: str, patterns: list[str], normalizer) -> str:
    for pattern in patterns:
        match = re.search(pattern, content, re.MULTILINE)
        if not match:
            continue
        candidate = normalizer(match.group(1))
        if candidate != "（未指定）":
            return candidate
    return "（未指定）"

def _log_generation_to_file(filepath: str, novel_number: int, stage: str, prompt: str, response: str):
    """
    记录生成过程中的LLM对话日志 (Universal Logger)
    """
    try:
        log_dir = os.path.join(filepath, "llm_logs", f"chapter_{novel_number}")
        os.makedirs(log_dir, exist_ok=True)
        
        timestamp = datetime.datetime.now().strftime("%H%M%S")
        # stage name can be 'draft', 'continuation', 'optimization'
        log_file = os.path.join(log_dir, f"gen_{stage}_{timestamp}.md")
        
        with open(log_file, 'w', encoding='utf-8') as f:
            f.write(f"# Chapter {novel_number} - Generation Log - {stage}\n\n")
            f.write(f"**Time**: {datetime.datetime.now().isoformat()}\n\n")
            f.write("## Prompt\n\n```\n")
            f.write(prompt[:8000] + ("..." if len(prompt) > 8000 else "")) 
            f.write("\n```\n\n")
            f.write("## Response\n\n```\n")
            f.write(response[:8000] + ("..." if len(response) > 8000 else ""))
            f.write("\n```\n")
    except Exception as e:
        logging.warning(f"Failed to log generation conversation: {e}")


def _append_guidance_block(base_guidance: str, extra_guidance: str) -> str:
    base_text = str(base_guidance or "").strip()
    extra_text = str(extra_guidance or "").strip()
    if not extra_text:
        return base_text
    if not base_text:
        return extra_text
    return f"{base_text}\n\n{extra_text}"


def _load_runtime_state_snapshot(
    filepath: str,
    chapter_info: dict[str, Any],
    protagonist_name: str,
) -> str:
    try:
        state_manager = WorldStateManager(filepath)
        if not os.path.exists(state_manager.state_path):
            fallback_name = protagonist_name or str(chapter_info.get("characters_involved", "")).split("、")[0].strip() or "Protagonist"
            state_manager.initialize_state("", fallback_name)
        return state_manager.get_state_snapshot().strip()
    except Exception as e:
        logging.debug(f"Runtime state snapshot unavailable: {e}")
        return ""


def _build_runtime_continuity_guidance(
    *,
    memory_guidance: str = "",
    global_summary_text: str = "",
    character_state_text: str = "",
    short_summary: str = "",
    previous_excerpt: str = "",
    filtered_context: str = "",
    next_chapter_summary: str = "",
    hook_summary_text: str = "",
    thread_summary_text: str = "",
    state_snapshot: str = "",
) -> str:
    sections: list[str] = []

    if memory_guidance.strip():
        sections.append(memory_guidance.strip())
    if global_summary_text.strip():
        sections.append(f"【最新全局摘要】\n{global_summary_text.strip()}")
    if character_state_text.strip():
        sections.append(f"【最新角色状态】\n{character_state_text.strip()}")
    if short_summary.strip() and short_summary.strip() != "（摘要生成失败）":
        sections.append(f"【近三章摘要】\n{short_summary.strip()}")
    if previous_excerpt.strip():
        sections.append(f"【前章结尾片段（用于强衔接，禁止剧情回滚）】\n{previous_excerpt.strip()}")
    if filtered_context.strip() and filtered_context.strip() != "（知识库处理失败）":
        sections.append(f"【检索知识（仅采纳与本章直接相关的信息）】\n{filtered_context.strip()}")
    if hook_summary_text.strip():
        sections.append(f"【伏笔回收提醒】\n{hook_summary_text.strip()}")
    if thread_summary_text.strip():
        sections.append(f"【叙事线程提醒】\n{thread_summary_text.strip()}")
    if next_chapter_summary.strip():
        sections.append(f"【下一章衔接锚点】\n{next_chapter_summary.strip()}")
    if state_snapshot.strip():
        sections.append(state_snapshot.strip())

    if not sections:
        return ""

    return "【运行时连续性上下文】\n" + "\n\n".join(sections)

def extract_protagonist_info(filepath: str) -> dict[str, str]:
    """
    从架构文件中提取主角核心信息用于身份锁定
    返回: {
        'protagonist_name': str,
        'system_name': str,
        'core_abilities': str,
        'protagonist_identity': str
    }
    """
    try:
        architecture_path = resolve_architecture_file(filepath)
        if not os.path.exists(architecture_path):
            logging.warning(f"小说架构文件不存在: {architecture_path}")
            return {
                'protagonist_name': '（未指定）',
                'system_name': '（未指定）',
                'core_abilities': '（未指定）',
                'protagonist_identity': '（未指定）'
            }
        
        content = read_file(architecture_path)
        
        # 提取主角名称（优先识别显式实名，避免误命中编号“1”）
        protagonist_name = _extract_first_valid_match(
            content,
            patterns=[
                r'(?m)^\s*主角实名[：:]\s*([^\n]+)',
                r'(?m)^\s*主角(?:姓名|名字)?[：:]\s*([^\n]+)',
                r'(?m)^\s*###\s*角色一[：:]\s*([^\n]+)',
                r'(?m)^\s*角色一[：:]\s*([^\n]+)',
                r'核心种子[^。\n]{0,30}?([^\s（(，。,；;、：:\d]{2,8})意外穿越',
                r'程序员([^\s（(，。,；;、：:\d]{2,8})意外穿越',
            ],
            normalizer=_normalize_protagonist_name,
        )

        # 提取系统名称
        system_name = _extract_first_valid_match(
            content,
            patterns=[
                r'(?m)^\s*###?\s*([A-Za-z\u4e00-\u9fff·]{2,20}系统)(?:[（(].*)?$',
                r'(?m)^\s*金手指(?:系统)?[：:]\s*([^\n，。；;]+)',
                r'(?m)^\s*系统(?:名称)?[：:]\s*([^\n，。；;]+)',
                r'系统流金手指[^\-]*[-—]\s*([^（\(]+)',
                r'激活.*?["""]([^"""]+系统)["""]',
                r'金手指.*?["""]([^"""]+系统)["""]',
            ],
            normalizer=lambda value: _sanitize_locked_field(value, fallback="（未指定）", field_name="系统名称"),
        )
        if system_name == "（未指定）":
            if "天书系统" in content:
                system_name = "天书系统"
            elif "残缺天书" in content or "天书" in content:
                system_name = "天书（残页）"

        # 提取核心能力
        core_abilities = "（未指定）"
        if "看见命运缝线" in content:
            core_abilities = "看见命运缝线（改命需付代价）"
        else:
            ability_patterns = [
                r'(?m)^\s*核心能力[：:]\s*([^\n]+)',
                r'系统流金手指.*?（([^）]+)）',
            ]
            core_abilities = _extract_first_valid_match(
                content,
                patterns=ability_patterns,
                normalizer=lambda value: _sanitize_locked_field(value, fallback="（未指定）", field_name="核心能力"),
            )

        # 提取主角身份
        protagonist_identity = "（未指定）"
        identity_patterns = [
            r'(?m)^\s*主角身份[：:]\s*([^\n]+)',
            r'\*\*背景：\*\*\s*([^\n]+)',
            r'背景：\s*([^\n]+)',
        ]
        protagonist_identity = _extract_first_valid_match(
            content,
            patterns=identity_patterns,
            normalizer=lambda value: _sanitize_locked_field(value, fallback="（未指定）", field_name="主角身份"),
        )
        if protagonist_identity == "（未指定）":
            story_identity_match = re.search(r'一句话故事：\s*\n?\s*主角([^，。\n]{2,32})', content)
            if story_identity_match:
                protagonist_identity = _sanitize_locked_field(
                    story_identity_match.group(1),
                    fallback="（未指定）",
                    field_name="主角身份",
                )

        logging.info(f"提取主角信息成功: {protagonist_name}, {system_name}")
        return {
            'protagonist_name': protagonist_name,
            'system_name': system_name,
            'core_abilities': core_abilities,
            'protagonist_identity': protagonist_identity
        }
    except Exception as e:
        logging.error(f"提取主角信息失败: {e}")
        return {
            'protagonist_name': '（未指定）',
            'system_name': '（未指定）',
            'core_abilities': '（未指定）',
            'protagonist_identity': '（未指定）'
        }


def _build_runtime_guardrail_prefix(filepath: str) -> str:
    architecture_path = resolve_architecture_file(filepath, prefer_active=False)
    if not os.path.exists(architecture_path):
        return ""
    full_architecture_text = read_file(architecture_path)
    runtime_architecture_text = build_runtime_architecture_view(full_architecture_text)
    if not runtime_architecture_text:
        return ""
    if contains_archive_sections(runtime_architecture_text):
        raise RuntimeError("运行时架构视图包含归档节（13-87），已阻断生成")
    return build_runtime_guardrail_brief(full_architecture_text)


def fix_chapter_title(content: str) -> str:
    """
    修复章节标题重复问题，如"第10章 第10章"修复为"第10章"
    """
    # 匹配"第X章 第X章"模式并替换为"第X章"
    pattern = r'(第\d+章)\s+第\d+章'
    fixed_content = re.sub(pattern, r'\1', content)
    
    if fixed_content != content:
        logging.info("已修复章节标题重复问题")
    
    return fixed_content


def extract_chapter_openings(
    chapters_dir: str,
    current_chapter_num: int,
    max_scan: int = 20,
) -> list[tuple[int, str]]:
    """
    🔧 Fix 3.6: 提取最近N章的开头首字/首词，用于防止开头模式化。
    返回: [(章号, 首字)] 列表，如 [(1, '夜'), (2, '清'), ...]
    """
    openings: list[tuple[int, str]] = []
    start = max(1, current_chapter_num - max_scan)
    for c in range(start, current_chapter_num):
        chap_file = os.path.join(chapters_dir, f"chapter_{c}.txt")
        if not os.path.exists(chap_file):
            continue
        try:
            text = read_file(chap_file).strip()
            if not text:
                continue
            # 跳过标题行（"第X章 XXX"）
            lines = text.split('\n')
            content_start = 0
            for i, line in enumerate(lines):
                stripped = line.strip()
                if stripped and not re.match(r'^第\d+章', stripped):
                    content_start = i
                    break
            # 提取首个非空内容行的第一个字符
            if content_start < len(lines):
                first_line = lines[content_start].strip()
                if first_line:
                    # 取首字（汉字）
                    first_char = first_line[0]
                    openings.append((c, first_char))
        except Exception:
            continue
    return openings

def get_last_n_chapters_text(chapters_dir: str, current_chapter_num: int, n: int = 3) -> list[str]:
    """
    从目录 chapters_dir 中获取最近 n 章的文本内容，返回文本列表。
    """
    texts: list[str] = []
    start_chap = max(1, current_chapter_num - n)
    for c in range(start_chap, current_chapter_num):
        chap_file = os.path.join(chapters_dir, f"chapter_{c}.txt")
        if os.path.exists(chap_file):
            text = read_file(chap_file).strip()
            texts.append(text)
        else:
            texts.append("")
    return texts

def summarize_recent_chapters(
    interface_format: str,
    api_key: str,
    base_url: str,
    model_name: str,
    temperature: float,
    max_tokens: int,
    chapters_text_list: list[str],
    novel_number: int,            # 新增参数
    chapter_info: dict[str, Any],           # 新增参数
    next_chapter_info: dict[str, Any],      # 新增参数
    timeout: int = 600
) -> str:  # 修改返回值类型为 str，不再是 tuple
    """
    根据前三章内容生成当前章节的精准摘要。
    如果解析失败，则返回空字符串。
    """
    try:
        combined_text = "\n".join(chapters_text_list).strip()
        if not combined_text:
            return ""
            
        # 限制组合文本长度
        max_combined_length = 4000
        if len(combined_text) > max_combined_length:
            combined_text = combined_text[-max_combined_length:]
            
        llm_adapter = create_llm_adapter(
            interface_format=interface_format,
            base_url=base_url,
            model_name=model_name,
            api_key=api_key,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout
        )
        
        # 确保所有参数都有默认值
        chapter_info = chapter_info or {}
        next_chapter_info = next_chapter_info or {}
        
        prompt = summarize_recent_chapters_prompt.format(
            combined_text=combined_text,
            novel_number=novel_number,
            chapter_title=chapter_info.get("chapter_title", "未命名"),
            chapter_role=chapter_info.get("chapter_role", "常规章节"),
            chapter_purpose=chapter_info.get("chapter_purpose", "内容推进"),
            suspense_level=chapter_info.get("suspense_level", "中等"),
            foreshadowing=chapter_info.get("foreshadowing", "无"),
            plot_twist_level=chapter_info.get("plot_twist_level", "★☆☆☆☆"),
            chapter_summary=chapter_info.get("chapter_summary", ""),
            next_chapter_number=novel_number + 1,
            next_chapter_title=next_chapter_info.get("chapter_title", "（未命名）"),
            next_chapter_role=next_chapter_info.get("chapter_role", "过渡章节"),
            next_chapter_purpose=next_chapter_info.get("chapter_purpose", "承上启下"),
            next_chapter_summary=next_chapter_info.get("chapter_summary", "衔接过渡内容"),
            next_chapter_suspense_level=next_chapter_info.get("suspense_level", "中等"),
            next_chapter_foreshadowing=next_chapter_info.get("foreshadowing", "无特殊伏笔"),
            next_chapter_plot_twist_level=next_chapter_info.get("plot_twist_level", "★☆☆☆☆")
        )
        
        response_text = invoke_with_cleaning(llm_adapter, prompt)
        summary = extract_summary_from_response(response_text)
        
        if not summary:
            logging.warning("Failed to extract summary, using full response")
            return response_text[:2000]  # 限制长度
            
        return summary[:2000]  # 限制摘要长度
        
    except Exception as e:
        logging.error(f"Error in summarize_recent_chapters: {str(e)}")
        return ""

def extract_summary_from_response(response_text: str) -> str:
    """从响应文本中提取摘要部分"""
    if not response_text:
        return ""
        
    # 查找摘要标记
    summary_markers = [
        "当前章节摘要:", 
        "章节摘要:",
        "摘要:",
        "本章摘要:"
    ]
    
    for marker in summary_markers:
        if (marker in response_text):
            parts = response_text.split(marker, 1)
            if len(parts) > 1:
                return parts[1].strip()
    
    return response_text.strip()

def format_chapter_info(chapter_info: dict[str, Any]) -> str:
    """将章节信息字典格式化为文本"""
    template = """
章节编号：第{number}章
章节标题：《{title}》
章节定位：{role}
核心作用：{purpose}
主要人物：{characters}
关键道具：{items}
场景地点：{location}
伏笔设计：{foreshadow}
悬念密度：{suspense}
转折程度：{twist}
章节简述：{summary}
"""
    return template.format(
        number=chapter_info.get('chapter_number', '未知'),
        title=chapter_info.get('chapter_title', '未知'),
        role=chapter_info.get('chapter_role', '未知'),
        purpose=chapter_info.get('chapter_purpose', '未知'),
        characters=chapter_info.get('characters_involved', '未指定'),
        items=chapter_info.get('key_items', '未指定'),
        location=chapter_info.get('scene_location', '未指定'),
        foreshadow=chapter_info.get('foreshadowing', '无'),
        suspense=chapter_info.get('suspense_level', '一般'),
        twist=chapter_info.get('plot_twist_level', '★☆☆☆☆'),
        summary=chapter_info.get('chapter_summary', '未提供')
    )

def parse_search_keywords(response_text: str) -> list[str]:
    """解析关键词列表，兼容多种分隔格式。"""
    if not response_text:
        return []

    parsed: list[str] = []
    for raw_line in response_text.strip().split('\n'):
        line = raw_line.strip()
        if not line:
            continue

        # 首选新版“·”分隔，其次兼容常见分隔符。
        if '·' in line:
            normalized = line.replace('·', ' ')
        elif any(sep in line for sep in ('，', ',', '、', ';', '；')):
            normalized = re.sub(r'[，,、;；]+', ' ', line)
        else:
            normalized = line

        normalized = re.sub(r'\s+', ' ', normalized).strip(" -:：")
        if normalized:
            parsed.append(normalized)

    return parsed[:5]  # 最多取5组

def apply_content_rules(texts: list[str], novel_number: int) -> list[str]:
    """应用内容处理规则"""
    processed: list[str] = []
    for text in texts:
        if re.search(r'第[\d]+章', text) or re.search(r'chapter_[\d]+', text):
            chap_nums = list(map(int, re.findall(r'\d+', text)))
            recent_chap = max(chap_nums) if chap_nums else 0
            time_distance = novel_number - recent_chap
            
            if time_distance <= 2:
                processed.append(f"[SKIP] 跳过近章内容：{text[:120]}...")
            elif 3 <= time_distance <= 5:
                processed.append(f"[MOD40%] {text}（需修改≥40%）")
            else:
                processed.append(f"[OK] {text}（可引用核心）")
        else:
            processed.append(f"[PRIOR] {text}（优先使用）")
    return processed

def apply_knowledge_rules(contexts: list[str], chapter_num: int) -> list[str]:
    """应用知识库使用规则"""
    processed: list[str] = []
    for text in contexts:
        # 检测历史章节内容
        if "第" in text and "章" in text:
            # 提取章节号判断时间远近
            chap_nums = [int(x) for x in re.findall(r'第\s*(\d+)\s*章', text)]
            recent_chap = max(chap_nums) if chap_nums else 0
            time_distance = chapter_num - recent_chap
            
            # 相似度处理规则
            if time_distance <= 3:  # 近三章内容
                processed.append(f"[历史章节限制] 跳过近期内容: {text[:50]}...")
                continue
                
            # 允许引用但需要转换
            processed.append(f"[历史参考] {text} (需进行30%以上改写)")
        else:
            # 第三方知识优先处理
            processed.append(f"[外部知识] {text}")
    return processed

def get_filtered_knowledge_context(
    api_key: str,
    base_url: str,
    model_name: str,
    interface_format: str,
    embedding_adapter,
    filepath: str,
    chapter_info: dict[str, Any],
    retrieved_texts: list[str],
    max_tokens: int = 2048,
    timeout: int = 600
) -> str:
    """优化后的知识过滤处理"""
    if not retrieved_texts:
        return "（无相关知识库内容）"

    try:
        processed_texts = apply_knowledge_rules(retrieved_texts, chapter_info.get('chapter_number', 0))
        llm_adapter = create_llm_adapter(
            interface_format=interface_format,
            base_url=base_url,
            model_name=model_name,
            api_key=api_key,
            temperature=0.3,
            max_tokens=max_tokens,
            timeout=timeout
        )
        
        # 限制检索文本长度并格式化
        formatted_texts = []
        max_text_length = 600
        for i, text in enumerate(processed_texts, 1):
            if len(text) > max_text_length:
                text = text[:max_text_length] + "..."
            formatted_texts.append(f"[预处理结果{i}]\n{text}")

        # 使用格式化函数处理章节信息
        formatted_chapter_info = (
            f"当前章节定位：{chapter_info.get('chapter_role', '')}\n"
            f"核心目标：{chapter_info.get('chapter_purpose', '')}\n"
            f"关键要素：{chapter_info.get('characters_involved', '')} | "
            f"{chapter_info.get('key_items', '')} | "
            f"{chapter_info.get('scene_location', '')}"
        )

        prompt = knowledge_filter_prompt.format(
            chapter_info=formatted_chapter_info,
            retrieved_texts="\n\n".join(formatted_texts) if formatted_texts else "（无检索结果）"
        )
        
        filtered_content = invoke_with_cleaning(llm_adapter, prompt)
        return filtered_content if filtered_content else "（知识内容过滤失败）"
        
    except Exception as e:
        logging.error(f"Error in knowledge filtering: {str(e)}")
        return "（内容过滤过程出错）"

def build_chapter_prompt(
    api_key: str,
    base_url: str,
    model_name: str,
    filepath: str,
    novel_number: int,
    word_number: int,
    temperature: float,
    user_guidance: str,
    characters_involved: str,
    key_items: str,
    scene_location: str,
    time_constraint: str,
    embedding_api_key: str,
    embedding_url: str,
    embedding_interface_format: str,
    embedding_model_name: str,
    embedding_retrieval_k: int = 2,
    interface_format: str = "openai",
    max_tokens: int = 2048,
    timeout: int = 600,
    next_chapter_summary: str = "",
    ending_style: str = "",
    min_word_number: int | None = None,
    runtime_architecture_max_chars: int = 18000,
    runtime_architecture_ignore_budget: bool = False,
) -> str:
    """
    构造当前章节的请求提示词（完整实现版）
    修改重点：
    1. 优化知识库检索流程
    2. 新增内容重复检测机制
    3. 集成提示词应用规则
    """
    # 读取基础文件
    arch_file = resolve_architecture_file(filepath, prefer_active=False)
    full_architecture_text = read_file(arch_file)
    try:
        context_budget = max(4000, min(120000, int(runtime_architecture_max_chars)))
    except (TypeError, ValueError):
        context_budget = 18000
    focus_text = "\n".join(
        str(x or "")
        for x in (
            user_guidance,
            characters_involved,
            key_items,
            scene_location,
            time_constraint,
            f"chapter:{novel_number}",
        )
    )
    novel_architecture_text = build_runtime_architecture_context(
        full_architecture_text,
        max_chars=context_budget,
        focus_text=focus_text,
        section_numbers_hint=(0, 88, 104, 119, 136),
        ignore_budget=bool(runtime_architecture_ignore_budget),
    )
    if not novel_architecture_text:
        novel_architecture_text = full_architecture_text
    if contains_archive_sections(novel_architecture_text):
        raise RuntimeError("运行时架构视图包含归档节（13-87），已阻断生成")
    runtime_guardrail_brief = build_runtime_guardrail_brief(full_architecture_text)
    if runtime_guardrail_brief:
        novel_architecture_text = f"{runtime_guardrail_brief}\n\n{novel_architecture_text}"
    
    # 🆕 动态架构指导注入
    # 自动从架构文件中提取特殊指导（如"程序员思维"、"暧昧技法"等）
    # 避免将特定小说的设定硬编码到程序中
    try:
        arch_reader = ArchitectureReader(novel_architecture_text)
        dynamic_guidelines = arch_reader.get_dynamic_guidelines()
        if dynamic_guidelines:
            logging.info("成功从架构文件中提取动态指导原则")
            # 将提取的指导追加到用户指导后，确保LLM能看到
            special_guide_header = "\n\n【架构文件中的特殊写作指导】\n(请严格遵守以下特定于本小说的创作原则)\n"
            user_guidance = (user_guidance + special_guide_header + dynamic_guidelines) if user_guidance else (special_guide_header + dynamic_guidelines)
    except Exception as e:
        logging.warning(f"提取动态架构指导失败: {e}")

    memory_context = GenerationStateFacade(filepath).load_prompt_memory_context(novel_number)
    global_summary_text = memory_context.global_summary_text
    character_state_text = memory_context.character_state_text
    
    # 获取章节信息
    chapter_info = load_chapter_info(filepath, novel_number)
    chapter_title = chapter_info.get("chapter_title", f"第{novel_number}章")
    chapter_role = chapter_info.get("chapter_role", "")
    chapter_purpose = chapter_info.get("chapter_purpose", "")
    suspense_level = chapter_info.get("suspense_level", "")
    foreshadowing = chapter_info.get("foreshadowing", "")
    plot_twist_level = chapter_info.get("plot_twist_level", "")
    chapter_summary = chapter_info.get("chapter_summary", "")

    # 获取下一章节信息
    next_chapter_number = novel_number + 1
    next_chapter_info = load_chapter_info(filepath, next_chapter_number)
    next_chapter_title = next_chapter_info.get("chapter_title", "（未命名）")
    next_chapter_role = next_chapter_info.get("chapter_role", "过渡章节")
    next_chapter_purpose = next_chapter_info.get("chapter_purpose", "承上启下")
    next_chapter_suspense = next_chapter_info.get("suspense_level", "中等")
    next_chapter_foreshadow = next_chapter_info.get("foreshadowing", "无特殊伏笔")
    next_chapter_twist = next_chapter_info.get("plot_twist_level", "★☆☆☆☆")
    next_chapter_summary = next_chapter_info.get("chapter_summary", "衔接过渡内容")

    # 章节契约卡：把蓝图锚点结构化注入提示词，降低章节漂移概率。
    chapter_contract = build_chapter_contract(
        chapter_info if isinstance(chapter_info, dict) else {},
        characters_involved=characters_involved,
        key_items=key_items,
        scene_location=scene_location,
        time_constraint=time_constraint,
        user_guidance=user_guidance,
    )
    chapter_contract_prompt = build_chapter_contract_prompt(chapter_contract)
    if chapter_contract_prompt:
        user_guidance = (
            f"{user_guidance}\n{chapter_contract_prompt}" if user_guidance else chapter_contract_prompt
        )

    # 创建章节目录
    chapters_dir = os.path.join(filepath, "chapters")
    os.makedirs(chapters_dir, exist_ok=True)

    # 提取主角核心信息用于身份锁定
    protagonist_info = extract_protagonist_info(filepath)
    state_snapshot = _load_runtime_state_snapshot(
        filepath,
        chapter_info if isinstance(chapter_info, dict) else {},
        str(protagonist_info.get("protagonist_name", "")).strip(),
    )

    first_chapter_continuity_guidance = _build_runtime_continuity_guidance(
        memory_guidance=memory_context.memory_guidance,
        global_summary_text=global_summary_text,
        character_state_text=character_state_text,
        next_chapter_summary=next_chapter_summary,
        hook_summary_text=memory_context.hook_summary_text,
        thread_summary_text=memory_context.thread_summary_text,
        state_snapshot=state_snapshot,
    )
    if first_chapter_continuity_guidance:
        user_guidance = _append_guidance_block(user_guidance, first_chapter_continuity_guidance)

    # 🆕 导入新的提示词增强常量
    from prompt_definitions import COT_INSTRUCTIONS, SUBTEXT_GUIDE, LITERARY_STYLE_GUIDE, TWO_TRACK_NARRATIVE_RULE, CULTURAL_DEPTH_GUIDE

    # 动态构建字数指导语
    if min_word_number and min_word_number > 0 and min_word_number < word_number:
        # 如果有明确的最低字数（且小于目标字数）
        word_count_guide = f"""⚠️ **字数要求（弹性范围）**：
1. 目标字数为 {word_number} 字。
2. **最低限度**：{min_word_number} 字（低于此值将视为生成失败）。
3. 最佳区间：{min_word_number}-{word_number} 字之间。
4. 若剧情紧凑，写满 {min_word_number} 字即可；若剧情丰富，可写到 {word_number} 字。"""
    else:
        # 默认模式（无最低字数，或最低字数等于目标字数）
        word_count_guide = f"""⚠️ **字数要求（目标导向）**：
1. 目标字数为 {word_number} 字。
2. 请确保情节充实，尽量接近目标字数。"""

    # 第一章特殊处理
    if novel_number == 1:
        return first_chapter_draft_prompt.format(
            protagonist_name=protagonist_info['protagonist_name'],
            system_name=protagonist_info['system_name'],
            core_abilities=protagonist_info['core_abilities'],
            protagonist_identity=protagonist_info['protagonist_identity'],
            novel_number=novel_number,
            word_number=word_number,
            word_count_guide=word_count_guide, # 传入生成的指导语
            chapter_title=chapter_title,
            chapter_role=chapter_role,
            chapter_purpose=chapter_purpose,
            suspense_level=suspense_level,
            foreshadowing=foreshadowing,
            plot_twist_level=plot_twist_level,
            chapter_summary=chapter_summary,
            characters_involved=characters_involved,
            key_items=key_items,
            scene_location=scene_location,
            time_constraint=time_constraint,
            user_guidance=user_guidance,
            novel_setting=novel_architecture_text,
            # 🆕 注入新的增强指令
            cot_instructions=COT_INSTRUCTIONS,
            subtext_guide=SUBTEXT_GUIDE,
            literary_style_guide=LITERARY_STYLE_GUIDE,
            TWO_TRACK_NARRATIVE_RULE=TWO_TRACK_NARRATIVE_RULE
        )

    # 获取前文内容和摘要
    recent_texts = get_last_n_chapters_text(chapters_dir, novel_number, n=3)
    
    try:
        logging.info("Attempting to generate summary")
        short_summary = summarize_recent_chapters(
            interface_format=interface_format,
            api_key=api_key,
            base_url=base_url,
            model_name=model_name,
            temperature=temperature,
            max_tokens=max_tokens,
            chapters_text_list=recent_texts,
            novel_number=novel_number,
            chapter_info=chapter_info,
            next_chapter_info=next_chapter_info,
            timeout=timeout
        )
        logging.info("Summary generated successfully")
    except Exception as e:
        logging.error(f"Error in summarize_recent_chapters: {str(e)}")
        short_summary = "（摘要生成失败）"

    # 获取前一章结尾
    previous_excerpt = ""
    for text in reversed(recent_texts):
        if text.strip():
            previous_excerpt = text[-800:] if len(text) > 800 else text
            break

    # 【重要】添加禁止剧情回滚的强指令
    if previous_excerpt:
        anti_repetition_instruction = """
【重要指令：禁止剧情回滚 + 强制衔接】

一、禁止剧情回滚：
请仔细阅读"前文片段"。新章节必须紧接前文结尾继续发展，**严禁**重复前文结尾已经发生的事件（如已经获得的奖励、已经完成的对话等）。
如果前文结尾主角已经完成了某个动作（如"签到"），新章节开头**绝对不能**再次描写该动作，而应直接描写该动作之后的结果或后续反应。

二、强制衔接要求：
本章第一段（前100字）必须与前章结尾直接关联，使用以下任一过渡方式：
1. 时间过渡："片刻后..."、"第二天清晨..."、"不知过了多久..."
2. 空间过渡："离开XX后..."、"回到XX..."、"走出XX..."
3. 情感过渡："想到刚才的XX..."、"心中那股XX..."
4. 动作延续：直接承接前章最后一个动作的后续

**严禁**：突然切换场景或视角而不做任何过渡！
"""
        user_guidance = f"{user_guidance}\n{anti_repetition_instruction}"

    # 【关键修复】叙事语言纯度硬约束：外轨禁止科技词，系统提示禁止流程播报
    narrative_purity_instruction = """
【叙事语言纯度·硬约束（最高优先级）】

一、外轨（旁白/人物对话）严禁出现现代技术词汇：
- 禁用词示例：程序、数据、下载、上传、服务器、CPU、Bug、接口、调试、解析、重铸、碎片
- 若需表达“看穿/推演/修复”，必须改写为仙侠语汇：神念、推演、参悟、洗髓、机缘、道痕

二、系统/金手指提示语禁止“流程播报”写法：
- 严禁：检测到…、正在…、加载中…、进度xx%
- 只允许“结果导向”写法：直接给出结论、目标、代价、反馈

三、双轨边界：
- 内轨（主角内心、系统面板）可出现少量机制化表达，但必须古风化、结果化。
- 外轨一旦出现科技词汇，视为出戏违规，必须重写。
"""
    user_guidance = f"{user_guidance}\n{narrative_purity_instruction}"

    # 🔧 Fix 3.6: 开头去重机制 — 防止多章以相同字/词开头
    if novel_number > 1:
        try:
            openings = extract_chapter_openings(chapters_dir, novel_number, max_scan=20)
            if openings:
                # 统计首字频率
                from collections import Counter
                char_counts = Counter(char for _, char in openings)
                # 找出出现3次以上的高频首字
                overused = [char for char, count in char_counts.items() if count >= 3]
                if overused:
                    forbidden_chars = "、".join(f"「{c}」" for c in overused)
                    opening_diversity_guide = f"""
【开头多样性要求】⚠️
近{len(openings)}章中以下字/词作为章节开头已过度重复，本章**严禁**以这些字开头：
{forbidden_chars}
请使用完全不同的开头方式，例如：对话、动作、环境声音、心理活动等。
"""
                    user_guidance = f"{user_guidance}\n{opening_diversity_guide}"
                    logging.info(f"🔧 Fix 3.6: 检测到高频开头字: {overused}，已注入去重约束")
        except Exception as e:
            logging.debug(f"开头去重分析跳过: {e}")

    # 【重要】黄金三章法则 (Ch 2 & Ch 3 特别增强)
    if novel_number in [2, 3]:
        golden_three_guide = """
【黄金三章·法则延续】(Ch 2-3 特别指导)
黄金三章的核心任务是：留存+期待。

📌 第2章核心任务：【铺垫与发酵】
- 承接第1章的悬念，给出初步解释，但立即引出更大的麻烦。
- 展示金手指/系统的初步威力（小试牛刀），让读者尝到甜头。
- 确立第一个反派/针对者的仇恨值，建立"被压迫->要反抗"的动力。

📌 第3章核心任务：【小高潮/显性冲突】
- 必须出现第一个完整的矛盾冲突闭环（如：打脸前的小冲突、获得宝物的惊险过程）。
- 主角必须完成一次"确立地位"或"展示不凡"的行动。
- 结尾必须抛出【第一个长期目标】或【重大危机预警】，开启正式剧情。

⚠️ 节奏警示：
- 严禁水字数！前三章每一句废话都会导致读者流失。
- 严禁大量说明书式设定堆砌，设定必须在剧情中抛出。
"""
        user_guidance = f"{user_guidance}\n{golden_three_guide}"
        logging.info(f"Injecting Golden Three guidance for Chapter {novel_number}")

    # 🆕 节奏大师 (Rhythm Agent) 介入 - 从第4章开始介入
    if novel_number >= 4:
        try:
            # 临时复用 summary_llm 的配置或主 LLM 配置
            pacing_llm_config = {
                'api_key': api_key,
                'base_url': base_url,
                'model_name': model_name,
                'interface_format': interface_format
            }
            pacing_agent = PacingAgent(pacing_llm_config)
            
            # 使用已获取的 recent_texts (最近3章)
            logging.info(f"🎵 Pacing Agent analyzing last {len(recent_texts)} chapters...")
            analysis_result = pacing_agent.analyze_pacing(recent_texts)
            pacing_guidance = pacing_agent.get_pacing_guidance(analysis_result)
            
            if pacing_guidance:
                user_guidance = f"{user_guidance}\n{pacing_guidance}"
                logging.info("✅ Pacing guidance injected.")
        except Exception as e:
            logging.warning(f"Pacing Agent failed: {e}")

    # 知识库检索和处理
    try:
        # 生成检索关键词
        llm_adapter = create_llm_adapter(
            interface_format=interface_format,
            base_url=base_url,
            model_name=model_name,
            api_key=api_key,
            temperature=0.3,
            max_tokens=max_tokens,
            timeout=timeout
        )
        
        search_prompt = knowledge_search_prompt.format(
            chapter_number=novel_number,
            chapter_title=chapter_title,
            characters_involved=characters_involved,
            key_items=key_items,
            scene_location=scene_location,
            chapter_role=chapter_role,
            chapter_purpose=chapter_purpose,
            foreshadowing=foreshadowing,
            short_summary=short_summary,
            user_guidance=user_guidance,
            time_constraint=time_constraint
        )
        
        search_response = invoke_with_cleaning(llm_adapter, search_prompt)
        keyword_groups = parse_search_keywords(search_response)

        # 执行向量检索
        all_contexts = []
        from embedding_adapters import create_embedding_adapter, is_embedding_adapter_available

        # 创建embedding适配器
        embedding_adapter = None
        try:
            embedding_adapter = create_embedding_adapter(
                embedding_interface_format,
                embedding_api_key,
                embedding_url,
                embedding_model_name
            )
        except Exception as e:
            logging.warning(f"Failed to create embedding adapter: {e}")

        # 检查embedding适配器是否可用
        if embedding_adapter and is_embedding_adapter_available(embedding_adapter):
            store = load_vector_store(embedding_adapter, filepath)
            if store:
                collection_size = store._collection.count()
                actual_k = min(embedding_retrieval_k, max(1, collection_size))

                for group in keyword_groups:
                    context = get_relevant_context_from_vector_store(
                        embedding_adapter=embedding_adapter,
                        query=group,
                        filepath=filepath,
                        k=actual_k
                    )
                    if context:
                        if any(kw in group.lower() for kw in ["技法", "手法", "模板"]):
                            all_contexts.append(f"[TECHNIQUE] {context}")
                        elif any(kw in group.lower() for kw in ["设定", "技术", "世界观"]):
                            all_contexts.append(f"[SETTING] {context}")
                        else:
                            all_contexts.append(f"[GENERAL] {context}")
            else:
                logging.info("Vector store not available, skipping knowledge retrieval")
        else:
            logging.warning("Embedding adapter not available, skipping vector search. This is likely due to missing API keys.")

        # 应用内容规则
        processed_contexts = apply_content_rules(all_contexts, novel_number)
        
        # 执行知识过滤
        chapter_info_for_filter = {
            "chapter_number": novel_number,
            "chapter_title": chapter_title,
            "chapter_role": chapter_role,
            "chapter_purpose": chapter_purpose,
            "characters_involved": characters_involved,
            "key_items": key_items,
            "scene_location": scene_location,
            "foreshadowing": foreshadowing,  # 修复拼写错误
            "suspense_level": suspense_level,
            "plot_twist_level": plot_twist_level,
            "chapter_summary": chapter_summary,
            "time_constraint": time_constraint
        }
        
        filtered_context = get_filtered_knowledge_context(
            api_key=api_key,
            base_url=base_url,
            model_name=model_name,
            interface_format=interface_format,
            embedding_adapter=embedding_adapter,
            filepath=filepath,
            chapter_info=chapter_info_for_filter,
            retrieved_texts=processed_contexts,
            max_tokens=max_tokens,
            timeout=timeout
        )
        
    except Exception as e:
        logging.error(f"知识处理流程异常：{str(e)}")
        filtered_context = "（知识库处理失败）"

    continuity_guidance = _build_runtime_continuity_guidance(
        memory_guidance=memory_context.memory_guidance,
        global_summary_text=global_summary_text,
        character_state_text=character_state_text,
        short_summary=short_summary,
        previous_excerpt=previous_excerpt,
        filtered_context=filtered_context,
        next_chapter_summary=next_chapter_summary,
        hook_summary_text=memory_context.hook_summary_text,
        thread_summary_text=memory_context.thread_summary_text,
        state_snapshot=state_snapshot,
    )
    if continuity_guidance:
        user_guidance = _append_guidance_block(user_guidance, continuity_guidance)

    # 【重要】叙事技法指导
    NARRATIVE_TECHNIQUES = """
【写作技法要求】
1. 设定融入: 通过对话/行动/内心独白自然展现,禁止直接罗列设定。
2. 冲突节奏: 每1000字至少1个小冲突或悬念点,保持阅读张力。
3. 描写多样化: 
   - 避免高频词: "脸色苍白""眼中闪过""心头一紧""嘴角勾起"
   - 使用五感细节: 视觉/听觉/触觉/嗅觉/味觉
4. 情绪具体化: 用动作/生理反应代替抽象词汇(如用"指尖颤抖"代替"害怕")。
"""
    user_guidance = f"{user_guidance}\n{NARRATIVE_TECHNIQUES}"



    # 【网文智能创作引擎】修为进度管理器（P1强化版）
    cultivation_constraint = get_cultivation_constraint(novel_number)
    if cultivation_constraint.get("constraint_text"):
        # P1: 优先使用蓝图预处理判断是否为突破章节
        is_breakthrough = False

        
        # 如果预处理未启用或判断为False（可能是没缓存），通过关键词检测回退
        if not is_breakthrough:
            is_breakthrough = any(
                keyword in chapter_summary.lower() 
                for keyword in ["突破", "晋级", "进阶", "跨入", "踏入"]
            ) if chapter_summary else False            
        
        if is_breakthrough:
            cultivation_guidance = f"""
╔════════════════════════════════════════════════════════════════╗
║ 🔓 【突破章节】本章蓝图允许主角境界突破                          ║
╠════════════════════════════════════════════════════════════════╣
║ 当前境界：{cultivation_constraint['current_realm']}                                        ║
║ 本章可突破至：{cultivation_constraint['max_realm']}                                 ║
║ 要求：必须有充分的突破铺垫、瓶颈描写、突破契机                  ║
╚════════════════════════════════════════════════════════════════╝
"""
            logging.info(f"第{novel_number}章为【突破章节】，允许突破至{cultivation_constraint['max_realm']}")
        else:
            cultivation_guidance = f"""
╔════════════════════════════════════════════════════════════════╗
║ 🔒 【非突破章节】本章严禁任何形式的境界提升！                    ║
╠════════════════════════════════════════════════════════════════╣
║ 当前锁定境界：{cultivation_constraint['current_realm']}                                  ║
║ 禁止内容：突破、晋级、修为提升、实力暴涨                        ║
║ 允许内容：积累、修炼、感悟瓶颈、为突破做准备                    ║
╚════════════════════════════════════════════════════════════════╝
本章主角的所有战斗、修炼场景中，修为必须维持在【{cultivation_constraint['current_realm']}】。
若描写修炼，应强调"尚在积累""距突破还有距离"的感觉。
"""
            logging.info(f"第{novel_number}章为【非突破章节】，修为锁定在{cultivation_constraint['current_realm']}")
        
        user_guidance = f"{user_guidance}\n{cultivation_guidance}"






    # 返回最终提示词
    return next_chapter_draft_prompt.format(
        protagonist_name=protagonist_info['protagonist_name'],
        system_name=protagonist_info['system_name'],
        core_abilities=protagonist_info['core_abilities'],
        protagonist_identity=protagonist_info['protagonist_identity'],
        user_guidance=user_guidance if user_guidance else "无特殊指导",
        novel_number=novel_number,
        foreshadowing=foreshadowing,
        plot_twist_level=plot_twist_level,
        chapter_summary=chapter_summary,
        word_number=word_number,
        characters_involved=characters_involved,
        key_items=key_items,
        scene_location=scene_location,
        time_constraint=time_constraint,
        novel_setting=novel_architecture_text,  # 修复：传入小说架构文本
        # 🆕 注入新的增强指令
        cot_instructions=COT_INSTRUCTIONS,
        subtext_guide=SUBTEXT_GUIDE,
        literary_style_guide=LITERARY_STYLE_GUIDE,
        TWO_TRACK_NARRATIVE_RULE=TWO_TRACK_NARRATIVE_RULE,
        # 🔧 Fix 3.5: 注入文化深度指南（违禁词转换表）
        cultural_depth_guide=CULTURAL_DEPTH_GUIDE
    )

def generate_chapter_draft(
    api_key: str,
    base_url: str,
    model_name: str,
    filepath: str,
    novel_number: int,
    word_number: int,
    temperature: float,
    user_guidance: str,
    characters_involved: str,
    key_items: str,
    scene_location: str,
    time_constraint: str,
    embedding_api_key: str,
    embedding_url: str,
    embedding_interface_format: str,
    embedding_model_name: str,
    min_word_number: int | None = None,
    embedding_retrieval_k: int = 2,
    interface_format: str = "openai",
    max_tokens: int = 2048,
    timeout: int = 600,
    custom_prompt_text: str | None = None,
    custom_prompt_is_complete: bool = False,
    runtime_architecture_max_chars: int = 18000,
    runtime_architecture_ignore_budget: bool = False,
    language_purity_enabled: bool = True,
    auto_correct_mixed_language: bool = True,
    preserve_proper_nouns: bool = True,
    strict_language_mode: bool = False,
    auto_optimize: bool = True
) -> str:
    """
    生成章节草稿，支持自定义提示词
    """
    # 获取章节信息，用于生成标题（优先读取 chapter_blueprints/chapter_X.txt）
    chapter_info = load_chapter_info(filepath, novel_number)

    # P3优化1: 动态字数控制
    word_count_target_str = chapter_info.get("word_count_target", "")
    if word_count_target_str:
        # 尝试提取最大值，例如 "800-1200字" -> 1200
        matches = re.findall(r'\d+', word_count_target_str)
        if matches:
            # 取最大值作为上限，稍微增加一点余量(10%)以防止截断
            max_val = max(map(int, matches))
            word_number = int(max_val * 1.1)
            logging.info(f"Using dynamic word count from blueprint: {word_number} (target: {word_count_target_str})")

    # P3优化2: 结尾多样性控制
    import random
    ending_style = random.choice(ENDING_STYLES)
    logging.info(f"Selected ending style for chapter {novel_number}: {ending_style}")

    # P3优化3: 剧情围栏 (获取下一章摘要)
    next_chapter_summary = chapter_info.get("next_chapter_summary", "")

    # 使用工具函数清理章节标题
    from chapter_title_utils import clean_chapter_title, add_chapter_title_if_missing
    chapter_title = clean_chapter_title(chapter_info.get("chapter_title", f"第{novel_number}章"))
    if custom_prompt_text is None:
        prompt_text = build_chapter_prompt(
            api_key=api_key,
            base_url=base_url,
            model_name=model_name,
            filepath=filepath,
            novel_number=novel_number,
            word_number=word_number,
            min_word_number=min_word_number,  # 传递此参数
            temperature=temperature,
            user_guidance=user_guidance,
            characters_involved=characters_involved,
            key_items=key_items,
            scene_location=scene_location,
            time_constraint=time_constraint,
            embedding_api_key=embedding_api_key,
            embedding_url=embedding_url,
            embedding_interface_format=embedding_interface_format,
            embedding_model_name=embedding_model_name,
            embedding_retrieval_k=embedding_retrieval_k,
            interface_format=interface_format,
            max_tokens=max_tokens,
            timeout=timeout,
            next_chapter_summary=next_chapter_summary,
            ending_style=ending_style,
            runtime_architecture_max_chars=runtime_architecture_max_chars,
            runtime_architecture_ignore_budget=runtime_architecture_ignore_budget,
        )
    else:
        prompt_text = custom_prompt_text.strip()
        if not custom_prompt_is_complete:
            memory_context = GenerationStateFacade(filepath).load_prompt_memory_context(novel_number)
            protagonist_name = extract_protagonist_info(filepath).get("protagonist_name", "")
            state_snapshot = _load_runtime_state_snapshot(
                filepath,
                chapter_info if isinstance(chapter_info, dict) else {},
                str(protagonist_name).strip(),
            )
            custom_runtime_guidance = _build_runtime_continuity_guidance(
                memory_guidance=memory_context.memory_guidance,
                global_summary_text=memory_context.global_summary_text,
                character_state_text=memory_context.character_state_text,
                next_chapter_summary=next_chapter_summary,
                hook_summary_text=memory_context.hook_summary_text,
                thread_summary_text=memory_context.thread_summary_text,
                state_snapshot=state_snapshot,
            )
            if custom_runtime_guidance:
                prompt_text = _append_guidance_block(prompt_text, custom_runtime_guidance)

    try:
        runtime_guardrail_prefix = _build_runtime_guardrail_prefix(filepath)
        if runtime_guardrail_prefix and RUNTIME_GUARDRAIL_MARKER not in prompt_text:
            prompt_text = f"{runtime_guardrail_prefix}\n\n{prompt_text}"
    except Exception as e:
        logging.error(f"运行时架构守卫失败: {e}")
        raise


    # Timeline Ledger Injection (all generation paths)
    try:
        timeline_manager = TimelineManager(filepath)
        timeline_snapshot = timeline_manager.get_timeline_snapshot()
        prompt_text = f"{prompt_text}\n\n{timeline_snapshot}"
    except Exception as e:
        logging.debug(f"Timeline Manager injection skipped: {e}")

    chapters_dir = os.path.join(filepath, "chapters")
    os.makedirs(chapters_dir, exist_ok=True)

    # 🔧 Fix 3.7: Token预算控制 — 防止prompt过长导致输出被压缩为"电报体"
    # 中文约1.5 token/字符，预留足够的输出空间
    estimated_prompt_tokens = int(len(prompt_text) * 1.5)
    # 常见模型上下文窗口：8k/16k/32k/128k，假设保守值
    # max_tokens 是输出token上限，prompt不应超过总窗口的75%
    # 假设总窗口 = max(max_tokens * 4, 16000)
    estimated_context_window = max(max_tokens * 4, 16000)
    safe_prompt_budget = int(estimated_context_window * 0.75)
    
    if estimated_prompt_tokens > safe_prompt_budget:
        logging.warning(
            f"⚠️ Token预算警告: prompt约{estimated_prompt_tokens}token，"
            f"安全预算{safe_prompt_budget}token（窗口{estimated_context_window}），"
            f"正在裁剪prompt以防止输出被压缩..."
        )
        # 裁剪策略：保留开头（核心设定）和结尾（格式要求），裁剪中间部分
        safe_char_limit = int(safe_prompt_budget / 1.5)
        if len(prompt_text) > safe_char_limit:
            # 保留开头+中段+结尾，减少关键蓝图约束丢失风险
            head_size = int(safe_char_limit * 0.30)
            mid_size = int(safe_char_limit * 0.40)
            tail_size = int(safe_char_limit * 0.30)
            mid_start = max(0, (len(prompt_text) // 2) - (mid_size // 2))
            mid_end = min(len(prompt_text), mid_start + mid_size)
            truncation_notice = "\n\n【系统提示：上下文已精简以确保输出质量，请基于现有信息创作】\n\n"
            prompt_text = (
                prompt_text[:head_size]
                + truncation_notice
                + prompt_text[mid_start:mid_end]
                + truncation_notice
                + prompt_text[-tail_size:]
            )
            logging.info(f"prompt已裁剪至{len(prompt_text)}字符（原{estimated_prompt_tokens}token → 约{int(len(prompt_text)*1.5)}token）")

    llm_adapter = create_llm_adapter(
        interface_format=interface_format,
        base_url=base_url,
        model_name=model_name,
        api_key=api_key,
        temperature=temperature,
        max_tokens=max_tokens,
        timeout=timeout
    )

    chapter_content = invoke_with_cleaning(llm_adapter, prompt_text)
    
    # 🆕 记录初始生成日志
    _log_generation_to_file(filepath, novel_number, "initial_draft", prompt_text, chapter_content)

    # 🔧 Fix 3.2: 空白章节重试兜底 — 防止空内容被保存为仅含标题的文件
    if not chapter_content.strip():
        logging.warning(f"第{novel_number}章生成结果为空，启动重试...")
        for _retry_i in range(3):
            logging.info(f"空白章节重试 {_retry_i + 1}/3...")
            chapter_content = invoke_with_cleaning(llm_adapter, prompt_text)
            if chapter_content.strip():
                logging.info(f"重试成功，第{novel_number}章已获取有效内容")
                _log_generation_to_file(filepath, novel_number, f"retry_{_retry_i+1}", prompt_text, chapter_content)
                break
            if _retry_i < 2:
                cooldown_seconds = 5 * (_retry_i + 1)
                logging.warning(
                    f"第{novel_number}章仍为空，等待{cooldown_seconds}秒后继续重试..."
                )
                time.sleep(cooldown_seconds)
        if not chapter_content.strip():
            error_msg = f"第{novel_number}章在3次重试后仍为空白，生成失败"
            logging.error(error_msg)
            raise RuntimeError(error_msg)

    # 使用工具函数添加章节标题
    chapter_content_with_title = add_chapter_title_if_missing(
        chapter_content, novel_number, chapter_title
    )

    # 🔧 Fix 3.3: 调用已有的标题去重函数 — 防止"第X章 第X章"
    chapter_content_with_title = fix_chapter_title(chapter_content_with_title)

    # Auto-Optimization Step
    if auto_optimize:
        try:
            from novel_generator.text_optimizer import ChapterTextOptimizer
            # Initialize optimizer
            optimizer = ChapterTextOptimizer(filepath)
            # Optimize content directly
            optimized_content = optimizer.optimize_content(
                chapter_content_with_title, 
                novel_number, 
                target_word_count=word_number  # Pass the target word count
            )
            
            if optimized_content != chapter_content_with_title:
                logging.info(f"✨ Chapter {novel_number} optimized automatically.")
                chapter_content_with_title = optimized_content
        except Exception as e:
            logging.error(f"⚠️ Auto-optimization failed: {e}")

    chapter_file = os.path.join(chapters_dir, f"chapter_{novel_number}.txt")
    clear_file_content(chapter_file)
    save_string_to_txt(chapter_content_with_title, chapter_file)
    logging.info(f"[Draft] Chapter {novel_number} generated as a draft with title.")
    return chapter_content_with_title

def generate_chapter_with_precise_word_count(
    api_key: str,
    base_url: str,
    model_name: str,
    filepath: str,
    novel_number: int,
    word_number: int,
    temperature: float,
    user_guidance: str,
    characters_involved: str,
    key_items: str,
    scene_location: str,
    time_constraint: str,
    embedding_api_key: str,
    embedding_url: str,
    embedding_interface_format: str,
    embedding_model_name: str,
    embedding_retrieval_k: int = 2,
    interface_format: str = "openai",
    max_tokens: int = 2048,
    timeout: int = 600,
    custom_prompt_text: str | None = None,
    language_purity_enabled: bool = True,
    auto_correct_mixed_language: bool = True,
    preserve_proper_nouns: bool = True,
    strict_language_mode: bool = False,
    ensure_precise_word_count: bool = True,
    word_count_tolerance: float = 0.05,
    max_word_count_retries: int = 3
) -> tuple[str, dict[str, Any]]:
    """
    生成章节草稿并确保字数精确达标

    Args:
        所有原有参数...
        ensure_precise_word_count: 是否启用精确字数控制（默认True）
        word_count_tolerance: 字数容差范围（默认5%）
        max_word_count_retries: 字数调整最大重试次数（默认3次）

    Returns:
        tuple: (章节内容, 生成报告)
    """

    # 标准生成流程
    logging.info(f"[基础生成] Chapter {novel_number} 目标字数: {word_number}字")
    original_content = generate_chapter_draft(
        api_key=api_key,
        base_url=base_url,
        model_name=model_name,
        filepath=filepath,
        novel_number=novel_number,
        word_number=word_number,
        temperature=temperature,
        user_guidance=user_guidance,
        characters_involved=characters_involved,
        key_items=key_items,
        scene_location=scene_location,
        time_constraint=time_constraint,
        embedding_api_key=embedding_api_key,
        embedding_url=embedding_url,
        embedding_interface_format=embedding_interface_format,
        embedding_model_name=embedding_model_name,
        embedding_retrieval_k=embedding_retrieval_k,
        interface_format=interface_format,
        max_tokens=max_tokens,
        timeout=timeout,
        custom_prompt_text=custom_prompt_text,
        language_purity_enabled=language_purity_enabled,
        auto_correct_mixed_language=auto_correct_mixed_language,
        preserve_proper_nouns=preserve_proper_nouns,
        strict_language_mode=strict_language_mode
    )

    # ========== 新增：自动续写机制 ==========
    current_stats = count_chapter_words(original_content)
    current_words = int(current_stats['chinese_chars'])
    min_required = int(word_number * 0.8)  # 至少达到目标的80%
    
    continuation_count = 0
    continuation_log = []
    
    if ensure_precise_word_count and current_words < min_required:
        logging.warning(f"[字数不足] Chapter {novel_number}: 当前{current_words}字 < 最低要求{min_required}字，启动自动续写...")
        
        # 创建续写用的LLM适配器
        continuation_adapter = create_llm_adapter(
            interface_format=interface_format,
            base_url=base_url,
            model_name=model_name,
            api_key=api_key,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout
        )
        
        while current_words < min_required and continuation_count < max_word_count_retries:
            continuation_count += 1
            words_needed = word_number - current_words
            
            # 获取最后2000字作为上下文
            context_text = original_content[-3000:] if len(original_content) > 3000 else original_content
            
            continuation_prompt = f"""你正在续写一个未完成的小说章节。

【当前进度】已写{current_words}字，目标{word_number}字，还需约{words_needed}字

【已有内容（最后部分）】
{context_text}

【续写要求】
1. 继续发展当前情节，保持风格和语调一致
2. 自然衔接，不要重复已有内容
3. 请写约{words_needed}字的续写内容
4. 不要写"续写完毕"等元叙述，直接写正文

请直接续写："""

            logging.info(f"[续写尝试 {continuation_count}/{max_word_count_retries}] 需要补充约{words_needed}字...")
            
            try:
                continuation = invoke_with_cleaning(continuation_adapter, continuation_prompt)
                
                # 🆕 记录续写日志
                _log_generation_to_file(filepath, novel_number, f"continuation_{continuation_count}", continuation_prompt, continuation)

                if continuation and continuation.strip():
                    # 追加续写内容
                    original_content = original_content.rstrip() + "\n\n" + continuation.strip()
                    
                    # 重新统计字数
                    current_stats = count_chapter_words(original_content)
                    new_words = int(current_stats['chinese_chars'])
                    added_words = new_words - current_words
                    
                    continuation_log.append({
                        'attempt': continuation_count,
                        'words_before': current_words,
                        'words_after': new_words,
                        'words_added': added_words
                    })
                    
                    logging.info(f"[续写成功] 新增{added_words}字，当前总计{new_words}字")
                    current_words = new_words
                else:
                    logging.warning(f"[续写失败] 第{continuation_count}次续写返回空内容")
                    
            except Exception as e:
                logging.error(f"[续写异常] 第{continuation_count}次续写失败: {e}")
                break
        
        if current_words >= min_required:
            logging.info(f"[续写完成] Chapter {novel_number} 最终字数: {current_words}字 (目标: {word_number}字)")
        else:
            logging.warning(f"[续写不足] Chapter {novel_number} 达到最大重试次数，当前字数: {current_words}字")

    # 生成报告
    final_stats = count_chapter_words(original_content)
    basic_report = {
        'target_words': word_number,
        'final_words': final_stats['chinese_chars'],
        'success': final_stats['chinese_chars'] >= min_required,
        'method': 'auto_continuation' if continuation_count > 0 else 'standard',
        'intelligent_control_enabled': ensure_precise_word_count,
        'continuation_attempts': continuation_count,
        'continuation_log': continuation_log
    }

    return original_content, basic_report





