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
    birth_place           VARCHAR,             -- "City, Republic SSR"
    birth_date            DATE,
    backstory             TEXT,
    service_record_details TEXT,               -- nationality, party status, education, etc.
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

-- Pool of pre-generated pilot photos sourced from a designated Discord
-- channel. Populated by /sync_avatar_pool; drawn from randomly (and marked
-- used) during /enlist so real, already-uploaded portraits get reused
-- instead of generating a new one every time.
-- message_id despite its name holds a per-IMAGE unique key (e.g.
-- "att-<attachment_id>" or "embed-<message_id>-<index>"), not the raw
-- Discord message ID, since a single message can contain multiple images.
CREATE TABLE IF NOT EXISTS avatar_pool (
    id            SERIAL PRIMARY KEY,
    message_id    VARCHAR NOT NULL UNIQUE,
    attachment_url TEXT NOT NULL,
    is_used        BOOLEAN NOT NULL DEFAULT FALSE,
    assigned_to    VARCHAR,             -- discord_id of the pilot it was given to
    added_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_avatar_pool_unused ON avatar_pool(is_used) WHERE is_used = FALSE;

-- Catalog of medal icons, keyed by a normalized (lowercased/trimmed) name so
-- /award reuses the same icon every time the same medal name is given out.
CREATE TABLE IF NOT EXISTS medal_catalog (
    medal_key     VARCHAR PRIMARY KEY,   -- normalized: lower().strip()
    display_name  VARCHAR NOT NULL,      -- original casing, shown in embeds
    image_url     TEXT NOT NULL,
    added_by      VARCHAR,
    added_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Catalog of rank icons, one row per canonical rank name.
CREATE TABLE IF NOT EXISTS rank_catalog (
    rank_name     VARCHAR PRIMARY KEY,
    image_url     TEXT NOT NULL,
    added_by      VARCHAR,
    added_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Singleton staging row for the next Daily Orders post. Admins can prep
-- mission_number/objective/readiness/manual crew list ahead of the
-- scheduled auto-post via dedicated commands; whatever hasn't been set
-- falls back to sensible defaults (auto-roster for crew, placeholder text
-- for objective) so the automatic post never goes out with blank fields.
-- Reset back to defaults after each post (scheduled or forced) so stale
-- info doesn't carry over to the next day.
CREATE TABLE IF NOT EXISTS daily_orders_state (
    id                  INTEGER PRIMARY KEY DEFAULT 1,
    mission_number      INTEGER NOT NULL DEFAULT 1,
    objective           TEXT,
    readiness_condition VARCHAR,
    manual_crew_ids     TEXT NOT NULL DEFAULT '[]',   -- JSON array of discord_ids; empty = auto roster
    conditions_text     TEXT,                          -- manually-staged server/mission/weather snapshot
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT daily_orders_state_singleton CHECK (id = 1)
);

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

-- Guncam kill claims. One row per image attachment posted in
-- #killclaims by an enlisted member. Stays PENDING until a Commissar
-- actions the approval buttons; kept permanently (not deleted) as an
-- audit trail even after resolution.
CREATE TABLE IF NOT EXISTS kill_claims (
    id             SERIAL PRIMARY KEY,
    discord_id     VARCHAR NOT NULL,
    message_id     VARCHAR NOT NULL,   -- original message in #killclaims
    channel_id     VARCHAR NOT NULL,   -- original message's channel
    review_message_id VARCHAR,          -- the approval-embed message in ADMIN_APPROVAL_CHANNEL_ID
    image_url      TEXT NOT NULL,
    status         VARCHAR NOT NULL DEFAULT 'PENDING',  -- PENDING, APPROVED_AIR, APPROVED_GROUND, DENIED
    reviewed_by    VARCHAR,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    reviewed_at    TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_kill_claims_status ON kill_claims(status) WHERE status = 'PENDING';

-- Per-pilot API tokens used by the Cold War EFB (or any future companion
-- app) to authenticate sortie reports without ever handling Discord OAuth.
-- The token IS the identity for ingestion purposes — the standalone
-- ingest service looks up discord_id from this table directly, so
-- dcs_player_name on pilot_records is informational/cosmetic only, not
-- part of the auth path. One live token per pilot; issuing a new one
-- invalidates the old (UNIQUE + upsert-by-discord_id).
CREATE TABLE IF NOT EXISTS pilot_efb_tokens (
    discord_id   VARCHAR PRIMARY KEY REFERENCES pilot_records(discord_id) ON DELETE CASCADE,
    token        VARCHAR NOT NULL UNIQUE,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Sortie reports posted by the EFB's bridge.js sortie tracker at the end
-- of each flight. Auto-credited on arrival (no Commissar review, unlike
-- kill_claims) — the ingest service inserts PENDING rows here, and
-- CommissarBot's dcs_sync cog polls, applies the stat deltas, and marks
-- them PROCESSED. Kept permanently as an audit trail.
CREATE TABLE IF NOT EXISTS dcs_sortie_reports (
    id                  SERIAL PRIMARY KEY,
    discord_id          VARCHAR NOT NULL,
    airframe            VARCHAR,
    sorties_delta       INTEGER NOT NULL DEFAULT 0,
    flight_hours_delta  REAL NOT NULL DEFAULT 0.0,
    takeoffs_delta      INTEGER NOT NULL DEFAULT 0,
    landings_delta      INTEGER NOT NULL DEFAULT 0,
    status              VARCHAR NOT NULL DEFAULT 'PENDING',  -- PENDING, PROCESSED, REJECTED
    raw_payload         TEXT,                                 -- original JSON, for audit/debugging
    reported_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    processed_at        TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_dcs_sortie_reports_status ON dcs_sortie_reports(status) WHERE status = 'PENDING';
CREATE INDEX IF NOT EXISTS idx_dcs_sortie_reports_discord_reported ON dcs_sortie_reports(discord_id, reported_at DESC);

-- ============================================================
-- Migrations for already-deployed databases
-- ============================================================
-- CREATE TABLE IF NOT EXISTS is a no-op on tables that already exist, so
-- columns added to an existing table's definition above won't actually
-- appear in a database that was created before this change. These
-- ALTER TABLE ... ADD COLUMN IF NOT EXISTS statements are idempotent and
-- safe to run on every boot regardless of whether the column already
-- exists (fresh install) or needs to be added (existing deployment).

ALTER TABLE pilot_records ADD COLUMN IF NOT EXISTS birth_place VARCHAR;
ALTER TABLE pilot_records ADD COLUMN IF NOT EXISTS birth_date DATE;
ALTER TABLE pilot_records ADD COLUMN IF NOT EXISTS backstory TEXT;
ALTER TABLE pilot_records ADD COLUMN IF NOT EXISTS service_record_details TEXT;
ALTER TABLE pilot_records ADD COLUMN IF NOT EXISTS dcs_player_name VARCHAR;
ALTER TABLE pilot_records ADD COLUMN IF NOT EXISTS takeoffs INTEGER NOT NULL DEFAULT 0;
ALTER TABLE pilot_records ADD COLUMN IF NOT EXISTS landings INTEGER NOT NULL DEFAULT 0;

-- Lifetime DCS-tracked totals, spanning every life this discord_id has ever
-- enlisted under. Unlike sorties/flight_hours/takeoffs/landings above
-- (which are per-character and deliberately reset to 0 on re-enlistment —
-- see create_pilot's ON CONFLICT clause in db.py), these four columns are
-- never zeroed by anything. They only ever go up. A KIA'd pilot's combat
-- record dies with them (as intended — permadeath should mean something),
-- but the underlying flight time and stick time a real person put in
-- flying for the squadron does not disappear just because their in-game
-- persona did.
ALTER TABLE pilot_records ADD COLUMN IF NOT EXISTS dcs_lifetime_sorties INTEGER NOT NULL DEFAULT 0;
ALTER TABLE pilot_records ADD COLUMN IF NOT EXISTS dcs_lifetime_flight_hours REAL NOT NULL DEFAULT 0.0;
ALTER TABLE pilot_records ADD COLUMN IF NOT EXISTS dcs_lifetime_takeoffs INTEGER NOT NULL DEFAULT 0;
ALTER TABLE pilot_records ADD COLUMN IF NOT EXISTS dcs_lifetime_landings INTEGER NOT NULL DEFAULT 0;

-- fallen_heroes gets the same takeoffs/landings snapshot sorties/flight_hours
-- already had, for consistency — the per-character DCS stats a fallen
-- pilot had at time of death are archived here same as everything else.
ALTER TABLE fallen_heroes ADD COLUMN IF NOT EXISTS takeoffs INTEGER;
ALTER TABLE fallen_heroes ADD COLUMN IF NOT EXISTS landings INTEGER;

-- Defensive: covers the case where daily_orders_state was already created
-- by an earlier deploy before conditions_text was added to its definition.
ALTER TABLE daily_orders_state ADD COLUMN IF NOT EXISTS conditions_text TEXT;

-- One-time repair: Discord signs CDN attachment URLs with ?ex=...&is=...
-- &hm=... query parameters that expire (~24h). Earlier versions of this
-- bot stored those signed URLs as-is in avatar_url/attachment_url/
-- image_url columns, so any image assigned more than about a day before
-- this fix deployed has gone dead. Per Discord's own API docs, the BARE
-- CDN path (no query string) is unsigned and never expires — stripping
-- the query string here retroactively repairs every already-broken image
-- without needing to re-fetch anything from Discord. Idempotent: rows
-- with no '?' (already stripped, or non-Discord URLs) are left unchanged.
UPDATE pilot_records
SET avatar_url = split_part(avatar_url, '?', 1)
WHERE avatar_url LIKE '%cdn.discordapp.com%' OR avatar_url LIKE '%media.discordapp.net%';

UPDATE avatar_pool
SET attachment_url = split_part(attachment_url, '?', 1)
WHERE attachment_url LIKE '%cdn.discordapp.com%' OR attachment_url LIKE '%media.discordapp.net%';

UPDATE medal_catalog
SET image_url = split_part(image_url, '?', 1)
WHERE image_url LIKE '%cdn.discordapp.com%' OR image_url LIKE '%media.discordapp.net%';

UPDATE rank_catalog
SET image_url = split_part(image_url, '?', 1)
WHERE image_url LIKE '%cdn.discordapp.com%' OR image_url LIKE '%media.discordapp.net%';
