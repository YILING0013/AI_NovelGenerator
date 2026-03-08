
import os

target_file = 'prompt_definitions.py'
gold_standard_file = 'Chapter_1_Gold_Standard.txt'

# Read the gold standard content
with open(gold_standard_file, 'r', encoding='utf-8') as f:
    gold_content = f.read()

# Read the corrupted file lines safely
with open(target_file, 'r', encoding='utf-8', errors='ignore') as f:
    lines = f.readlines()

# Find where BLUEPRINT_FEW_SHOT_EXAMPLE starts
start_index = -1
for i, line in enumerate(lines):
    if 'BLUEPRINT_FEW_SHOT_EXAMPLE = """' in line:
        start_index = i
        break

if start_index != -1:
    # Keep everything before the corrupted variable
    clean_lines = lines[:start_index]
else:
    # If not found, imply it might be so corrupted or missing, but we assume it's there based on error
    # If not found, we might append it, but let's check if we are just appending to a file that missed it? 
    # No, error says line 2168.
    print("Could not find BLUEPRINT_FEW_SHOT_EXAMPLE definition. Appending to end.")
    clean_lines = lines

# Reconstruct the file content
new_content_list = clean_lines
new_content_list.append('\nBLUEPRINT_FEW_SHOT_EXAMPLE = """\n')
new_content_list.append(gold_content)
new_content_list.append('\n"""\n')

# Write back with utf-8
with open(target_file, 'w', encoding='utf-8') as f:
    f.writelines(new_content_list)

print("Successfully repaired prompt_definitions.py")
