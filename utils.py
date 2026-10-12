# utils.py
# -*- coding: utf-8 -*-
import os
import json

def read_file(filename: str) -> str:
    """读取文件的全部内容，若文件不存在或异常则返回空字符串。"""
    try:
        with open(filename, 'r', encoding='utf-8') as file:
            content = file.read()
        return content
    except FileNotFoundError:
        return ""
    except Exception as e:
        print(f"[read_file] 读取文件时发生错误: {e}")
        return ""

def append_text_to_file(text_to_append: str, file_path: str):
    """在文件末尾追加文本(带换行)。若文本非空且无换行，则自动加换行。"""
    if text_to_append and not text_to_append.startswith('\n'):
        text_to_append = '\n' + text_to_append

    try:
        with open(file_path, 'a', encoding='utf-8') as file:
            file.write(text_to_append)
    except IOError as e:
        print(f"[append_text_to_file] 发生错误：{e}")

def clear_file_content(filename: str):
    """清空指定文件内容。"""
    try:
        with open(filename, 'w', encoding='utf-8') as file:
            pass
    except IOError as e:
        print(f"[clear_file_content] 无法清空文件 '{filename}' 的内容：{e}")

def save_string_to_txt(content: str, filename: str):
    """将字符串保存为 txt 文件（覆盖写）。"""
    try:
        with open(filename, 'w', encoding='utf-8') as file:
            file.write(content)
    except Exception as e:
        print(f"[save_string_to_txt] 保存文件时发生错误: {e}")

def save_data_to_json(data: dict, file_path: str) -> bool:
    """将数据保存到 JSON 文件。"""
    try:
        with open(file_path, 'w', encoding='utf-8') as json_file:
            json.dump(data, json_file, ensure_ascii=False, indent=4)
        return True
    except Exception as e:
        print(f"[save_data_to_json] 保存数据到JSON文件时出错: {e}")

def get_word_count(text: str) -> int:
    """
    根据 config_manager.IS_ENGLISH 计算字数。
    如果是英文模式，按单词（空格分隔）计算；
    如果是中文模式，按字符数计算。
    """
    try:
        import config_manager
        is_english = getattr(config_manager, 'IS_ENGLISH', False)
    except ImportError:
        is_english = False

    if not text:
        return 0
    if is_english:
        # 英文模式：按单词计算
        return len(text.split())
    else:
        # 中文模式：按字符计算
        return len(text)
