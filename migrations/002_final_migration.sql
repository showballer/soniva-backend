-- 完成声鉴结果表字段迁移

-- 1. 修改 main_voice_type 字段类型为 JSON
ALTER TABLE voice_test_results
MODIFY COLUMN main_voice_type JSON NOT NULL COMMENT 'Main voice type {level1, level2, full_name}';

-- 2. 添加新字段
ALTER TABLE voice_test_results
ADD COLUMN auxiliary_tags JSON COMMENT 'Auxiliary tags array' AFTER main_voice_type,
ADD COLUMN development_directions JSON COMMENT 'Development directions array' AFTER auxiliary_tags,
ADD COLUMN voice_position VARCHAR(100) COMMENT 'Voice position' AFTER development_directions,
ADD COLUMN resonance JSON COMMENT 'Resonance array' AFTER voice_position,
ADD COLUMN voice_temperature VARCHAR(20) COMMENT 'Voice temperature: 暖/冷/中性' AFTER voice_attribute,
ADD COLUMN perceived_food VARCHAR(200) COMMENT 'Perceived food' AFTER voice_temperature,
ADD COLUMN perceived_age INT COMMENT 'Perceived age' AFTER perceived_food,
ADD COLUMN perceived_height INT COMMENT 'Perceived height' AFTER perceived_age,
ADD COLUMN perceived_feedback JSON COMMENT 'Perceived feedback array' AFTER perceived_height,
ADD COLUMN love_score INT COMMENT 'Love score 0-100' AFTER perceived_feedback,
ADD COLUMN recommended_partner JSON COMMENT 'Recommended partner array' AFTER love_score,
ADD COLUMN signature TEXT COMMENT 'Voice signature poem' AFTER recommended_partner,
ADD COLUMN improvement_tips JSON COMMENT 'Improvement tips array' AFTER signature;

-- 3. 更新 voice_attribute 字段注释
ALTER TABLE voice_test_results
MODIFY COLUMN voice_attribute VARCHAR(20) COMMENT 'Voice attribute: 攻/受/可攻可受';
