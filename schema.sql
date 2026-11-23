-- Giai đoạn 1 theo ERD. Idempotent: chạy lại an toàn.
-- Giai đoạn 2/3 (artwork_likes, comments, challenges, events, attendance, device_tokens) thêm bằng migration riêng.

CREATE TABLE IF NOT EXISTS profiles (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    full_name     text NOT NULL CHECK (length(full_name) BETWEEN 1 AND 80),
    email         text NOT NULL,
    password_hash text,
    role          text NOT NULL DEFAULT 'member' CHECK (role IN ('member', 'admin')),
    status        text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'break', 'former')),
    is_locked     boolean NOT NULL DEFAULT false,
    avatar_url    text,
    created_at    timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS profiles_email_key ON profiles (lower(email));

CREATE TABLE IF NOT EXISTS activation_codes (
    id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    profile_id uuid NOT NULL REFERENCES profiles(id),
    code_hash  text NOT NULL UNIQUE,
    expires_at timestamptz NOT NULL,
    used_at    timestamptz,
    revoked_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS artworks (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    author_id     uuid NOT NULL REFERENCES profiles(id),
    title         text NOT NULL CHECK (length(title) BETWEEN 1 AND 120),
    description   text,
    original_id   text NOT NULL,  -- Cloudinary public_id, type=private, không bao giờ lộ ra HTML
    public_id     text NOT NULL,  -- bản nén + watermark; type=upload nếu public, authenticated nếu internal
    visibility    text NOT NULL DEFAULT 'public' CHECK (visibility IN ('public', 'internal')),
    status        text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'rejected')),
    reject_reason text,
    created_at    timestamptz NOT NULL DEFAULT now(),
    deleted_at    timestamptz
);
CREATE INDEX IF NOT EXISTS artworks_feed_idx ON artworks (created_at DESC) WHERE status = 'approved' AND deleted_at IS NULL;

CREATE TABLE IF NOT EXISTS tags (
    id   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name text NOT NULL CHECK (length(name) BETWEEN 1 AND 30),
    type text NOT NULL CHECK (type IN ('location', 'material', 'session'))
);
CREATE UNIQUE INDEX IF NOT EXISTS tags_name_type_key ON tags (lower(name), type);

CREATE TABLE IF NOT EXISTS artwork_tags (
    artwork_id uuid NOT NULL REFERENCES artworks(id) ON DELETE CASCADE,
    tag_id     uuid NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    PRIMARY KEY (artwork_id, tag_id)
);

CREATE TABLE IF NOT EXISTS albums (
    id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    title      text NOT NULL CHECK (length(title) BETWEEN 1 AND 120),
    cover_path text NOT NULL,  -- Cloudinary public_id (type=upload)
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS album_photos (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    album_id    uuid NOT NULL REFERENCES albums(id) ON DELETE CASCADE,
    uploaded_by uuid NOT NULL REFERENCES profiles(id),
    image_path  text NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS notifications (
    id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    title      text NOT NULL CHECK (length(title) BETWEEN 1 AND 120),
    body       text NOT NULL,
    type       text NOT NULL DEFAULT 'news' CHECK (type IN ('news', 'event')),
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS audit_logs (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    actor_id    uuid REFERENCES profiles(id),  -- NULL = thao tác từ CLI
    action      text NOT NULL,
    target_type text,
    target_id   uuid,
    created_at  timestamptz NOT NULL DEFAULT now()
);
