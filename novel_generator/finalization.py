#novel_generator/finalization.py
# -*- coding: utf-8 -*-
"""
章节处理模块：
- polish_chapter_content: 真正的文章内容精校（润色、格式规范、错别字修正）
- update_context_data: 更新上下文资料（摘要、角色状态、向量库）
- enrich_chapter_text: 扩写章节
- finalize_chapter: 向后兼容别名 → update_context_data
"""
import os
import logging
import re
from typing import Any
from llm_adapters import create_llm_adapter
from embedding_adapters import create_embedding_adapter
from prompt_definitions import summary_prompt, update_character_state_prompt
from novel_generator.common import invoke_with_cleaning
from utils import read_file
from novel_generator.generation_state_facade import GenerationStateFacade
from novel_generator.state_manager import WorldStateManager
from novel_generator.hook_tracker import HookTracker
from novel_generator.narrative_threads import NarrativeThreadTracker
from novel_generator.timeline_manager import TimelineManager
from novel_generator.story_ledger import _build_chapter_summary
from novel_generator.vectorstore_utils import update_vector_store
from novel_generator.wordcount_utils import count_chapter_words
logging.basicConfig(
    filename='app.log',      # 日志文件名
    filemode='a',            # 追加模式（'w' 会覆盖）
    level=logging.INFO,      # 记录 INFO 及以上级别的日志
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)


def check_chapter_similarity(
    new_chapter: str,
    previous_chapter: str,
    threshold: float = 0.15,
) -> tuple[bool, float, list[str]]:
    """
    检测新章节与前一章的相似度，防止跨章节内容重复
    
    Args:
        new_chapter: 新生成的章节内容
        previous_chapter: 前一章的内容
        threshold: 重复段落占比阈值，超过则判定为相似（默认15%）
    
    Returns:
        tuple: (is_similar: bool, similarity_score: float, duplicate_segments: list)
    """
    if not new_chapter or not previous_chapter:
        return False, 0.0, []
    
    # 按段落拆分
    new_paragraphs = [p.strip() for p in new_chapter.split('\n\n') if p.strip() and len(p.strip()) > 30]
    prev_paragraphs = [p.strip() for p in previous_chapter.split('\n\n') if p.strip() and len(p.strip()) > 30]
    
    if not new_paragraphs:
        return False, 0.0, []
    
    duplicate_segments: list[str] = []
    
    for new_para in new_paragraphs:
        # 取前80字符作为指纹
        fingerprint = new_para[:80]
        for prev_para in prev_paragraphs:
            # 检测前80字符是否在前一章出现
            if fingerprint in prev_para or prev_para[:80] in new_para:
                duplicate_segments.append(new_para[:60] + "...")
                break
    
    # 相似度计算：重复段落数 / 总段落数
    similarity = len(duplicate_segments) / len(new_paragraphs) if new_paragraphs else 0.0
    is_similar = similarity > threshold
    
    if is_similar:
        logging.warning(f"章节相似度过高: {similarity:.2%}，发现{len(duplicate_segments)}个重复段落")
    
    return is_similar, similarity, duplicate_segments


def get_previous_chapter_anchor(chapters_dir: str, current_chapter_num: int, anchor_length: int = 300) -> str:
    """
    获取前一章尾部内容作为上下文锚点，防止内容重复
    
    Args:
        chapters_dir: 章节目录
        current_chapter_num: 当前章节号
        anchor_length: 锚点长度（默认300字符）
    
    Returns:
        前一章尾部内容
    """
    if current_chapter_num <= 1:
        return ""
    
    prev_file = os.path.join(chapters_dir, f"chapter_{current_chapter_num - 1}.txt")
    if not os.path.exists(prev_file):
        return ""
    
    try:
        with open(prev_file, 'r', encoding='utf-8') as f:
            content = f.read()
        # 返回尾部anchor_length字符
        anchor = content[-anchor_length:] if len(content) > anchor_length else content
        logging.info(f"获取第{current_chapter_num - 1}章尾部{len(anchor)}字符作为上下文锚点")
        return anchor
    except IOError as e:
        logging.warning(f"无法读取前一章内容: {e}")
        return ""


def _validate_and_clean_summary(new_summary: str, max_length: int = 4000) -> str:
    """
    验证并清理摘要内容，防止重复累积
    
    Args:
        new_summary: LLM生成的新摘要
        max_length: 最大允许字符数（约2000字）
    
    Returns:
        清理后的摘要
    """
    if not new_summary:
        return new_summary
    
    # 1. 检测字数是否异常膨胀
    if len(new_summary) > max_length:
        logging.warning(f"Summary length {len(new_summary)} exceeds max {max_length}, truncating...")
        # 尝试只保留最后的有效内容（假设最新内容在末尾）
        paragraphs = new_summary.strip().split('\n\n')
        result = []
        current_length = 0
        for para in reversed(paragraphs):
            if current_length + len(para) < max_length:
                result.insert(0, para)
                current_length += len(para) + 2
            else:
                break
        new_summary = '\n\n'.join(result) if result else new_summary[-max_length:]
    
    # 2. 检测并移除重复段落
    paragraphs = new_summary.split('\n\n')
    seen_paragraphs = set()
    unique_paragraphs = []
    for para in paragraphs:
        para_stripped = para.strip()
        # 使用段落前100个字符作为去重key，避免完全相同段落重复
        para_key = para_stripped[:100] if len(para_stripped) > 100 else para_stripped
        if para_key and para_key not in seen_paragraphs:
            seen_paragraphs.add(para_key)
            unique_paragraphs.append(para)
        elif not para_stripped:
            continue  # 跳过空段落
    
    cleaned = '\n\n'.join(unique_paragraphs)
    
    if len(cleaned) < len(new_summary):
        logging.info(f"Summary cleaned: {len(new_summary)} -> {len(cleaned)} chars")
    
    return cleaned


def _extract_top_level_state_names(state_text: str) -> list[str]:
    names: list[str] = []
    for raw_line in (state_text or "").splitlines():
        line = raw_line.strip()
        if not line or line.startswith(("├", "│", "└", "-", "*")):
            continue
        match = re.match(r"^([^\s:：]{2,16})[：:]\s*$", line)
        if not match:
            continue
        name = match.group(1).strip()
        if name and name not in names:
            names.append(name)
    return names


def _is_close_name_variant(candidate: str, canonical: str) -> bool:
    if not candidate or not canonical:
        return False
    if len(candidate) != len(canonical):
        return False
    if len(canonical) < 2:
        return False
    if candidate[0] != canonical[0]:
        return False
    diff_count = sum(1 for a, b in zip(candidate, canonical) if a != b)
    return diff_count == 1


def _normalize_protagonist_name_drift(text: str, protagonist_name: str) -> str:
    content = text or ""
    canonical = (protagonist_name or "").strip()
    if not canonical:
        return content

    normalized = content
    prefix_boundary = r'(?:(?<=^)|(?<=[\s"“”\'‘’（(【\[\{：:，。！？、\n\-─│├└]))'
    normalized = re.sub(
        rf"{prefix_boundary}1(?=[\u4e00-\u9fff])",
        canonical,
        normalized,
    )
    normalized = re.sub(
        rf"{prefix_boundary}1(?=[：:，。！？、\s\"“”'‘’])",
        canonical,
        normalized,
    )

    for alias in _extract_top_level_state_names(normalized):
        if _is_close_name_variant(alias, canonical):
            normalized = normalized.replace(alias, canonical)
    return normalized


def _summary_is_valid(summary_text: str, chapter_text: str, protagonist_name: str) -> bool:
    text = (summary_text or "").strip()
    if len(text) < 120:
        return False
    if len(text) > 5000:
        return False
    canonical = (protagonist_name or "").strip()
    if canonical and canonical in (chapter_text or "") and canonical not in text:
        return False
    return True


def _character_state_is_valid(state_text: str, chapter_text: str, protagonist_name: str) -> bool:
    text = (state_text or "").strip()
    if not text:
        return False
    if "生死状态" not in text:
        return False

    canonical = (protagonist_name or "").strip()
    if canonical and canonical in (chapter_text or ""):
        if canonical not in text:
            return False
        if f"{canonical}：" not in text and f"{canonical}:" not in text:
            return False
    return True


def finalize_chapter(
    novel_number: int,
    word_number: int,
    api_key: str,
    base_url: str,
    model_name: str,
    temperature: float,
    filepath: str,
    embedding_api_key: str,
    embedding_url: str,
    embedding_interface_format: str,
    embedding_model_name: str,
    interface_format: str,
    max_tokens: int,
    timeout: int = 600
):
    """
    对指定章节做最终处理：更新前文摘要、更新角色状态、插入向量库等。
    默认无需再做扩写操作，若有需要可在外部调用 enrich_chapter_text 处理后再定稿。
    """
    chapters_dir = os.path.join(filepath, "chapters")
    chapter_file = os.path.join(chapters_dir, f"chapter_{novel_number}.txt")
    chapter_text = read_file(chapter_file).strip()
    if not chapter_text:
        logging.warning(f"Chapter {novel_number} is empty, cannot finalize.")
        return

    global_summary_file = os.path.join(filepath, "global_summary.txt")
    old_global_summary = read_file(global_summary_file)
    character_state_file = os.path.join(filepath, "character_state.txt")
    old_character_state = read_file(character_state_file)
    protagonist_name = ""

    try:
        from novel_generator.chapter import extract_protagonist_info
        protagonist_info = extract_protagonist_info(filepath)
        protagonist_name = str(protagonist_info.get('protagonist_name', '')).strip()
        if protagonist_name == '（未指定）':
            protagonist_name = ""
    except Exception as e:
        logging.debug(f"主角信息提取失败，跳过强校验: {e}")

    llm_adapter = create_llm_adapter(
        interface_format=interface_format,
        base_url=base_url,
        model_name=model_name,
        api_key=api_key,
        temperature=temperature,
        max_tokens=max_tokens,
        timeout=timeout
    )

    prompt_summary = summary_prompt.format(
        chapter_text=chapter_text,
        global_summary=old_global_summary
    )
    new_global_summary = invoke_with_cleaning(llm_adapter, prompt_summary)
    if not new_global_summary.strip():
        new_global_summary = old_global_summary
    else:
        # 验证并清理摘要，防止重复累积
        new_global_summary = _validate_and_clean_summary(new_global_summary, max_length=4000)
    new_global_summary = _normalize_protagonist_name_drift(new_global_summary, protagonist_name)
    if not _summary_is_valid(new_global_summary, chapter_text, protagonist_name):
        logging.warning("摘要更新结果未通过校验，尝试一次强约束重试。")
        retry_summary_prompt = (
            prompt_summary
            + "\n\n⚠️ 你的上一版输出未通过校验："
              "必须包含章节中主角实名、禁止名字漂移、禁止出现“1”占位名。"
              "请重写并仅输出最终摘要。"
        )
        retry_summary = invoke_with_cleaning(llm_adapter, retry_summary_prompt)
        retry_summary = _validate_and_clean_summary(retry_summary, max_length=4000)
        retry_summary = _normalize_protagonist_name_drift(retry_summary, protagonist_name)
        if _summary_is_valid(retry_summary, chapter_text, protagonist_name):
            new_global_summary = retry_summary
        elif old_global_summary.strip():
            logging.warning("摘要重试仍不合规，回退到旧摘要以避免污染。")
            new_global_summary = old_global_summary

    prompt_char_state = update_character_state_prompt.format(
        chapter_text=chapter_text,
        old_state=old_character_state
    )
    new_char_state = invoke_with_cleaning(llm_adapter, prompt_char_state)
    if not new_char_state.strip():
        new_char_state = old_character_state
    new_char_state = _normalize_protagonist_name_drift(new_char_state, protagonist_name)
    if not _character_state_is_valid(new_char_state, chapter_text, protagonist_name):
        logging.warning("角色状态更新结果未通过校验，尝试一次强约束重试。")
        retry_char_state_prompt = (
            prompt_char_state
            + "\n\n⚠️ 你的上一版输出未通过校验："
              "必须使用章节中的角色实名、主角名不可漂移、每个主要角色块必须包含“生死状态”字段。"
              "请重写并仅输出角色状态文本。"
        )
        retry_char_state = invoke_with_cleaning(llm_adapter, retry_char_state_prompt)
        retry_char_state = _normalize_protagonist_name_drift(retry_char_state, protagonist_name)
        if _character_state_is_valid(retry_char_state, chapter_text, protagonist_name):
            new_char_state = retry_char_state
        elif old_character_state.strip():
            logging.warning("角色状态重试仍不合规，回退到旧状态以避免污染。")
            new_char_state = old_character_state

    # 🔧 Fix 3.1b: 名字一致性后处理校验
    # 从架构文件提取主角名，检测摘要/角色状态中是否出现名字互换
    try:
        if protagonist_name and protagonist_name != '（未指定）':
            # 检测主角名是否在新摘要中出现（应该出现）
            if protagonist_name not in new_global_summary and len(new_global_summary) > 100:
                logging.warning(
                    f"⚠️ 名字一致性警告: 主角'{protagonist_name}'未出现在新摘要中，"
                    f"可能发生了名字漂移。请检查global_summary.txt"
                )
            if protagonist_name not in new_char_state and len(new_char_state) > 100:
                logging.warning(
                    f"⚠️ 名字一致性警告: 主角'{protagonist_name}'未出现在角色状态中，"
                    f"可能发生了名字漂移。请检查character_state.txt"
                )
    except Exception as e:
        logging.debug(f"名字一致性校验跳过: {e}")

    world_state = _refresh_runtime_state_artifacts(
        filepath=filepath,
        chapter_text=chapter_text,
        chapter_number=novel_number,
        llm_adapter=llm_adapter,
        protagonist_name=protagonist_name,
    )

    story_state_facade = GenerationStateFacade(filepath)
    story_state_facade.commit_chapter_state(
        chapter_number=novel_number,
        chapter_text=chapter_text,
        global_summary_text=new_global_summary,
        character_state_text=new_char_state,
        chapter_summary=_build_chapter_summary(chapter_text),
        world_state=world_state,
        metadata={
            "target_word_count": word_number,
            "actual_word_count": count_chapter_words(chapter_text),
        },
    )

    update_vector_store(
        embedding_adapter=create_embedding_adapter(
            embedding_interface_format,
            embedding_api_key,
            embedding_url,
            embedding_model_name
        ),
        new_chapter=chapter_text,
        filepath=filepath
    )

    logging.info(f"Chapter {novel_number} has been finalized.")


def _refresh_runtime_state_artifacts(
    *,
    filepath: str,
    chapter_text: str,
    chapter_number: int,
    llm_adapter,
    protagonist_name: str,
) -> dict[str, Any]:
    world_state: dict[str, Any] = {}

    try:
        state_manager = WorldStateManager(filepath)
        state_path = getattr(state_manager, "state_path", "")
        if state_path and not os.path.exists(state_path) and hasattr(state_manager, "initialize_state"):
            initial_name = protagonist_name or "Protagonist"
            state_manager.initialize_state("", initial_name)
        state_manager.update_state_from_chapter(chapter_text, llm_adapter)
        world_state = dict(getattr(state_manager, "state", {}) or {})
    except Exception as e:
        logging.warning(f"World state refresh failed during finalization: {e}")

    try:
        hook_tracker = HookTracker(filepath)
        hook_tracker.check_resolutions(chapter_text, chapter_number)
        hook_tracker.register_hooks(chapter_text, chapter_number)
    except Exception as e:
        logging.warning(f"Hook tracker refresh failed during finalization: {e}")

    try:
        thread_tracker = NarrativeThreadTracker(filepath)
        thread_tracker.update_threads(chapter_text, chapter_number)
    except Exception as e:
        logging.warning(f"Narrative thread refresh failed during finalization: {e}")

    try:
        timeline_manager = TimelineManager(filepath)
        timeline_manager.update_timeline(chapter_text, chapter_number)
    except Exception as e:
        logging.warning(f"Timeline refresh failed during finalization: {e}")

    return world_state

def enrich_chapter_text(
    chapter_text: str,
    word_number: int,
    api_key: str,
    base_url: str,
    model_name: str,
    temperature: float,
    interface_format: str,
    max_tokens: int,
    timeout: int=600
) -> str:
    """
    对章节文本进行扩写，使其更接近 word_number 字数，保持剧情连贯。
    修复版本：保留章节标题格式，只扩写内容部分。
    """
    # 🔧 关键修复：分离标题和内容，保留标题格式
    try:
        from chapter_title_utils import add_chapter_title_if_missing, format_chapter_title_line
        import re

        # 尝试提取章节编号和标题
        lines = chapter_text.split('\n')
        title_line = lines[0].strip() if lines else ""
        title_pattern = r'^第(\d+)章\s+(.+)'
        title_match = re.match(title_pattern, title_line)

        if title_match:
            # 有标题的情况
            chapter_number = int(title_match.group(1))
            chapter_title = title_match.group(2)

            # 分离标题和内容
            content_lines = []
            for i, line in enumerate(lines):
                if i > 0:  # 跳过标题行
                    if line.strip():  # 跳过开头的空行
                        content_lines.append(line)
                elif i > 1:  # 如果不是第二个空行，就保留
                    content_lines.append(line)

            content_only = '\n'.join(content_lines).strip()

            if not content_only:
                return chapter_text  # 如果没有内容，返回原文

        else:
            # 没有标题的情况，直接处理全部内容
            content_only = chapter_text
            chapter_number = None
            chapter_title = None

        # 只对内容部分进行扩写
        llm_adapter = create_llm_adapter(
            interface_format=interface_format,
            base_url=base_url,
            model_name=model_name,
            api_key=api_key,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout
        )

        prompt = f"""以下章节文本较短，请在保持剧情连贯的前提下进行扩写，使其更充实，接近 {word_number} 字左右，仅给出最终文本，不要解释任何内容。

原内容：
{content_only}
"""
        enriched_content = invoke_with_cleaning(llm_adapter, prompt)
        enriched_content = enriched_content if enriched_content else content_only

        # 🔧 重新组合标题和扩写后的内容
        if chapter_number and chapter_title:
            # 使用工具函数确保标题格式正确
            from chapter_title_utils import format_chapter_title_line
            title_line = format_chapter_title_line(chapter_number, chapter_title)
            return f"{title_line}\n\n{enriched_content.strip()}"
        else:
            # 没有标题的情况，直接返回扩写内容
            return enriched_content

    except Exception as e:
        # 如果处理失败，记录错误并返回原始内容
        import logging
        logging.error(f"Error in enrich_chapter_text (title preservation): {str(e)}")
        return chapter_text


# ============================================================
# 🆕 真正的精校函数 - 对文章内容进行润色优化
# ============================================================

def polish_chapter_content(
    chapter_text: str,
    api_key: str,
    base_url: str,
    model_name: str,
    temperature: float = 0.5,
    interface_format: str = "openai",
    max_tokens: int = 8000,
    timeout: int = 600
) -> str:
    """
    对章节内容进行真正的精校润色
    
    Args:
        chapter_text: 原始章节内容
        api_key: API密钥
        base_url: API基础URL
        model_name: 模型名称
        temperature: 温度（精校时建议较低，如0.5）
        interface_format: 接口格式
        max_tokens: 最大token数
        timeout: 超时时间
    
    Returns:
        精校后的章节内容
    """
    if not chapter_text or len(chapter_text.strip()) < 100:
        return chapter_text
    
    llm_adapter = create_llm_adapter(
        interface_format=interface_format,
        base_url=base_url,
        model_name=model_name,
        api_key=api_key,
        temperature=temperature,
        max_tokens=max_tokens,
        timeout=timeout
    )
    current_length = int(count_chapter_words(chapter_text)['chinese_chars'])
    
    prompt = f"""你是一位资深网文编辑，请对以下章节进行【精校润色】。

【字数控制】⚠️ 重要
- 原文中文(Chinese Words): {current_length}
- 精校后字数必须保持在 {int(current_length * 0.95)}~{int(current_length * 1.05)} 字之间
- 精校是润色，不是扩写！不要增加内容！

【精校要求】
1. **修正病句**：检查并修正语法错误、用词不当
2. **润色措辞**：优化生硬的表达，使行文更流畅
3. **格式规范**：
   - 确保对话使用中文引号「」或""
   - 段落分隔合理，不要过长或过短
   - 标点符号使用正确
4. **错别字修正**：检查并修正错别字
5. **风格统一**：确保全文语言风格一致
6. **保持原意**：不要改变剧情内容和人物关系

【严格禁止】
- 不要增加任何新内容
- 不要扩写任何段落
- 不要删减任何剧情内容
- 不要改变故事走向
- 不要添加新的情节
- 不要改变人物性格

【原始章节】
{chapter_text}

请直接输出精校后的完整章节内容（保留原有标题格式，字数保持不变）：
"""
    
    try:
        polished = invoke_with_cleaning(llm_adapter, prompt)
        
        # 检查字数变化
        if polished:
            polished_stats = count_chapter_words(polished)
            polished_len = int(polished_stats['chinese_chars'])
            polished_total_len = int(polished_stats['all_chars'])
            change_ratio = polished_len / current_length if current_length > 0 else 1.0
            
            if polished_len < current_length * 0.7:
                logging.warning(f"精校结果异常（长度不足 {polished_len} < {current_length}*0.7），保留原文")
                return chapter_text
            elif polished_len > current_length * 1.2:
                logging.warning(f"精校结果字数过多({polished_len} > {current_length}*1.2)，保留原文")
                return chapter_text
            else:
                logging.info(f"精校完成: {current_length}字 -> {polished_len}字 (变化{(change_ratio-1)*100:+.1f}%)")
                return polished
        else:
            logging.warning(f"精校结果为空，保留原文")
            return chapter_text
            
    except Exception as e:
        logging.error(f"精校失败: {e}")
        return chapter_text


# ============================================================
# 重命名别名：finalize_chapter → update_context_data
# ============================================================

def update_context_data(
    novel_number: int,
    word_number: int,
    api_key: str,
    base_url: str,
    model_name: str,
    temperature: float,
    filepath: str,
    embedding_api_key: str,
    embedding_url: str,
    embedding_interface_format: str,
    embedding_model_name: str,
    interface_format: str,
    max_tokens: int,
    timeout: int = 600
):
    """
    更新上下文资料（原finalize_chapter的真实功能）
    - 更新全局摘要
    - 更新角色状态
    - 更新向量库
    """
    # 直接调用finalize_chapter（保持向后兼容）
    return finalize_chapter(
        novel_number=novel_number,
        word_number=word_number,
        api_key=api_key,
        base_url=base_url,
        model_name=model_name,
        temperature=temperature,
        filepath=filepath,
        embedding_api_key=embedding_api_key,
        embedding_url=embedding_url,
        embedding_interface_format=embedding_interface_format,
        embedding_model_name=embedding_model_name,
        interface_format=interface_format,
        max_tokens=max_tokens,
        timeout=timeout
    )
