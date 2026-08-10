ALTER TABLE schedules
ADD COLUMN share_token VARCHAR(64) UNIQUE,
ADD COLUMN share_enabled BOOLEAN DEFAULT FALSE,
ADD COLUMN share_expires_at TIMESTAMP WITH TIME ZONE;

CREATE INDEX idx_schedules_share_token ON schedules(share_token) WHERE share_token IS NOT NULL;
