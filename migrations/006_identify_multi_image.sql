-- ============================================================
-- Migration 006: Multi-image support for 识Ta messages
--
-- Old schema kept just `image_url VARCHAR(500)` per message, so when
-- a user sent 2+ images we silently dropped everything but the first
-- on persistence. The bubble re-rendered as a single image on reload
-- (no stacked-card / "+N" visual), even though FastGPT had received
-- all of them.
--
-- Fix: add a `image_urls JSON` column that stores the full array.
-- The legacy `image_url` column is kept (NULLable) for back-compat
-- with any code that still reads it; new writes populate both, with
-- `image_urls` being the source of truth.
-- ============================================================

ALTER TABLE identify_messages
    ADD COLUMN image_urls JSON NULL
        COMMENT 'Array of uploaded image OSS URLs (all images for this message)' AFTER image_url;
