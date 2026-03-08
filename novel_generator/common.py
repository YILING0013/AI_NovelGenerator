#novel_generator/common.py
# -*- coding: utf-8 -*-
"""
通用重试、清洗、日志工具
"""
import logging
import re
import time
import traceback
import sys
import os
import threading
import json
from datetime import datetime
from typing import Any, Dict, Optional
# 确保日志支持中文
logging.basicConfig(
    filename='app.log',      # 日志文件名
    filemode='a',            # 追加模式（'w' 会覆盖）
    level=logging.INFO,      # 记录 INFO 及以上级别的日志
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    encoding='utf-8'         # 设置编码为UTF-8
)

# 配置控制台输出也支持中文
if sys.platform.startswith('win'):
    # Windows平台配置
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

_LLM_LOG_CONTEXT = threading.local()
_RUNTIME_LOG_STAGE_CONTEXT = threading.local()
_RUNTIME_STAGE_PREFIX_MAP: Dict[str, str] = {
    "S1": "[S1]",
    "S2": "[S2]",
    "S3": "[S3]",
}
_RUNTIME_STAGE_PREFIX_RE = re.compile(r"^\[(S1|S2|S3)\](\s|$)")
_RUNTIME_STAGE_FILTER_LOCK = threading.Lock()
_RUNTIME_STAGE_FILTER_INSTALLED = False


def _normalize_runtime_log_stage(stage: Optional[str]) -> Optional[str]:
    if stage is None:
        return None
    normalized = str(stage).strip().upper()
    if not normalized:
        return None
    if normalized.startswith("[") and normalized.endswith("]"):
        normalized = normalized[1:-1].strip().upper()
    for stage_key in ("S1", "S2", "S3"):
        if normalized.startswith(stage_key):
            return stage_key
    return normalized


def set_runtime_log_stage(stage: Optional[str]) -> Optional[str]:
    """设置当前线程的运行阶段（用于 app.log 根日志打 [S1/S2/S3] 前缀）。"""
    normalized = _normalize_runtime_log_stage(stage)
    if normalized:
        _RUNTIME_LOG_STAGE_CONTEXT.value = normalized
    else:
        _RUNTIME_LOG_STAGE_CONTEXT.value = None
    return normalized


def get_runtime_log_stage() -> Optional[str]:
    """获取当前线程绑定的运行阶段。"""
    stage = getattr(_RUNTIME_LOG_STAGE_CONTEXT, "value", None)
    normalized = _normalize_runtime_log_stage(stage)
    return normalized


def clear_runtime_log_stage() -> None:
    """清理当前线程的运行阶段标记。"""
    _RUNTIME_LOG_STAGE_CONTEXT.value = None


class RuntimeStagePrefixFilter(logging.Filter):
    """为 root 日志自动附加 [S1/S2/S3] 阶段前缀（线程级）。"""

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: D401
        stage = get_runtime_log_stage()
        if not stage:
            return True

        prefix = _RUNTIME_STAGE_PREFIX_MAP.get(stage, f"[{stage}]")
        try:
            rendered_message = record.getMessage()
        except Exception:
            rendered_message = str(record.msg)

        if _RUNTIME_STAGE_PREFIX_RE.match(rendered_message):
            return True

        record.msg = f"{prefix} {rendered_message}"
        record.args = ()
        return True


def ensure_runtime_stage_log_filter_installed() -> None:
    """确保 root logger 已安装阶段前缀过滤器（幂等）。"""
    global _RUNTIME_STAGE_FILTER_INSTALLED
    if _RUNTIME_STAGE_FILTER_INSTALLED:
        return

    with _RUNTIME_STAGE_FILTER_LOCK:
        if _RUNTIME_STAGE_FILTER_INSTALLED:
            return
        root_logger = logging.getLogger()
        if not any(isinstance(item, RuntimeStagePrefixFilter) for item in root_logger.filters):
            root_logger.addFilter(RuntimeStagePrefixFilter())
        _RUNTIME_STAGE_FILTER_INSTALLED = True


ensure_runtime_stage_log_filter_installed()


def set_llm_log_context(
    *,
    project_path: Optional[str] = None,
    chapter_num: Optional[int] = None,
    stage: Optional[str] = None,
    model_name: Optional[str] = None,
    interface_format: Optional[str] = None,
    reset: bool = False,
) -> Dict[str, Any]:
    """设置当前线程的 LLM 日志上下文（按章节归档）。"""
    ctx = {} if reset else dict(getattr(_LLM_LOG_CONTEXT, "value", {}) or {})
    if project_path is not None:
        ctx["project_path"] = str(project_path).strip()
    if chapter_num is not None:
        try:
            ctx["chapter_num"] = int(chapter_num)
        except (TypeError, ValueError):
            pass
    if stage is not None:
        ctx["stage"] = str(stage).strip() or "generic"
    if model_name is not None:
        ctx["model_name"] = str(model_name).strip()
    if interface_format is not None:
        ctx["interface_format"] = str(interface_format).strip()
    _LLM_LOG_CONTEXT.value = ctx
    return dict(ctx)


def get_llm_log_context() -> Dict[str, Any]:
    """获取当前线程的 LLM 日志上下文。"""
    return dict(getattr(_LLM_LOG_CONTEXT, "value", {}) or {})


def clear_llm_log_context() -> None:
    """清理当前线程的 LLM 日志上下文。"""
    _LLM_LOG_CONTEXT.value = {}


def _sanitize_llm_log_stage(stage: str) -> str:
    normalized = re.sub(r"[^\w\-\u4e00-\u9fa5]+", "_", str(stage or "").strip()).strip("_")
    return normalized[:80] if normalized else "generic"


def write_llm_interaction_log(
    prompt: str,
    response: str,
    *,
    stage: Optional[str] = None,
    extra_meta: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    """
    将一次 LLM 交互写入当前章节目录。
    目录结构：<project>/llm_dialogues_by_chapter/chapter_<N>/
    """
    context = get_llm_log_context()
    project_path = str(context.get("project_path", "") or "").strip()
    chapter_num = context.get("chapter_num")
    if not project_path or chapter_num in (None, ""):
        return None

    try:
        chapter_id = int(chapter_num)
    except (TypeError, ValueError):
        return None

    stage_name = _sanitize_llm_log_stage(stage or context.get("stage", "generic"))
    chapter_dir = os.path.join(project_path, "llm_dialogues_by_chapter", f"chapter_{chapter_id}")
    os.makedirs(chapter_dir, exist_ok=True)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    log_path = os.path.join(chapter_dir, f"{ts}_{stage_name}.md")

    meta: Dict[str, Any] = {
        "time": datetime.now().isoformat(),
        "chapter": chapter_id,
        "stage": stage_name,
        "model_name": context.get("model_name", ""),
        "interface_format": context.get("interface_format", ""),
        "prompt_chars": len(prompt or ""),
        "response_chars": len(response or ""),
    }
    if isinstance(extra_meta, dict):
        meta.update(extra_meta)

    try:
        with open(log_path, "w", encoding="utf-8") as f:
            f.write(f"# Chapter {chapter_id} - LLM Interaction - {stage_name}\n\n")
            f.write("## Meta\n\n")
            for key, value in meta.items():
                f.write(f"- {key}: {value}\n")
            f.write("\n## Prompt\n\n```text\n")
            f.write(prompt or "")
            f.write("\n```\n\n## Response\n\n```text\n")
            f.write(response or "")
            f.write("\n```\n")
        return log_path
    except Exception as e:
        logging.warning(f"写入章节LLM交互日志失败: {e}")
        return None


def call_with_retry(func, max_retries=3, sleep_time=2, fallback_return=None, **kwargs):
    """
    通用的重试机制封装。
    :param func: 要执行的函数
    :param max_retries: 最大重试次数
    :param sleep_time: 重试前的等待秒数
    :param fallback_return: 如果多次重试仍失败时的返回值
    :param kwargs: 传给func的命名参数
    :return: func的结果，若失败则返回 fallback_return
    """
    for attempt in range(1, max_retries + 1):
        try:
            return func(**kwargs)
        except Exception as e:
            logging.warning(f"[call_with_retry] Attempt {attempt} failed with error: {e}")
            traceback.print_exc()
            if attempt < max_retries:
                time.sleep(sleep_time)
            else:
                logging.error("Max retries reached, returning fallback_return.")
                return fallback_return

def remove_think_tags(text: str) -> str:
    """移除 <think>...</think> 包裹的内容"""
    return re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)

def debug_log(prompt: str, response_content: str):
    logging.info(
        f"\n[#########################################  Prompt  #########################################]\n{prompt}\n"
    )
    logging.info(
        f"\n[######################################### Response #########################################]\n{response_content}\n"
    )

def invoke_with_cleaning(llm_adapter, prompt: str, max_retries: int = 3) -> str:
    """调用 LLM 并清理返回结果"""
    print("\n" + "="*50)
    print("发送到 LLM 的提示词:")
    print("-"*50)
    print(prompt)
    print("="*50 + "\n")
    
    result = ""
    retry_count = 0
    
    while retry_count < max_retries:
        try:
            raw_result = llm_adapter.invoke(prompt)
            result = raw_result
            print("\n" + "="*50)
            print("LLM 返回的内容:")
            print("-"*50)
            print(result)
            print("="*50 + "\n")

            write_llm_interaction_log(
                prompt=prompt,
                response=str(raw_result or ""),
                extra_meta={"attempt": retry_count + 1},
            )
            
            # 清理结果中的特殊格式标记
            result = result.replace("```", "").strip()
            
            # 🆕 清理LLM元叙事污染
            result = clean_llm_output(result)
            
            if result:
                return result
            retry_count += 1
            if retry_count < max_retries:
                wait_time = min(2 ** (retry_count - 1), 10)
                logging.warning(
                    f"LLM返回空内容，{wait_time}秒后重试 ({retry_count}/{max_retries})..."
                )
                time.sleep(wait_time)
        except Exception as e:
            print(f"调用失败 ({retry_count + 1}/{max_retries}): {str(e)}")
            retry_count += 1
            if retry_count >= max_retries:
                raise e
            wait_time = min(2 ** (retry_count - 1), 10)
            logging.warning(
                f"LLM调用异常，{wait_time}秒后重试 ({retry_count}/{max_retries}): {e}"
            )
            time.sleep(wait_time)
    
    return result


def extract_revised_text_payload(text: str) -> Optional[str]:
    """尽力从结构化回包中提取 revised_text（容忍半结构化/缺大括号输出）。"""
    source = str(text or "").strip()
    if not source:
        return None

    candidates: list[str] = []
    if "{" in source and "}" in source:
        candidates.append(source[source.find("{"):source.rfind("}") + 1])

    fence_pattern = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.IGNORECASE)
    for block in fence_pattern.findall(source):
        block = block.strip()
        if not block:
            continue
        if "{" in block and "}" in block:
            candidates.append(block[block.find("{"):block.rfind("}") + 1])
        elif re.match(r'^\s*"?(change_log|self_check|revised_text)"?\s*:', block):
            candidates.append("{" + block + "}")

    if re.match(r'^\s*"?(change_log|self_check|revised_text)"?\s*:', source):
        candidates.append("{" + source + "}")

    for candidate in candidates:
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            revised = payload.get("revised_text")
            if isinstance(revised, str) and len(revised.strip()) > 80:
                return revised.strip()

    quoted_match = re.search(r'"revised_text"\s*:\s*"((?:\\.|[^"\\])*)"', source, re.S)
    if quoted_match:
        raw_value = quoted_match.group(1)
        try:
            decoded = json.loads(f'"{raw_value}"')
        except json.JSONDecodeError:
            decoded = raw_value.replace("\\n", "\n").replace('\\"', '"')
        if isinstance(decoded, str) and len(decoded.strip()) > 80:
            return decoded.strip()

    plain_match = re.search(r'(?is)"?revised_text"?\s*[:：]\s*(.+)$', source)
    if plain_match:
        candidate_text = plain_match.group(1).strip()
        if candidate_text.startswith('"'):
            candidate_text = candidate_text[1:]
        candidate_text = candidate_text.rstrip(",").strip()
        if candidate_text.endswith('"'):
            candidate_text = candidate_text[:-1]
        if "\\n" in candidate_text:
            candidate_text = candidate_text.replace("\\n", "\n").replace('\\"', '"')
        if len(candidate_text) > 80:
            return candidate_text

    return None


def clean_llm_output(text: str) -> str:
    """
    清理LLM输出中的元叙事污染
    - 移除"好的，主编"等开场白
    - 移除分隔线
    - 移除markdown标题前的杂项
    """
    if not text:
        return text

    revised_payload = extract_revised_text_payload(text)
    if revised_payload:
        text = revised_payload

    # 常见的LLM元叙事前缀模式
    meta_patterns = [
        r'^好的[，,].*?[。\n]',  # "好的，主编。"
        r'^以下是.*?[：:\n]',    # "以下是重写后的内容："
        r'^根据.*?[，,].*?[。\n]',  # "根据您的要求，..."
        r'^我已.*?[。\n]',       # "我已仔细研读..."
        r'^我是.*?[。\n]',       # "我是小说蓝图架构..." (新增)
        r'^你好[，,].*?[。\n]',   # "你好，我是..."
        r'^这是.*?[：:\n]',      # "这是修改后的版本："
        r'^明白[，,].*?[。\n]',   # "明白，我来..."
        r'^收到[，,].*?[。\n]',   # "收到，..."
        r'^---+\s*\n',          # 分隔线
        # 🆕 新增更多废话模式
        r'^在审阅了.*?[。\n]',   # "在审阅了您的..."
        r'^经过.*?审阅.*?[。\n]', # "经过仔细审阅..."
        r'^我认为.*?[。\n]',     # "我认为整体..."
        r'^我的工作.*?[。\n]',   # "我的工作将聚焦于..."
        r'^整体叙事.*?[。\n]',   # "整体叙事节奏..."
        r'^非常感谢.*?[。\n]',   # "非常感谢您的信任..."
        r'^感谢您.*?[。\n]',     # "感谢您的耐心..."
        r'^您好.*?[。\n]',       # "您好，..."
        r'^尊敬的.*?[。\n]',     # "尊敬的用户..."
        r'^请看.*?[：:\n]',      # "请看以下内容："
        r'^下面是.*?[：:\n]',    # "下面是修改后的："
        r'^现在让我.*?[。\n]',   # "现在让我为您..."
        # 🆕 针对编辑反馈的特定模式
        r'^针对.*?[：:\n]',      # "针对您提出的..."
        r'^修正.*?[：:\n]',      # "修正说明："
        r'^优化.*?[：:\n]',      # "优化重点："
        r'^修改.*?[：:\n]',      # "修改理由："
        r'^本次.*?[：:\n]',      # "本次修改..."
        r'^关于.*?[：:\n]',      # "关于您提到的..."
        r'^Refining.*?[：:\n]', # "Refining the chapter..."
        r'^As requested.*?[,\n]', # "As requested..."
        # 🆕 针对数字列表形式的反馈（需谨慎，只匹配文件开头）
        r'^\d+\.\s+.*?\n',       # "1. xxxx"
        r'^\d+\、\s+.*?\n',      # "1、xxxx"
        r'^这一章.*?[。\n]',     # "这一章我优化了..."
        r'^我重点优化.*?[：:\n]', # "我重点优化了..."
        r'^在终润定稿中.*?[：:\n]', # "在终润定稿中..."
        r'^作为金牌编辑.*?[。\n]', # "作为金牌编辑..."
        r'^编辑手记\s*$',         # "编辑手记"
        r'^编辑修改精评\s*$',      # "编辑修改精评"
        # 🆕 移除 [Thinking] 思考过程块
        r'\[Thinking\].*?(\[\/Thinking\]|$)',
        r'(?s)\[Thinking\].*?(\[\/Thinking\]|$)',
        r'(?s)<Thinking>.*?(</Thinking>|$)',
        r'(?s)<thinking>.*?(</thinking>|$)',
        r'(?s)Step 1: 【思考】.*?Step 3: 【执行】',
        # 🆕 移除 "高光设计" / "设计思路" 块 
        r'(?s)### 高光设计.*?### 最终章节正文',
        r'(?s)高光设计.*?最终章节正文',
        r'(?s)设计思路.*?最终章节正文',
        r'(?s)画面描述.*?最终章节正文',
        r'(?s)^高光设计.*?(?=第\d+章)', # Remove from "高光设计" until next Chapter Title if "最终章节正文" is missing
        r'^高光设计.*?[：:\n]',
        r'^设计思路.*?[：:\n]',
        r'^画面描述.*?[：:\n]',
        r'^最终章节正文.*?[：:\n]',
    ]
    
    # 逐个匹配并移除
    for pattern in meta_patterns:
        # 使用 MULTILINE 模式匹配每一行
        text = re.sub(pattern, '', text, flags=re.MULTILINE)
    
    # 如果内容以markdown标题开头，确保它是第一行
    lines = text.strip().split('\n')
    clean_lines = []
    found_content = False
    
    for line in lines:
        stripped = line.strip()
        # 跳过空行直到找到实际内容
        if not found_content:
            if not stripped:
                continue
            # 如果是markdown标题或章节标题，这是有效内容的开始
            if stripped.startswith('#') or stripped.startswith('第') or stripped.startswith('**第'):
                found_content = True
                clean_lines.append(line)
            # 如果是纯文字开头（非元叙事），也是有效内容
            elif len(stripped) > 10 and not any(stripped.startswith(p) for p in ['好的', '以下', '根据', '我已', '这是', '明白', '收到', '---', '针对', '修正', '优化', '修改', '本次', '关于']):
                found_content = True
                clean_lines.append(line)
        else:
            clean_lines.append(line)
    
    result = '\n'.join(clean_lines).strip()
    
    # 🆕 清理markdown标题符号（如 ### 第3章 → 第3章）
    result = re.sub(r'^#{1,6}\s*', '', result, flags=re.MULTILINE)
    
    # 🆕 清理标题开头的**符号（如 **第51章 → 第51章）
    result = re.sub(r'^\*+\s*', '', result, flags=re.MULTILINE)
    
    # 🆕 清理正文中的markdown加粗符号（如 **文字** → 文字）
    result = re.sub(r'\*\*([^*]+)\*\*', r'\1', result)
    
    # 🆕 清理标题行末尾的markdown符号（如 第2章 xxx** → 第2章 xxx）
    lines = result.split('\n')
    for i, line in enumerate(lines):
        # 对所有包含"第X章"的行进行清理
        if re.match(r'^第\d+章', line):
            lines[i] = re.sub(r'[*#]+\s*$', '', line)  # 移除末尾的*和#符号
            lines[i] = re.sub(r'\*+', '', lines[i])     # 移除行中任意位置的*符号
    result = '\n'.join(lines)
    
    # 🆕 移除重复句子
    result = remove_duplicate_sentences(result)

    # 🆕 清理结构化回包残留行（JSON键名/孤立符号）
    result = re.sub(r'(?im)^\s*"?(change_log|self_check|revised_text)"?\s*:\s*.*$', '', result)
    result = re.sub(r'(?im)^\s*[\[\]\{\},]+\s*$', '', result)

    # 🆕 若输出保留了大量转义换行，做一次可读化恢复
    if result.count("\\n") >= 8 and result.count("\n") <= 4:
        result = result.replace("\\n", "\n").replace('\\"', '"')

    # 清理可能残留的尾部“编辑修改精评”附录
    appendix_markers = ("\n编辑修改精评", "\n### 编辑修改精评", "\n#### 编辑修改精评")
    for marker in appendix_markers:
        marker_idx = result.find(marker)
        if marker_idx > max(120, len(result) // 3):
            result = result[:marker_idx].rstrip()
            break

    # 压缩多余空行
    result = re.sub(r'\n{3,}', '\n\n', result).strip()

    # 🆕 检测修辞密度（仅警告，不修改）
    check_metaphor_density(result)
    
    return result


def remove_duplicate_sentences(text: str) -> str:
    """
    检测并移除文本中的重复句子
    - 如果两个句子的前20个字符相似度超过80%，移除后一个
    """
    if not text or len(text) < 100:
        return text
    
    # 按句号、感叹号、问号分割
    sentences = re.split(r'([。！？])', text)
    
    # 重组句子（保留标点）
    full_sentences = []
    for i in range(0, len(sentences) - 1, 2):
        if i + 1 < len(sentences):
            full_sentences.append(sentences[i] + sentences[i + 1])
        else:
            full_sentences.append(sentences[i])
    
    # 检测重复
    seen_keys = set()
    result_sentences = []
    
    for sentence in full_sentences:
        # 提取关键特征：去除常见虚词后的前30个字符
        clean_sentence = re.sub(r'[的了是在他她它这那个一]', '', sentence)
        key = clean_sentence[:30] if len(clean_sentence) > 30 else clean_sentence
        
        # 如果这个key已经出现过，跳过（去重）
        if key and len(key) > 10:
            if key in seen_keys:
                logging.info(f"[重复检测] 移除重复句子: {sentence[:30]}...")
                continue
            seen_keys.add(key)
        
        result_sentences.append(sentence)
    
    return ''.join(result_sentences)


def check_metaphor_density(text: str) -> None:
    """
    检测文本中的修辞密度，如果过高则记录警告日志
    - 单段落超过4个修辞标记词视为堆砌
    """
    if not text or len(text) < 200:
        return
    
    metaphor_markers = ['如同', '仿佛', '像是', '好似', '犹如', '宛如', '般的', '一般', '似的']
    paragraphs = text.split('\n\n')
    
    for i, para in enumerate(paragraphs):
        if len(para) < 50:  # 跳过短段落
            continue
        count = sum(para.count(m) for m in metaphor_markers)
        if count >= 3:  # 从4降低到3，更严格检测堆砌
            logging.warning(f"[修辞密度] 第{i+1}段检测到{count}处修辞词，可能存在堆砌问题")
