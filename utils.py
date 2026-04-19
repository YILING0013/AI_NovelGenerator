# utils.py
# -*- coding: utf-8 -*-
import os
import json

def read_file(filename: str) -> str:
    """Read the entire content of a file. Returns an empty string if the file does not exist or an error occurs."""
    try:
        with open(filename, 'r', encoding='utf-8') as file:
            content = file.read()
        return content
    except FileNotFoundError:
        return ""
    except Exception as e:
        print(f"[read_file] Error reading file: {e}")
        return ""

def append_text_to_file(text_to_append: str, file_path: str):
    """Append text to the end of a file (with a newline). If the text is not empty and has no newline, one is added automatically."""
    if text_to_append and not text_to_append.startswith('\n'):
        text_to_append = '\n' + text_to_append

    try:
        with open(file_path, 'a', encoding='utf-8') as file:
            file.write(text_to_append)
    except IOError as e:
        print(f"[append_text_to_file] Error occurred: {e}")

def clear_file_content(filename: str):
    """Clear the content of the specified file."""
    try:
        with open(filename, 'w', encoding='utf-8') as file:
            pass
    except IOError as e:
        print(f"[clear_file_content] Unable to clear file '{filename}': {e}")

def save_string_to_txt(content: str, filename: str):
    """Save a string as a txt file (overwrites existing content)."""
    try:
        with open(filename, 'w', encoding='utf-8') as file:
            file.write(content)
    except Exception as e:
        print(f"[save_string_to_txt] Error saving file: {e}")

def save_data_to_json(data: dict, file_path: str) -> bool:
    """Save data to a JSON file."""
    try:
        with open(file_path, 'w', encoding='utf-8') as json_file:
            json.dump(data, json_file, ensure_ascii=False, indent=4)
        return True
    except Exception as e:
        print(f"[save_data_to_json] Error saving data to JSON file: {e}")
        return False
