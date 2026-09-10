-- Server-side identity, sessions, rate limits, audit events, and isolated user watchlists.
CREATE TABLE quantrade.app_users (
    user_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email TEXT NOT NULL,
    normalized_email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'owner' CHECK (role IN ('owner', 'member')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    disabled_at TIMESTAMPTZ
);

CREATE TABLE quantrade.app_sessions (
    session_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES quantrade.app_users(user_id) ON DELETE CASCADE,
    token_sha256 CHAR(64) NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL,
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    revoked_at TIMESTAMPTZ,
    CHECK (expires_at > created_at)
);
CREATE INDEX app_sessions_user_active_idx
    ON quantrade.app_sessions (user_id, expires_at DESC)
    WHERE revoked_at IS NULL;

CREATE TABLE quantrade.user_watchlist_entries (
    user_id UUID NOT NULL REFERENCES quantrade.app_users(user_id) ON DELETE CASCADE,
    security_id UUID NOT NULL REFERENCES quantrade.securities(security_id) ON DELETE CASCADE,
    note TEXT NOT NULL DEFAULT '' CHECK (length(note) <= 240),
    tags TEXT[] NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, security_id),
    CHECK (cardinality(tags) <= 5)
);
CREATE INDEX user_watchlist_entries_user_updated_idx
    ON quantrade.user_watchlist_entries (user_id, updated_at DESC);

CREATE TABLE quantrade.web_rate_limit_windows (
    scope TEXT NOT NULL,
    subject_sha256 CHAR(64) NOT NULL,
    window_started_at TIMESTAMPTZ NOT NULL,
    request_count INTEGER NOT NULL CHECK (request_count > 0),
    expires_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (scope, subject_sha256, window_started_at)
);
CREATE INDEX web_rate_limit_expiry_idx ON quantrade.web_rate_limit_windows (expires_at);

CREATE TABLE quantrade.web_audit_events (
    audit_event_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    request_id UUID NOT NULL,
    user_id UUID REFERENCES quantrade.app_users(user_id) ON DELETE SET NULL,
    event_type TEXT NOT NULL,
    outcome TEXT NOT NULL CHECK (outcome IN ('allowed', 'denied', 'failed')),
    route TEXT NOT NULL,
    subject_sha256 CHAR(64),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX web_audit_events_occurred_idx ON quantrade.web_audit_events (occurred_at DESC);
CREATE INDEX web_audit_events_user_idx ON quantrade.web_audit_events (user_id, occurred_at DESC);

CREATE FUNCTION quantrade.reject_web_audit_event_mutation()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'web audit events are append-only';
END;
$$;
CREATE TRIGGER web_audit_events_append_only
    BEFORE UPDATE OR DELETE ON quantrade.web_audit_events
    FOR EACH ROW EXECUTE FUNCTION quantrade.reject_web_audit_event_mutation();

COMMENT ON TABLE quantrade.user_watchlist_entries IS
    'Private user data; every query must scope by the authenticated user_id.';
COMMENT ON TABLE quantrade.web_audit_events IS
    'Append-only security events; metadata must never contain credentials, session tokens, or raw IP addresses.';
