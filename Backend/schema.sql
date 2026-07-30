-- CentralWatch schema (TimescaleDB / Postgres)
-- Run this once against a fresh database:
--   psql -d centralwatch -f schema.sql

CREATE EXTENSION IF NOT EXISTS timescaledb;

-- ============================================================
-- 1. services: registry of known target services (for quota/cost
--    lookups and so the dashboard has something to list even
--    before any events exist for a service).
-- ============================================================
CREATE TABLE IF NOT EXISTS services (
    service_name    TEXT PRIMARY KEY,
    display_name    TEXT,
    provider        TEXT,               -- e.g. 'aws', 'stripe', 'internal'
    quota_limit     INTEGER,            -- calls per window, nullable if unknown
    quota_window_s  INTEGER,            -- window length in seconds, e.g. 60
    cost_per_call   NUMERIC(10, 6),     -- USD per call, nullable if unknown
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ============================================================
-- 2. events: the core hypertable. One row per observed API call.
--    This is the schema Person A's collector agent must produce.
-- ============================================================
CREATE TABLE IF NOT EXISTS events (
    event_id        UUID NOT NULL DEFAULT gen_random_uuid(),
    ts              TIMESTAMPTZ NOT NULL,        -- when the call happened
    source_env      TEXT NOT NULL,               -- 'dev' | 'staging' | 'prod'
    agent_id        TEXT,                        -- which collector instance sent this
    target_service  TEXT NOT NULL,               -- e.g. 'stripe', 's3', 'weather_api'
    endpoint        TEXT,                        -- e.g. '/v1/charges'
    method          TEXT,                        -- GET/POST/etc
    status_code     INTEGER,                     -- HTTP status, null if request never returned
    latency_ms      NUMERIC(10, 2),               -- null if timed out
    payload_size_b  INTEGER,                     -- request+response bytes, best-effort
    error_type      TEXT,                        -- 'timeout' | 'connection_error' | 'http_error' | null
    error_message   TEXT,
    received_at     TIMESTAMPTZ NOT NULL DEFAULT now(),  -- when OUR backend got it
    PRIMARY KEY (event_id, ts)
);

-- Convert to a hypertable partitioned on time (7-day chunks is a
-- reasonable default for a semester-length project's data volume)
SELECT create_hypertable('events', 'ts', chunk_time_interval => INTERVAL '7 days',
                          if_not_exists => TRUE);

CREATE INDEX IF NOT EXISTS idx_events_service_ts ON events (target_service, ts DESC);
CREATE INDEX IF NOT EXISTS idx_events_env_ts ON events (source_env, ts DESC);
CREATE INDEX IF NOT EXISTS idx_events_status ON events (status_code);

-- ============================================================
-- 3. alerts: rows written whenever the rules engine fires.
--    The dashboard's alert feed reads directly from this table.
-- ============================================================
CREATE TABLE IF NOT EXISTS alerts (
    alert_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    triggered_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    rule_name       TEXT NOT NULL,               -- e.g. 'error_rate_threshold'
    severity        TEXT NOT NULL,               -- 'warning' | 'critical'
    source_env      TEXT,
    target_service  TEXT,
    message         TEXT NOT NULL,
    details         JSONB,                       -- e.g. {"error_rate": 0.12, "threshold": 0.05}
    resolved        BOOLEAN NOT NULL DEFAULT FALSE,
    resolved_at     TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_alerts_triggered ON alerts (triggered_at DESC);
CREATE INDEX IF NOT EXISTS idx_alerts_service ON alerts (target_service, triggered_at DESC);

-- ============================================================
-- 4. continuous aggregate: 1-minute rollups per service/env.
--    This is what makes dashboard graphs fast — querying raw
--    events for a week-long chart would be slow and wasteful.
-- ============================================================
CREATE MATERIALIZED VIEW IF NOT EXISTS events_1min
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 minute', ts) AS bucket,
    source_env,
    target_service,
    count(*)                                        AS call_count,
    count(*) FILTER (WHERE status_code >= 400 OR error_type IS NOT NULL) AS error_count,
    avg(latency_ms)                                 AS avg_latency_ms,
    max(latency_ms)                                 AS max_latency_ms
    -- NOTE: p95 latency is deliberately NOT rolled up here. Ordered-set
    -- aggregates (percentile_cont) are unreliable inside continuous
    -- aggregates across TimescaleDB versions. Compute p95 on-demand
    -- from raw `events` for short windows instead (see query.py).
FROM events
GROUP BY bucket, source_env, target_service
WITH NO DATA;

SELECT add_continuous_aggregate_policy('events_1min',
    start_offset => INTERVAL '1 hour',
    end_offset   => INTERVAL '1 minute',
    schedule_interval => INTERVAL '1 minute',
    if_not_exists => TRUE);

-- Retention: drop raw event chunks older than 30 days to keep the
-- demo DB small. Adjust or remove if your prof wants full history.
SELECT add_retention_policy('events', INTERVAL '30 days', if_not_exists => TRUE);
