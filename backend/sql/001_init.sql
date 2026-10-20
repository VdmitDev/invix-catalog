CREATE TABLE IF NOT EXISTS products (
    id BIGSERIAL PRIMARY KEY,
    title VARCHAR(200) NOT NULL CHECK (length(btrim(title)) > 0),
    image_key VARCHAR(300) NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    source_chat_id BIGINT,
    source_message_id BIGINT,
    CONSTRAINT products_telegram_source_unique UNIQUE (source_chat_id, source_message_id)
);

CREATE INDEX IF NOT EXISTS idx_products_created_at_id
    ON products (created_at DESC, id DESC);
