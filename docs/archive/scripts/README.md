# Archived Scripts

This directory stores one-off maintenance scripts that are intentionally removed from runtime paths.

## legacy_fixes

Prompt migration/repair scripts archived from the repository root:

- `add_chunked_prompt.py`
- `fix_chunked_prompt.py`
- `fix_prompt_add_fewshot.py`
- `fix_template_sections.py`
- `fix_orphaned_template.py`
- `repair_prompt_file.py`
- `fix_sections_8_to_13.py`

These scripts were used during historical prompt cleanup and should not be imported by runtime modules.

## one_off_root

Historical one-off scripts moved out of repository root to keep the runtime surface minimal.

Current archived files include:

- analysis scripts (`analyze_*`)
- debug/diagnose scripts (`debug_*`, `diagnose_*`)
- ad-hoc repair scripts (`fix_*`, `apply_*`, `auto_fix_*`)
- temporary integration/manual runners (`manual_test_gen.py`, `integration_example.py`, etc.)

Do not import these scripts from runtime modules.
