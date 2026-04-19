# chapter_blueprint_parser.py
# -*- coding: utf-8 -*-
import re

def parse_chapter_blueprint(blueprint_text: str):
    """
    Parses the entire chapter blueprint text and returns a list of dictionaries.
    """

    # Split into chunks by empty lines
    chunks = re.split(r'\n\s*\n', blueprint_text.strip())
    results = []

    # Match chapter number and title
    chapter_number_pattern = re.compile(r'^Chapter\s*(\d+)\s*-\s*\[?(.*?)\]?$', re.IGNORECASE)

    role_pattern      = re.compile(r'^Chapter (?:Role|Position)[::]?\s*\[?(.*)\]?$', re.IGNORECASE)
    purpose_pattern   = re.compile(r'^Core Purpose[::]?\s*\[?(.*)\]?$', re.IGNORECASE)
    suspense_pattern  = re.compile(r'^Suspense (?:Density|Level)[::]?\s*\[?(.*)\]?$', re.IGNORECASE)
    foreshadow_pattern = re.compile(r'^Foreshadowing[::]?\s*\[?(.*)\]?$', re.IGNORECASE)
    twist_pattern     = re.compile(r'^Plot Twist Level[::]?\s*\[?(.*)\]?$', re.IGNORECASE)
    summary_pattern   = re.compile(r'^Chapter Summary[::]?\s*\[?(.*)\]?$', re.IGNORECASE)

    for chunk in chunks:
        lines = chunk.strip().splitlines()
        if not lines:
            continue

        chapter_number   = None
        chapter_title    = ""
        chapter_role     = ""
        chapter_purpose  = ""
        suspense_level   = ""
        foreshadowing    = ""
        plot_twist_level = ""
        chapter_summary  = ""

        header_match = chapter_number_pattern.match(lines[0].strip())
        if not header_match:
            continue

        chapter_number = int(header_match.group(1))
        chapter_title  = header_match.group(2).strip()

        for line in lines[1:]:
            line_stripped = line.strip()
            if not line_stripped:
                continue

            m_role = role_pattern.match(line_stripped)
            if m_role:
                chapter_role = m_role.group(1).strip()
                continue

            m_purpose = purpose_pattern.match(line_stripped)
            if m_purpose:
                chapter_purpose = m_purpose.group(1).strip()
                continue

            m_suspense = suspense_pattern.match(line_stripped)
            if m_suspense:
                suspense_level = m_suspense.group(1).strip()
                continue

            m_foreshadow = foreshadow_pattern.match(line_stripped)
            if m_foreshadow:
                foreshadowing = m_foreshadow.group(1).strip()
                continue

            m_twist = twist_pattern.match(line_stripped)
            if m_twist:
                plot_twist_level = m_twist.group(1).strip()
                continue

            m_summary = summary_pattern.match(line_stripped)
            if m_summary:
                chapter_summary = m_summary.group(1).strip()
                continue

        results.append({
            "chapter_number": chapter_number,
            "chapter_title": chapter_title,
            "chapter_role": chapter_role,
            "chapter_purpose": chapter_purpose,
            "suspense_level": suspense_level,
            "foreshadowing": foreshadowing,
            "plot_twist_level": plot_twist_level,
            "chapter_summary": chapter_summary
        })

    results.sort(key=lambda x: x["chapter_number"])
    return results

def get_chapter_info_from_blueprint(blueprint_text: str, target_chapter_number: int):
    all_chapters = parse_chapter_blueprint(blueprint_text)
    for ch in all_chapters:
        if ch["chapter_number"] == target_chapter_number:
            return ch
    return {
        "chapter_number": target_chapter_number,
        "chapter_title": f"Chapter {target_chapter_number}",
        "chapter_role": "",
        "chapter_purpose": "",
        "suspense_level": "",
        "foreshadowing": "",
        "plot_twist_level": "",
        "chapter_summary": ""
    }
