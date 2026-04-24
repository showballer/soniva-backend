-- ============================================================
-- Migration 004: Add structured TRIPLE-TACTICS storage to identify_messages
--
-- Populated on assistant-message persistence from the FastGPT workflow's
-- `策略生成` node (moduleType=contentExtract). Shape:
--   [
--     {"title": "...", "description": "...", "phrases": ["...", "..."]},
--     ...
--   ]
-- Optional — old rows stay NULL and the frontend falls back to regex
-- extraction from final_content.
-- ============================================================

ALTER TABLE identify_messages
    ADD COLUMN tactics JSON NULL
    COMMENT 'Structured TRIPLE-TACTICS cards [{title, description, phrases}]'
    AFTER workflow_nodes;
