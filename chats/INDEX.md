# Chat History Index

This directory contains exported chat conversations related to the ocr-text-aligner project.

## Chat Files

<!-- Add entries below as you export chats. Format:
- [filename.md](filename.md) - Date: YYYY-MM-DD | Summary: Brief description of what was discussed | LLM: Model name if available
-->
- [26-11-2025_chat_visualization-and-edge-case-handling.md](26-11-2025_chat_visualization-and-edge-case-handling.md) 
    - Date: 2025-11-26
    - Summary: Restored and enhanced fuzzy matching visualization to show full pipeline (ALTO elements → fuzzy matching → LLM token candidates → context scoring → final selection). Handled edge cases including fixing "Witness:" being incorrectly flagged as error, improved hyphen visualization placement, and added comprehensive pipeline visualization with linguistic context positions.
    - LLM: Not specified in export

- [25_11_2025_chat_first-debug.md](25_11_2025_chat_first-debug.md) 
    - Date: 2025-11-25
    - Summary: Comprehensive error review and fixes in map_up_text.py (excluding hyphenation/splits handling). Fixed syntax errors, performance issues (list modification during iteration), optimized fuzzy matching functions (assign_llm_candidates_to_all_token_hypotheses_by_fuzzy_matching, search_for_word_merges), and corrected various bugs throughout the codebase.
    - LLM: Not specified in export

- [21-11-2025_chat_visualize-process.md](21-11-2025_chat_visualize-process.md)
    - Date: 2025-11-21
    - Summary: Created initial visualization module (visualize_matching.py) for map_up_text.py to understand the complex matching process. Implemented spatial visualizations with matplotlib showing word positions, matching tables with Rich library, hyphen analysis tree views, step-by-step hyphen linking process, and summary dashboards. Fixed normalize_token bug. Integrated visualizations into main script.
    - LLM: Not specified in export


## Instructions

1. Export each relevant chat from Cursor using the export option in each chat tab
2. Save the exported markdown files to this `chats/` directory
3. Add an entry to this index file with:
   - Filename
   - Date of the conversation
   - Brief description of what was discussed/accomplished
   - LLM model used (if available in the export)

## Notes

- Use descriptive filenames like `YYYY-MM-DD_chat_summary.md`
- Keep descriptions concise but informative
- Include any important decisions, bug fixes, or feature implementations discussed

