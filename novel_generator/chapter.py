# novel_generator/chapter.py
# -*- coding: utf-8 -*-
"""
Chapter draft generation and retrieval of historical chapters, current chapter summaries, etc.
"""
import os
import json
import logging
import re
from llm_adapters import create_llm_adapter
from prompt_definitions import (
    first_chapter_draft_prompt, 
    next_chapter_draft_prompt, 
    summarize_recent_chapters_prompt,
    knowledge_filter_prompt,
    knowledge_search_prompt
)
from chapter_directory_parser import get_chapter_info_from_blueprint
from novel_generator.common import invoke_with_cleaning
from utils import read_file, clear_file_content, save_string_to_txt
from novel_generator.vectorstore_utils import (
    get_relevant_context_from_vector_store,
    load_vector_store
)

logging.basicConfig(
    filename='app.log',
    filemode='a',
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

def get_last_n_chapters_text(chapters_dir: str, current_chapter_num: int, n: int = 3) -> list:
    """
    Retrieves the text content of the last n chapters from the chapters_dir.
    """
    texts = []
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
    chapters_text_list: list,
    novel_number: int,
    chapter_info: dict,
    next_chapter_info: dict,
    timeout: int = 600
) -> str:
    """
    Generates a precise summary for the current chapter based on the previous three chapters.
    Returns an empty string if parsing fails.
    """
    try:
        combined_text = "\n".join(chapters_text_list).strip()
        if not combined_text:
            return ""
            
        # Limit combined text length
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
        
        # Ensure all parameters have default values
        chapter_info = chapter_info or {}
        next_chapter_info = next_chapter_info or {}
        
        prompt = summarize_recent_chapters_prompt.format(
            combined_text=combined_text,
            novel_number=novel_number,
            chapter_title=chapter_info.get("chapter_title", "Untitled"),
            chapter_role=chapter_info.get("chapter_role", "Regular Chapter"),
            chapter_purpose=chapter_info.get("chapter_purpose", "Content Progression"),
            suspense_level=chapter_info.get("suspense_level", "Medium"),
            foreshadowing=chapter_info.get("foreshadowing", "None"),
            plot_twist_level=chapter_info.get("plot_twist_level", "1/5"),
            chapter_summary=chapter_info.get("chapter_summary", ""),
            next_chapter_number=novel_number + 1,
            next_chapter_title=next_chapter_info.get("chapter_title", "Untitled"),
            next_chapter_role=next_chapter_info.get("chapter_role", "Transition Chapter"),
            next_chapter_purpose=next_chapter_info.get("chapter_purpose", "Connecting Plot"),
            next_chapter_summary=next_chapter_info.get("chapter_summary", "Transition content"),
            next_chapter_suspense_level=next_chapter_info.get("suspense_level", "Medium"),
            next_chapter_foreshadowing=next_chapter_info.get("foreshadowing", "No specific foreshadowing"),
            next_chapter_plot_twist_level=next_chapter_info.get("plot_twist_level", "1/5")
        )
        
        response_text = invoke_with_cleaning(llm_adapter, prompt)
        summary = extract_summary_from_response(response_text)
        
        if not summary:
            logging.warning("Failed to extract summary, using full response")
            return response_text[:2000]
            
        return summary[:2000]
        
    except Exception as e:
        logging.error(f"Error in summarize_recent_chapters: {str(e)}")
        return ""

def extract_summary_from_response(response_text: str) -> str:
    """Extracts the summary part from the response text."""
    if not response_text:
        return ""
        
    # Look for summary markers
    summary_markers = [
        "Current Chapter Summary:",
        "Chapter Summary:",
        "Summary:"
    ]
    
    for marker in summary_markers:
        if (marker in response_text):
            parts = response_text.split(marker, 1)
            if len(parts) > 1:
                return parts[1].strip()
    
    return response_text.strip()

def format_chapter_info(chapter_info: dict) -> str:
    """Formats the chapter info dictionary into text."""
    template = """
Chapter Number: {number}
Chapter Title: "{title}"
Chapter Position: {role}
Core Purpose: {purpose}
Major Characters: {characters}
Key Items: {items}
Scene Location: {location}
Foreshadowing: {foreshadow}
Suspense Density: {suspense}
Plot Twist Level: {twist}
Chapter Summary: {summary}
"""
    return template.format(
        number=chapter_info.get('chapter_number', 'Unknown'),
        title=chapter_info.get('chapter_title', 'Unknown'),
        role=chapter_info.get('chapter_role', 'Unknown'),
        purpose=chapter_info.get('chapter_purpose', 'Unknown'),
        characters=chapter_info.get('characters_involved', 'Not specified'),
        items=chapter_info.get('key_items', 'Not specified'),
        location=chapter_info.get('scene_location', 'Not specified'),
        foreshadow=chapter_info.get('foreshadowing', 'None'),
        suspense=chapter_info.get('suspense_level', 'Medium'),
        twist=chapter_info.get('plot_twist_level', '1/5'),
        summary=chapter_info.get('chapter_summary', 'Not provided')
    )

def parse_search_keywords(response_text: str) -> list:
    """Parses the search keyword format."""
    return [
        line.strip()
        for line in response_text.strip().split('\n')
        if line.strip()
    ][:5]

def apply_content_rules(texts: list, novel_number: int) -> list:
    """Applies content processing rules to retrieved texts."""
    processed = []
    for text in texts:
        # Detect chapter references
        match = re.search(r'Chapter\s*(\d+)', text, re.IGNORECASE)
        if match or re.search(r'chapter_[\d]+', text):
            chap_nums = list(map(int, re.findall(r'\d+', text)))
            recent_chap = max(chap_nums) if chap_nums else 0
            time_distance = novel_number - recent_chap
            
            if time_distance <= 2:
                processed.append(f"[SKIP] Skipping recent chapter content: {text[:120]}...")
            elif 3 <= time_distance <= 5:
                processed.append(f"[MOD40%] {text} (Requires >= 40% modification)")
            else:
                processed.append(f"[OK] {text} (Core can be referenced)")
        else:
            processed.append(f"[PRIOR] {text} (Priority use)")
    return processed

def apply_knowledge_rules(contexts: list, chapter_num: int) -> list:
    """Applies usage rules for knowledge base content."""
    processed = []
    for text in contexts:
        # Detect historical chapter content
        if "Chapter" in text:
            chap_nums = [int(s) for s in re.findall(r'\d+', text)]
            recent_chap = max(chap_nums) if chap_nums else 0
            time_distance = chapter_num - recent_chap
            
            if time_distance <= 3:
                processed.append(f"[LIMIT] Skipping recent content: {text[:50]}...")
                continue
                
            processed.append(f"[REF] {text} (Requires >30% rewrite)")
        else:
            processed.append(f"[EXTERNAL] {text}")
    return processed

def get_filtered_knowledge_context(
    api_key: str,
    base_url: str,
    model_name: str,
    interface_format: str,
    embedding_adapter,
    filepath: str,
    chapter_info: dict,
    retrieved_texts: list,
    max_tokens: int = 2048,
    timeout: int = 600
) -> str:
    """Optimized knowledge filtering process."""
    if not retrieved_texts:
        return "(No relevant knowledge base content)"

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
        
        # Limit retrieval text length and format
        formatted_texts = []
        max_text_length = 600
        for i, text in enumerate(processed_texts, 1):
            if len(text) > max_text_length:
                text = text[:max_text_length] + "..."
            formatted_texts.append(f"[Preprocessing Result {i}]\n{text}")

        # Format chapter info for filtering
        formatted_chapter_info = (
            f"Chapter Position: {chapter_info.get('chapter_role', '')}\n"
            f"Core Target: {chapter_info.get('chapter_purpose', '')}\n"
            f"Key Elements: {chapter_info.get('characters_involved', '')} | "
            f"{chapter_info.get('key_items', '')} | "
            f"{chapter_info.get('scene_location', '')}"
        )

        prompt = knowledge_filter_prompt.format(
            chapter_info=formatted_chapter_info,
            retrieved_texts="\n\n".join(formatted_texts) if formatted_texts else "(No retrieval results)"
        )
        
        filtered_content = invoke_with_cleaning(llm_adapter, prompt)
        return filtered_content if filtered_content else "(Content filtering failed)"
        
    except Exception as e:
        logging.error(f"Error in knowledge filtering: {str(e)}")
        return "(Error during content filtering process)"

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
    timeout: int = 600
) -> str:
    """
    Constructs the request prompt for the current chapter.
    """
    # Read base files
    arch_file = os.path.join(filepath, "Novel_architecture.txt")
    novel_architecture_text = read_file(arch_file)
    directory_file = os.path.join(filepath, "Novel_directory.txt")
    blueprint_text = read_file(directory_file)
    global_summary_file = os.path.join(filepath, "global_summary.txt")
    global_summary_text = read_file(global_summary_file)
    character_state_file = os.path.join(filepath, "character_state.txt")
    character_state_text = read_file(character_state_file)
    
    # Get chapter info
    chapter_info = get_chapter_info_from_blueprint(blueprint_text, novel_number)
    chapter_title = chapter_info["chapter_title"]
    chapter_role = chapter_info["chapter_role"]
    chapter_purpose = chapter_info["chapter_purpose"]
    suspense_level = chapter_info["suspense_level"]
    foreshadowing = chapter_info["foreshadowing"]
    plot_twist_level = chapter_info["plot_twist_level"]
    chapter_summary = chapter_info["chapter_summary"]

    # Get next chapter info
    next_chapter_number = novel_number + 1
    next_chapter_info = get_chapter_info_from_blueprint(blueprint_text, next_chapter_number)
    next_chapter_title = next_chapter_info.get("chapter_title", "Untitled")
    next_chapter_role = next_chapter_info.get("chapter_role", "Transition Chapter")
    next_chapter_purpose = next_chapter_info.get("chapter_purpose", "Connecting Plot")
    next_chapter_suspense = next_chapter_info.get("suspense_level", "Medium")
    next_chapter_foreshadow = next_chapter_info.get("foreshadowing", "No specific foreshadowing")
    next_chapter_twist = next_chapter_info.get("plot_twist_level", "1/5")
    next_chapter_summary = next_chapter_info.get("chapter_summary", "Transition content")

    # Create chapters directory
    chapters_dir = os.path.join(filepath, "chapters")
    os.makedirs(chapters_dir, exist_ok=True)

    # Special handling for the first chapter
    if novel_number == 1:
        return first_chapter_draft_prompt.format(
            novel_number=novel_number,
            word_number=word_number,
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
            novel_setting=novel_architecture_text
        )

    # Get recent context and summary
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
        short_summary = "(Summary generation failed)"

    # Get excerpt from the previous chapter
    previous_excerpt = ""
    for text in reversed(recent_texts):
        if text.strip():
            previous_excerpt = text[-800:] if len(text) > 800 else text
            break

    # Knowledge base retrieval and processing
    try:
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
            scene_location=scene_loc,
            chapter_role=chapter_role,
            chapter_purpose=chapter_purpose,
            foreshadowing=foreshadowing,
            short_summary=short_summary,
            user_guidance=user_guidance,
            time_constraint=time_constraint
        )
        
        search_response = invoke_with_cleaning(llm_adapter, search_prompt)
        keyword_groups = search_response.strip().split('\n')[:5]

        all_contexts = []
        from embedding_adapters import create_embedding_adapter
        embedding_adapter = create_embedding_adapter(
            embedding_interface_format,
            embedding_api_key,
            embedding_url,
            embedding_model_name
        )
        
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
                    if any(kw in group.lower() for kw in ["technique", "method", "template"]):
                        all_contexts.append(f"[TECHNIQUE] {context}")
                    elif any(kw in group.lower() for kw in ["setting", "tech", "worldbuilding"]):
                        all_contexts.append(f"[SETTING] {context}")
                    else:
                        all_contexts.append(f"[GENERAL] {context}")

        processed_contexts = apply_content_rules(all_contexts, novel_number)
        
        chapter_info_for_filter = {
            "chapter_number": novel_number,
            "chapter_title": chapter_title,
            "chapter_role": chapter_role,
            "chapter_purpose": chapter_purpose,
            "characters_involved": characters_involved,
            "key_items": key_items,
            "scene_location": scene_location,
            "foreshadowing": foreshadowing,
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
        logging.error(f"Knowledge processing error: {str(e)}")
        filtered_context = "(Knowledge base processing failed)"

    # Final prompt
    return next_chapter_draft_prompt.format(
        user_guidance=user_guidance if user_guidance else "No specific guidance",
        global_summary=global_summary_text,
        previous_chapter_excerpt=previous_excerpt,
        character_state=character_state_text,
        short_summary=short_summary,
        novel_number=novel_number,
        chapter_title=chapter_title,
        chapter_role=chapter_role,
        chapter_purpose=chapter_purpose,
        suspense_level=suspense_level,
        foreshadowing=foreshadowing,
        plot_twist_level=plot_twist_level,
        chapter_summary=chapter_summary,
        word_number=word_number,
        characters_involved=characters_involved,
        key_items=key_items,
        scene_location=scene_location,
        time_constraint=time_constraint,
        next_chapter_number=next_chapter_number,
        next_chapter_title=next_chapter_title,
        next_chapter_role=next_chapter_role,
        next_chapter_purpose=next_chapter_purpose,
        next_chapter_suspense_level=next_chapter_suspense,
        next_chapter_foreshadowing=next_chapter_foreshadow,
        next_chapter_plot_twist_level=next_chapter_twist,
        next_chapter_summary=next_chapter_summary,
        filtered_context=filtered_context
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
    embedding_retrieval_k: int = 2,
    interface_format: str = "openai",
    max_tokens: int = 2048,
    timeout: int = 600,
    custom_prompt_text: str = None
) -> str:
    """
    Generates a chapter draft, supporting custom prompt text.
    """
    if custom_prompt_text is None:
        prompt_text = build_chapter_prompt(
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
            timeout=timeout
        )
    else:
        prompt_text = custom_prompt_text

    chapters_dir = os.path.join(filepath, "chapters")
    os.makedirs(chapters_dir, exist_ok=True)

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
    if not chapter_content.strip():
        logging.warning("Generated chapter draft is empty.")
    chapter_file = os.path.join(chapters_dir, f"chapter_{novel_number}.txt")
    clear_file_content(chapter_file)
    save_string_to_txt(chapter_content, chapter_file)
    logging.info(f"[Draft] Chapter {novel_number} generated as a draft.")
    return chapter_content
