-- ============================================================
-- Soviet VVS Enlistment Bot — PostgreSQL Schema
-- Target: PostgreSQL 13+ (Railway-managed Postgres)
-- ============================================================

CREATE TABLE IF NOT EXISTS pilot_records (
    discord_id          VARCHAR PRIMARY KEY,
    soviet_name         VARCHAR NOT NULL,
    callsign            VARCHAR NOT NULL,
    current_rank        VARCHAR NOT NULL DEFAULT 'Junior Lieutenant',
    airframe            VARCHAR,
    squadron            VARCHAR,
    sorties             INTEGER NOT NULL DEFAULT 0,
    flight_hours        REAL NOT NULL DEFAULT 0.0,
    kills_ground         INTEGER NOT NULL DEFAULT 0,
    kills_air           INTEGER NOT NULL DEFAULT 0,
    status               VARCHAR NOT NULL DEFAULT 'ACTIVE',   -- ACTIVE, LOA, KIA, FATIGUED
    fatigue_score        REAL NOT NULL DEFAULT 0.0,
    cheks                INTEGER NOT NULL DEFAULT 0,
    avatar_url           TEXT,
    earned_medals         TEXT NOT NULL DEFAULT '[]',           -- JSON array of medal IDs
    commendations         TEXT NOT NULL DEFAULT '[]',           -- JSON array of {reason, by, ts}
    reprimands            TEXT NOT NULL DEFAULT '[]',           -- JSON array of {reason, by, ts}

    -- Extra bookkeeping columns not in the original spec but required for
    -- the mechanics to function correctly across restarts / audits.
    guild_id              VARCHAR,
    custom_callsign_used  BOOLEAN NOT NULL DEFAULT FALSE,       -- /baza custom callsign one-time flag
    reprimand_count_active INTEGER NOT NULL DEFAULT 0,          -- extra flight-hours-to-promotion penalty tracker
    rr_return_at          TIMESTAMPTZ,                          -- when /rest will auto-clear FATIGUED status
    loa_start             DATE,
    loa_end               DATE,
    loa_reason            TEXT,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_pilot_records_status ON pilot_records(status);
CREATE INDEX IF NOT EXISTS idx_pilot_records_squadron ON pilot_records(squadron);

-- Simple audit trail for Commissar actions (reprimand/commend/award/promote/kia)
CREATE TABLE IF NOT EXISTS commissar_log (
    id            SERIAL PRIMARY KEY,
    discord_id    VARCHAR NOT NULL REFERENCES pilot_records(discord_id) ON DELETE CASCADE,
    action_type   VARCHAR NOT NULL,     -- REPRIMAND, COMMEND, AWARD, PROMOTE, KIA, LOA_APPROVE, LOA_RETURN
    reason        TEXT,
    issued_by     VARCHAR NOT NULL,     -- discord_id of admin/commissar
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_commissar_log_pilot ON commissar_log(discord_id);

-- Fallen-heroes memorial archive (kept even after a fresh /enlist wipes the
-- live pilot_records row identity, since pilot_records is reused by
-- discord_id on re-enlistment).
CREATE TABLE IF NOT EXISTS fallen_heroes (
    id              SERIAL PRIMARY KEY,
    discord_id      VARCHAR NOT NULL,
    soviet_name     VARCHAR NOT NULL,
    callsign        VARCHAR NOT NULL,
    final_rank      VARCHAR NOT NULL,
    squadron        VARCHAR,
    airframe        VARCHAR,
    sorties         INTEGER,
    flight_hours    REAL,
    kills_ground    INTEGER,
    kills_air       INTEGER,
    medals          TEXT,
    cause_of_death  TEXT,
    died_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
