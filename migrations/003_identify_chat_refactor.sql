-- ============================================================
-- Migration 003: Refactor Identify (识Ta) into chat-analysis conversations
--
-- Old tables `user_portraits` and `analysis_records` are no longer used by
-- the application. They are LEFT IN PLACE to preserve historical data. Feel
-- free to drop them manually once you're sure no production data needs to be
-- kept.
-- ============================================================

-- 1. Conversations -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS identify_conversations (
    id               VARCHAR(36)  NOT NULL PRIMARY KEY COMMENT 'UUID, also used as FastGPT chatId',
    user_id          VARCHAR(36)  NOT NULL COMMENT 'Owner user id',
    title            VARCHAR(120) NOT NULL DEFAULT '新会话' COMMENT 'Auto-generated from first user message',
    message_count    INT          NOT NULL DEFAULT 0,
    last_message_at  TIMESTAMP    NULL,
    status           TINYINT      NOT NULL DEFAULT 1 COMMENT '1-active 0-deleted',
    created_at       TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at       TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    KEY idx_user_status_last (user_id, status, last_message_at),
    CONSTRAINT fk_identify_conv_user
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Chat-analysis conversation thread';

-- 2. Messages ----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS identify_messages (
    id                VARCHAR(36) NOT NULL PRIMARY KEY,
    conversation_id   VARCHAR(36) NOT NULL,
    role              VARCHAR(16) NOT NULL COMMENT 'user / assistant',

    -- user-side
    text              TEXT        NULL,
    image_url         VARCHAR(500) NULL,

    -- assistant-side
    final_content     MEDIUMTEXT  NULL,
    workflow_nodes    JSON        NULL,
    duration_seconds  INT         NULL,
    status            VARCHAR(16) NOT NULL DEFAULT 'done' COMMENT 'streaming/done/failed',
    error_message     VARCHAR(500) NULL,

    created_at        TIMESTAMP   NOT NULL DEFAULT CURRENT_TIMESTAMP,

    KEY idx_conv_created (conversation_id, created_at),
    CONSTRAINT fk_identify_msg_conv
        FOREIGN KEY (conversation_id) REFERENCES identify_conversations(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Messages within a chat-analysis conversation';

-- 3. (Optional) mark legacy tables as deprecated -----------------------------
--
-- Not executed by default. Uncomment if you want to drop old portrait data.
--
-- DROP TABLE IF EXISTS analysis_records;
-- DROP TABLE IF EXISTS user_portraits;
