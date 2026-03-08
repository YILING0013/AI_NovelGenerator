# AGENTS.md - ui

**Generated:** 2026-01-27
**Module:** CustomTkinter GUI interface

## OVERVIEW
CustomTkinter-based GUI providing tabbed interface for novel generation configuration and execution.

## STRUCTURE
```
ui/
├── __init__.py
├── main_window.py           # Main application window
├── main_tab.py             # Main control panel
├── config_tab.py            # LLM/API configuration
├── novel_params_tab.py      # Novel parameters
├── directory_tab.py         # Output directory settings
├── character_tab.py        # Character management
├── summary_tab.py          # Chapter summary management
├── chapters_tab.py         # Chapter list/operations
├── setting_tab.py          # Generation settings
├── generation_handlers.py  # Generation logic handlers
├── context_menu.py         # Right-click context menus
├── helpers.py              # UI utility functions
├── other_settings.py       # Additional settings
├── role_library.py         # Pre-defined character roles
└── generation/             # Generation-specific UI
```

## WHERE TO LOOK
| Task | File | Notes |
|------|------|-------|
| Main window | main_window.py | App entry point |
| LLM config | config_tab.py | API keys, model selection |
| Novel params | novel_params_tab.py | Title, genre, word count |
| Chapters | chapters_tab.py | Chapter list, actions |
| Generation | generation_handlers.py | Backend integration |
| Helpers | helpers.py | Common UI utilities |

## CONVENTIONS
- **CustomTkinter widgets**: Use CTkButton, CTkLabel, CTkEntry
- **Tab structure**: Each major feature = separate tab
- **Event handling**: Callbacks in generation_handlers.py
- **State management**: Config loaded/saved via config_manager
- **UI updates**: Use main_window methods for app-wide updates

## ANTI-PATTERNS
- Do NOT block UI thread with long-running operations
- Do NOT hardcode paths - use directory_tab
- Do NOT store config in UI - use config_manager
- Do NOT bypass generation_handlers for backend calls

## UNIQUE STYLES
- Tabbed interface: modular design for different features
- Context menu: right-click actions for chapters
- Role library: pre-defined character archetypes
- Generation handlers: separation of UI and logic

## NOTES
- All UI components inherit from CustomTkinter base widgets
- Generation is non-blocking (uses threading/background tasks)
- Config saved to JSON via config_manager
