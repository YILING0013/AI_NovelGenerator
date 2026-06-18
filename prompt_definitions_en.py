# prompt_definitions.py
# -*- coding: utf-8 -*-
"""
Centralized storage for all prompts, integrating the Snowflake Writing Method, Character Arc Theory, the Three-Element Suspense Model, etc.
Also includes newly added prompts for summarizing the first three chapters / extracting keywords for the next chapter, as well as chapter body writing prompts.
"""

# =============== Draft Generation Prompts: Current Chapter Summary & Knowledge Base Extraction ===============
# Current chapter summary generation prompt
summarize_recent_chapters_prompt = """\
As a professional novel editor and knowledge management expert, you are generating a precise summary of the current chapter based on the completed content of the previous three chapters and the current chapter's information. Please strictly follow the workflow below:

Previous three chapters content:
{combined_text}

Current chapter information:
Chapter {novel_number} "{chapter_title}":
├── Chapter role: {chapter_role}
├── Core function: {chapter_purpose}
├── Suspense density: {suspense_level}
├── Foreshadowing: {foreshadowing}
├── Cognitive subversion: {plot_twist_level}
└── Chapter summary: {chapter_summary}

Next chapter information:
Chapter {next_chapter_number} "{next_chapter_title}":
├── Chapter role: {next_chapter_role}
├── Core function: {next_chapter_purpose}
├── Suspense density: {next_chapter_suspense_level}
├── Foreshadowing: {next_chapter_foreshadowing}
├── Cognitive subversion: {next_chapter_plot_twist_level}
└── Chapter summary: {next_chapter_summary}

**Contextual Analysis Phase**:
1. Review the core content of the previous three chapters:
   - Chapter 1 core elements: [chapter title] -> [core conflict/theory] -> [key characters/concepts]
   - Chapter 2 development path: [established character relationships] -> [technical/plot progression] -> [lingering foreshadowing]
   - Chapter 3 turning point: [newly introduced variables] -> [worldbuilding expansion] -> [unresolved issues]
2. Extract continuity elements:
   - Required inherited elements: list the 3 core settings from the previous 3 chapters that must be carried forward
   - Adjustable elements: identify 2 secondary settings that may undergo moderate changes

**Current Chapter Summary Generation Rules**:
1. Content architecture:
   - Inheritance weight: 70% of content must form a logical progression from the previous 3 chapters
   - Innovation space: 30% of content may introduce new elements, but must be labeled with the type of innovation (e.g., technological breakthrough / character corruption)
2. Structure control:
   - Use a three-part "Inheritance -> Development -> Setup" structure
   - Each part contains 1 callback to previous content + 1 new development
3. Warning mechanism:
   - If a conflict with the previous 3 chapters' settings is detected, mark it with [!] and explain
   - For open-ended development paths, provide 2 reasonable evolution directions

Based on the current story progress, please complete the following two tasks:
In at most 800 words, write a concise and clear "Current Chapter Summary";

Please output in the following format (no additional explanation needed):
Current Chapter Summary: <write the current chapter summary here>
"""

# Knowledge base search query generation prompt
knowledge_search_prompt = """\
Based on the following current writing requirements, generate appropriate knowledge base search keywords:

Chapter metadata:
- Preparing to write: Chapter {chapter_number}
- Chapter theme: {chapter_title}
- Core characters: {characters_involved}
- Key items: {key_items}
- Scene location: {scene_location}

Writing goals:
- Chapter role: {chapter_role}
- Core function: {chapter_purpose}
- Foreshadowing: {foreshadowing}

Current summary:
{short_summary}

- User guidance:
{user_guidance}

- Core characters (may not be specified): {characters_involved}
- Key items (may not be specified): {key_items}
- Spatial coordinates (may not be specified): {scene_location}
- Time pressure (may not be specified): {time_constraint}

Generation rules:

1. Keyword combination logic:
- Type 1: [entity] + [attribute] (e.g., "quantum computer malfunction log")
- Type 2: [event] + [consequence] (e.g., "laboratory explosion radiation leak")
- Type 3: [location] + [feature] (e.g., "underground city oxygen circulation system")

2. Priority:
- First choice: terms explicitly mentioned in user guidance
- Second choice: core items/locations involved in the current chapter
- Last: supplementary extended concepts that may be relevant

3. Filter mechanism:
- Exclude concepts with an abstraction level above "intermediate"
- Exclude vocabulary with over 60% repetition rate from the previous 3 chapters

Generate 3-5 sets of search terms, listed in descending order of priority.
Format: connect 2-3 keywords per set with "·", one set per line

Example:
tech company · data breach
underground lab · genetic engineering · forbidden experiment
"""

# Knowledge base content filter prompt
knowledge_filter_prompt = """\
Perform a three-level filter on the knowledge base content:

Content to be filtered:
{retrieved_texts}

Current narrative requirements:
{chapter_info}

Filtering process:

Conflict detection:

Delete content with over 40% repetition rate compared to existing summaries

Mark content with worldbuilding contradictions (use ▲ prefix)

Value assessment:

Key value points (marked with ❗):
· Provides new possibilities for character relationships
· Contains metaphorical material that can be adapted
· Has at least 2 extensible detail anchor points

Secondary value points (marked with ·):
· Supplements environmental details
· Provides technical/procedural descriptions

Structural reorganization:

Classify by "plot fuel / character dimension / world fragments / narrative technique"

Add applicable scene hints to each category (e.g., "can be used for XX type of foreshadowing")

Output format:
[Category name] -> [Applicable scene]
❗/· [Content snippet] (▲ conflict note)
...

Example:
[Plot Fuel] -> can be used for time-pressure-type suspense
❗ Underground oxygen system has 23% storage remaining (can create a survival crisis)
▲ Conflicts with the "permanent ecological circulation system" setting mentioned in Chapter 3

Output the final text only, do not explain anything.
Prompt: Content
"""

# =============== 1. Core Seed Setup (Snowflake Layer 1) ===================
core_seed_prompt = """\
As a professional writer, use Step 1 of the "Snowflake Writing Method" to build the story's core:
Theme: {topic}
Genre: {genre}
Length: approximately {number_of_chapters} chapters (each chapter {word_number} words)

Summarize the essence of the story in a single-sentence formula, for example:
"When [protagonist] encounters [core event], they must [key action], otherwise [catastrophic consequence]; meanwhile, [a hidden, greater crisis] is brewing."

Requirements:
1. Must include both an overt conflict and a latent crisis
2. Reflect the character's core driving force
3. Hint at the key contradictions of the worldbuilding
4. Express precisely in 25-100 words

Return only the story core text, do not explain anything.
"""

# =============== 2. Character Dynamics Setup (Character Arc Model) ===================
character_dynamics_prompt = """\
Based on the following elements:
- Content guidance: {user_guidance}
- Core seed: {core_seed}

Please design 3-6 core characters with dynamic change potential. Each character must include:

Traits:
- Background, appearance, gender, age, occupation, etc.
- Hidden secrets or potential weaknesses (may relate to the worldbuilding or other characters)

Core motivation triangle:
- Surface pursuit (material goals)
- Deep desire (emotional needs)
- Soul need (philosophical dimension)

Character arc design:
Initial state -> Triggering event -> Cognitive dissonance -> Transformation node -> Final state

Relationship conflict web:
- Relationships or points of opposition with other characters
- Value conflicts with at least two other characters
- One bond of cooperation
- One hidden possibility of betrayal

Requirements:
Output the final text only, do not explain anything.
"""

# =============== 3. World Building Matrix (Three-Dimensional Weaving Method) ===================
world_building_prompt = """\
Based on the following elements:
- Content guidance: {user_guidance}
- Core conflict: "{core_seed}"

To serve the above content, please construct a three-dimensionally interwoven worldbuilding:

1. Physical dimension:
- Spatial structure (geography x social class distribution map)
- Timeline (chronology of key historical events)
- Rule system (loopholes in physical / magical / social rules)

2. Social dimension:
- Fault lines of power structures (class / racial / organizational conflicts that can trigger conflict)
- Cultural taboos (taboos that can be broken and their consequences)
- Economic lifelines (focal points of resource competition)

3. Metaphorical dimension:
- Visual symbol system woven throughout the book (recurring imagery)
- Psychological states mapped by climate / environmental changes
- Civilizational predicaments implied by architectural styles

Requirements:
Each dimension must include at least 3 dynamic elements that can interact with character decisions.
Output the final text only, do not explain anything.
"""

# =============== 4. Plot Architecture (Three-Act Suspense) ===================
plot_architecture_prompt = """\
Based on the following elements:
- Content guidance: {user_guidance}
- Core seed: {core_seed}
- Character system: {character_dynamics}
- Worldbuilding: {world_building}

Design the structure as follows:
Act One (Triggering)
- Signs of abnormality in the ordinary state (3 setup points)
- Opening the story: present the beginning of the main line, the hidden thread, and the subplot
- Key event: the catalyst that breaks the balance (must change the relationships of at least 3 characters)
- Wrong choice: the protagonist's erroneous reaction caused by their cognitive limitations

Act Two (Confrontation)
- Plot escalation: intersection of main line and subplot
- Dual pressure: external obstacles escalate + internal setbacks
- False victory: a turning point that appears to resolve the crisis but actually deepens it
- Dark night of the soul: the moment of worldview cognitive subversion

Act Three (Resolution)
- Cost revealed: the core value that must be sacrificed to resolve the crisis
- Nested twist: includes at least three layers of cognitive subversion (surface resolution -> new crisis -> ultimate choice)
- Aftermath: leave 2 open-ended suspense factors

Each phase must include 3 key turning points and their corresponding foreshadowing payoff plans.
Output the final text only, do not explain anything.
"""

# =============== 5. Chapter Outline Generation (Suspense Rhythm Curve) ===================
chapter_blueprint_prompt = """\
Based on the following elements:
- Content guidance: {user_guidance}
- Novel architecture:
{novel_architecture}

Design the rhythm distribution for {number_of_chapters} chapters:
1. Chapter cluster division:
- Every 3-5 chapters form one suspense unit, containing a complete minor climax
- Set up a "cognitive roller coaster" between units (2 consecutive intense chapters -> 1 buffer chapter)
- Key turning point chapters should reserve multi-perspective setup space

2. Each chapter must specify:
- Chapter role (character / event / theme, etc.)
- Core suspense type (information gap / moral dilemma / time pressure, etc.)
- Emotional tone transition (e.g., from doubt -> fear -> resolve)
- Foreshadowing operations (plant / reinforce / resolve)
- Cognitive subversion intensity (level 1-5)

Output format example:
Chapter n - [Title]
Chapter role: [character / event / theme / ...]
Core function: [advance / turn / reveal / ...]
Suspense density: [tight / gradual / explosive / ...]
Foreshadowing: plant (clue A) -> reinforce (conflict B)...
Cognitive subversion: ★☆☆☆☆
Chapter summary: [one-sentence overview]

Chapter n+1 - [Title]
Chapter role: [character / event / theme / ...]
Core function: [advance / turn / reveal / ...]
Suspense density: [tight / gradual / explosive / ...]
Foreshadowing: plant (clue A) -> reinforce (conflict B)...
Cognitive subversion: ★☆☆☆☆
Chapter summary: [one-sentence overview]

Requirements:
- Use concise language; keep each chapter description under 100 words.
- Arrange the pacing reasonably to ensure the coherence of the overall suspense curve.
- Do not include a concluding chapter before all {number_of_chapters} chapters have been generated.

Output the final text only, do not explain anything.
"""

chunked_chapter_blueprint_prompt = """\
Based on the following elements:
- Content guidance: {user_guidance}
- Novel architecture:
{novel_architecture}

The total rhythm distribution to be generated is {number_of_chapters} chapters.

Existing chapter list (if empty, this is the initial generation):\n
{chapter_list}

Now please design the rhythm distribution for Chapters {n} through {m}:
1. Chapter cluster division:
- Every 3-5 chapters form one suspense unit, containing a complete minor climax
- Set up a "cognitive roller coaster" between units (2 consecutive intense chapters -> 1 buffer chapter)
- Key turning point chapters should reserve multi-perspective setup space

2. Each chapter must specify:
- Chapter role (character / event / theme, etc.)
- Core suspense type (information gap / moral dilemma / time pressure, etc.)
- Emotional tone transition (e.g., from doubt -> fear -> resolve)
- Foreshadowing operations (plant / reinforce / resolve)
- Cognitive subversion intensity (level 1-5)

Output format example:
Chapter n - [Title]
Chapter role: [character / event / theme / ...]
Core function: [advance / turn / reveal / ...]
Suspense density: [tight / gradual / explosive / ...]
Foreshadowing: plant (clue A) -> reinforce (conflict B)...
Cognitive subversion: ★☆☆☆☆
Chapter summary: [one-sentence overview]

Chapter n+1 - [Title]
Chapter role: [character / event / theme / ...]
Core function: [advance / turn / reveal / ...]
Suspense density: [tight / gradual / explosive / ...]
Foreshadowing: plant (clue A) -> reinforce (conflict B)...
Cognitive subversion: ★☆☆☆☆
Chapter summary: [one-sentence overview]

Requirements:
- Use concise language; keep each chapter description under 100 words.
- Arrange the pacing reasonably to ensure the coherence of the overall suspense curve.
- Do not include a concluding chapter before all {number_of_chapters} chapters have been generated.

Output the final text only, do not explain anything.
"""

# =============== 6. Previous Text Summary Update ===================
summary_prompt = """\
The following is the newly completed chapter text:
{chapter_text}

This is the current previous-text summary (may be empty):
{global_summary}

Please update the previous-text summary based on the new content from this chapter.
Requirements:
- Retain existing important information while incorporating new plot key points
- Describe the overall progress of the book in concise, coherent language
- Describe objectively; do not speculate or elaborate
- Keep the total word count within 2000 words

Return only the previous-text summary text, do not explain anything.
"""

# =============== 7. Character State Update ===================
create_character_state_prompt = """\
Based on the current character dynamics setting: {character_dynamics}

Please generate a character state document in the following format:
Example:
Zhang San:
├── Items:
│  ├── Blue robe: a worn cyan long robe stained with dark red marks
│  └── Cold iron longsword: a broken iron sword with ancient runes carved on the blade
├── Abilities
│  ├── Skill 1 - Strong mental perception: able to sense the thoughts of people nearby
│  └── Skill 2 - Invisible attack: can release a mental attack that cannot be seen with the naked eye
├── Status
│  ├── Physical status: tall and upright, wearing ornate armor, with a cold expression
│  └── Mental status: currently calm, but harboring hidden ambitions and unease over control of Liuxi Village
├── Main character relationship network
│  ├── Li Si: Zhang San has been connected to her since childhood and has always kept watch over her growth
│  └── Wang Er: the two share a complicated past; a recent conflict has made the other feel threatened
├── Triggered or deepened events
│  ├── Unknown symbols suddenly appear in the village: these symbols seem to hint that a major event is about to occur in Liuxi Village
│  └── Li Si is pierced through the skin: this event made both realize the other's formidable strength, prompting them to quickly leave the group

Character name:
├── Items:
│  ├── Some item (prop): description
│  └── XX longsword (weapon): description
│   ...
├── Abilities
│  ├── Skill 1: description
│  └── Skill 2: description
│   ...
├── Status
│  ├── Physical status:
│  └── Mental status: description
│    
├── Main character relationship network
│  ├── Li Si: description
│  └── Wang Er: description
│   ...
├── Triggered or deepened events
│  ├── Event 1: description
│  └── Event 2: description
    ...

New characters:
- (Fill in basic information for any new or temporarily appearing characters here)

Requirements:
Return only the written character state text, do not explain anything.
"""

update_character_state_prompt = """\
The following is the newly completed chapter text:
{chapter_text}

This is the current character state document:
{old_state}

Please update the main character states in the following format:
Example:
Zhang San:
├── Items:
│  ├── Blue robe: a worn cyan long robe stained with dark red marks
│  └── Cold iron longsword: a broken iron sword with ancient runes carved on the blade
├── Abilities
│  ├── Skill 1 - Strong mental perception: able to sense the thoughts of people nearby
│  └── Skill 2 - Invisible attack: can release a mental attack that cannot be seen with the naked eye
├── Status
│  ├── Physical status: tall and upright, wearing ornate armor, with a cold expression
│  └── Mental status: currently calm, but harboring hidden ambitions and unease over control of Liuxi Village
├── Main character relationship network
│  ├── Li Si: Zhang San has been connected to her since childhood and has always kept watch over her growth
│  └── Wang Er: the two share a complicated past; a recent conflict has made the other feel threatened
├── Triggered or deepened events
│  ├── Unknown symbols suddenly appear in the village: these symbols seem to hint that a major event is about to occur in Liuxi Village
│  └── Li Si is pierced through the skin: this event made both realize the other's formidable strength, prompting them to quickly leave the group

Character name:
├── Items:
│  ├── Some item (prop): description
│  └── XX longsword (weapon): description
│   ...
├── Abilities
│  ├── Skill 1: description
│  └── Skill 2: description
│   ...
├── Status
│  ├── Physical status:
│  └── Mental status: description
│    
├── Main character relationship network
│  ├── Li Si: description
│  └── Wang Er: description
│   ...
├── Triggered or deepened events
│  ├── Event 1: description
│  └── Event 2: description
    ...

......

New characters:
- Basic information for any new or temporarily appearing characters; keep it brief, do not expand. Characters who have faded from the story may be removed.

Requirements:
- Make additions and deletions directly on the existing document
- Do not change the original structure; keep the language concise and organized

Return only the updated character state text, do not explain anything.
"""

# =============== 8. Chapter Body Writing ===================

# 8.1 First chapter draft prompt
first_chapter_draft_prompt = """\
Preparing to write: Chapter {novel_number} "{chapter_title}"
Chapter role: {chapter_role}
Core function: {chapter_purpose}
Suspense density: {suspense_level}
Foreshadowing: {foreshadowing}
Cognitive subversion: {plot_twist_level}
Chapter summary: {chapter_summary}

Available elements:
- Core characters (may not be specified): {characters_involved}
- Key items (may not be specified): {key_items}
- Spatial coordinates (may not be specified): {scene_location}
- Time pressure (may not be specified): {time_constraint}

Reference documents:
- Novel settings:
{novel_setting}

Complete the body of Chapter {novel_number}, with a word count requirement of {word_number} words. Design at least 2 or more of the following scenes with dynamic tension:
1. Dialogue scene:
   - Subtext conflict (discussing A on the surface, actually contesting B)
   - Power dynamics shift (conveyed through asymmetric dialogue length)

2. Action scene:
   - Environmental interaction details (at least 3 sensory descriptions)
   - Pacing control (short sentences to accelerate + metaphors to decelerate)
   - Action reveals hidden character traits

3. Psychological scene:
   - Concrete manifestations of cognitive dissonance (behavioral contradictions)
   - Use of metaphor system (connecting worldbuilding symbols)
   - Description of the value balance before a decision

4. Environmental scene:
   - Spatial perspective shift (macro -> micro -> anomalous focus)
   - Unconventional sensory combinations (e.g., "hearing the weight of sunlight")
   - Dynamic environment reflecting psychology (environment corresponds to the character's mental state)

Format requirements:
- Return only the chapter body text;
- Do not use sub-chapter headings;
- Do not use markdown formatting.

Additional guidance (may not be specified): {user_guidance}
"""

# 8.2 Subsequent chapter draft prompt
next_chapter_draft_prompt = """\
Reference documents:
└── Previous text summary:
    {global_summary}

└── Previous chapter closing paragraph:
    {previous_chapter_excerpt}

└── User guidance:
    {user_guidance}

└── Character states:
    {character_state}

└── Current chapter summary:
    {short_summary}

Current chapter information:
Chapter {novel_number} "{chapter_title}":
├── Chapter role: {chapter_role}
├── Core function: {chapter_purpose}
├── Suspense density: {suspense_level}
├── Foreshadowing design: {foreshadowing}
├── Twist level: {plot_twist_level}
├── Chapter summary: {chapter_summary}
├── Word count requirement: {word_number} words
├── Core characters: {characters_involved}
├── Key items: {key_items}
├── Scene location: {scene_location}
└── Time pressure: {time_constraint}

Next chapter outline
Chapter {next_chapter_number} "{next_chapter_title}":
├── Chapter role: {next_chapter_role}
├── Core function: {next_chapter_purpose}
├── Suspense density: {next_chapter_suspense_level}
├── Foreshadowing design: {next_chapter_foreshadowing}
├── Twist level: {next_chapter_plot_twist_level}
└── Chapter summary: {next_chapter_summary}

Knowledge base reference: (apply by priority)
{filtered_context}

Knowledge Base Application Rules:
1. Content classification:
   - Writing technique category (priority):
     ▸ Scene construction templates
     ▸ Dialogue writing techniques
     ▸ Suspense building methods
   - Setting reference category (selective):
     ▸ Unique worldbuilding elements
     ▸ Technical details not yet used
   - Prohibited category (must avoid):
     ▸ Specific plot points that have already appeared in previous chapters
     ▸ Repeated character relationship developments

2. Usage restrictions:
   ● Do not directly copy the plot patterns of existing chapters
   ● Historical chapter content is only permitted for:
     -> Referencing narrative pacing (no more than 20% similarity)
     -> Continuing necessary character reaction patterns (must be adapted by at least 30%)
   ● Third-party writing knowledge should be prioritized for:
     -> Enhancing scene expressiveness (comprising over 60% of knowledge application)
     -> Innovative suspense design (at least 1 new technique)

3. Conflict detection:
   If repetition with historical chapters is detected:
   - Similarity > 40%: narrative angle must be restructured
   - Similarity 20-40%: replace at least 3 key elements
   - Similarity < 20%: allowed to retain core concepts but change their expression

Based on all the above settings, begin completing the body of Chapter {novel_number}, with a word count requirement of {word_number} words.
Content generation must strictly follow:
- User guidance
- Current chapter summary
- Current chapter information
- No logical loopholes
Ensure the chapter content connects smoothly with the previous text summary and the previous chapter's closing paragraph, and that the next chapter outline maintains complete contextual continuity.

Format requirements:
- Return only the chapter body text;
- Do not use sub-chapter headings;
- Do not use markdown formatting.
"""

Character_Import_Prompt = """\
Based on the following text content, analyze all characters and their attribute information. Strictly follow the format requirements below:

<<Character State Format Requirements>>
1. Must include the following five categories (in order):
   ● Items ● Abilities ● Status ● Main character relationship network ● Triggered or deepened events
2. Each attribute entry must use the format [name: description]
   Example: ├──Blue robe: a worn cyan long robe stained with dark red marks
3. Status must include:
   ● Physical status: [current physical condition]
   ● Mental status: [current mental/psychological condition]
4. Relationship network format:
   ● [Character name]: [relationship type, e.g., "rival" / "ally"]
5. Triggered event format:
   ● [Event name]: [brief description and impact]

<<Example>>
Elder Li:
├── Items:
│  ├── Blue robe: a worn cyan long robe stained with dark red marks
│  └── Cold iron longsword: the blade is cracked, with "Azure Cloud" runes engraved on it
├── Abilities:
│  ├── Mental perception: can sense living beings within a 30-meter radius
│  └── Sword-qi suppression: releases mental pressure through eye contact
├── Status:
│  ├── Physical status: right arm has an unhealed sword wound
│  └── Mental status: feels wary of Su Mingyuan's strength
├── Main character relationship network:
│  ├── Su Mingyuan: rival, former colleague from ten years ago
│  └── Lin Wan'er: a secretly cultivated successor
├── Triggered or deepened events:
│  ├── Armory raid: lost three heirloom swords, affecting combat strength
│  └── Anonymous threatening letter: the paper smells of sandalwood, hinting at an internal leak

Please strictly analyze the following content in the above format:
<<Start of novel text to be analyzed>>
{content}
<<End of novel text to be analyzed>>
"""

enrich_prompt = """\
The following chapter text is short. Please expand it while maintaining plot continuity to make it more substantial, aiming for approximately {word_number} words. Output only the final text, do not explain anything.
Original content:
{chapter_text}
"""

# =============== Global Style Enforcement ===============
# This block automatically injects common writing style requirements into all prompts.
_STYLE_REQUIREMENTS = "- CRITICAL: Never use em dashes (—), en dashes (–), or double dashes (--) in any writing."

def _inject_style_requirements(prompt_text):
    if "Format requirements:" in prompt_text:
        return prompt_text.replace("Format requirements:", f"Format requirements:\n{_STYLE_REQUIREMENTS}")
    if "Requirements:" in prompt_text:
        return prompt_text.replace("Requirements:", f"Requirements:\n{_STYLE_REQUIREMENTS}")
    if "Generation rules:" in prompt_text:
        return prompt_text.replace("Generation rules:", f"Generation rules:\n{_STYLE_REQUIREMENTS}")
    if "<<Character State Format Requirements>>" in prompt_text:
        return prompt_text.replace("<<Character State Format Requirements>>", f"<<Character State Format Requirements>>\n{_STYLE_REQUIREMENTS}")
    return prompt_text + f"\n\nStyle Requirement:\n{_STYLE_REQUIREMENTS}"

for _name in list(globals()):
    if (_name.endswith("_prompt") or _name.endswith("_Prompt")) and isinstance(globals()[_name], str):
        globals()[_name] = _inject_style_requirements(globals()[_name])
