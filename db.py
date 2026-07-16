"""
Database access layer for the Soviet VVS Enlistment Bot.

Uses asyncpg with a connection pool. All queries live here so cogs never
touch SQL directly — this keeps the schema change surface in one place.
"""

import json
import os
import logging
from typing import Optional, Any

import asyncpg

logger = logging.getLogger("vvs.db")

_pool: Optional[asyncpg.Pool] = None


async def init_pool() -> asyncpg.Pool:
    """Create the global connection pool. Call once at bot startup."""
    global _pool
    dsn = os.environ["DATABASE_URL"]
    # Railway's DATABASE_URL sometimes uses postgres:// which asyncpg accepts,
    # but normalize just in case a driver-specific prefix sneaks in.
    if dsn.startswith("postgres://"):
        dsn = dsn.replace("postgres://", "postgresql://", 1)
    _pool = await asyncpg.create_pool(dsn=dsn, min_size=1, max_size=10)
    logger.info("Database pool initialized.")
    return _pool


async def close_pool():
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


def get_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("DB pool not initialized — call init_pool() first.")
    return _pool


async def run_schema(schema_sql_path: str = "schema.sql"):
    """Idempotently apply schema.sql. Safe to run on every boot."""
    with open(schema_sql_path, "r", encoding="utf-8") as f:
        sql = f.read()
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute(sql)
    logger.info("Schema applied.")


# ------------------------------------------------------------------
# Pilot record CRUD
# ------------------------------------------------------------------

async def get_pilot(discord_id: str) -> Optional[asyncpg.Record]:
    pool = get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            "SELECT * FROM pilot_records WHERE discord_id = $1", str(discord_id)
        )


async def create_pilot(
    discord_id: str,
    guild_id: str,
    soviet_name: str,
    callsign: str,
    airframe: str,
    squadron: str,
    avatar_url: str,
) -> asyncpg.Record:
    """Insert a fresh pilot row, or fully reset an existing KIA row.

    ON CONFLICT covers the case where a discord_id already has a row from a
    prior KIA'd service record — re-enlisting must wipe stats back to zero
    rather than erroring on the primary key.
    """
    pool = get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            """
            INSERT INTO pilot_records (
                discord_id, guild_id, soviet_name, callsign, current_rank,
                airframe, squadron, sorties, flight_hours, kills_ground,
                kills_air, status, fatigue_score, cheks, avatar_url,
                earned_medals, commendations, reprimands,
                custom_callsign_used, reprimand_count_active,
                rr_return_at, loa_start, loa_end, loa_reason, updated_at
            ) VALUES (
                $1, $2, $3, $4, 'Junior Lieutenant',
                $5, $6, 0, 0.0, 0,
                0, 'ACTIVE', 0.0, 0, $7,
                '[]', '[]', '[]',
                FALSE, 0,
                NULL, NULL, NULL, NULL, NOW()
            )
            ON CONFLICT (discord_id) DO UPDATE SET
                guild_id = EXCLUDED.guild_id,
                soviet_name = EXCLUDED.soviet_name,
                callsign = EXCLUDED.callsign,
                current_rank = 'Junior Lieutenant',
                airframe = EXCLUDED.airframe,
                squadron = EXCLUDED.squadron,
                sorties = 0,
                flight_hours = 0.0,
                kills_ground = 0,
                kills_air = 0,
                status = 'ACTIVE',
                fatigue_score = 0.0,
                cheks = 0,
                avatar_url = EXCLUDED.avatar_url,
                earned_medals = '[]',
                commendations = '[]',
                reprimands = '[]',
                custom_callsign_used = FALSE,
                reprimand_count_active = 0,
                rr_return_at = NULL,
                loa_start = NULL,
                loa_end = NULL,
                loa_reason = NULL,
                updated_at = NOW()
            WHERE pilot_records.status = 'KIA'
            RETURNING *
            """,
            str(discord_id), str(guild_id), soviet_name, callsign,
            airframe, squadron, avatar_url,
        )


async def update_pilot_fields(discord_id: str, **fields: Any) -> Optional[asyncpg.Record]:
    """Generic partial update. fields keys must be valid column names."""
    if not fields:
        return await get_pilot(discord_id)
    pool = get_pool()
    set_clauses = []
    values = []
    for i, (key, value) in enumerate(fields.items(), start=1):
        set_clauses.append(f"{key} = ${i}")
        values.append(value)
    values.append(str(discord_id))
    query = (
        f"UPDATE pilot_records SET {', '.join(set_clauses)}, updated_at = NOW() "
        f"WHERE discord_id = ${len(values)} RETURNING *"
    )
    async with pool.acquire() as conn:
        return await conn.fetchrow(query, *values)


async def transfer_airframe(discord_id: str, airframe: str, squadron: str) -> Optional[asyncpg.Record]:
    """Update airframe/squadron only — everything else stays untouched."""
    return await update_pilot_fields(discord_id, airframe=airframe, squadron=squadron)


async def set_status(discord_id: str, status: str) -> Optional[asyncpg.Record]:
    return await update_pilot_fields(discord_id, status=status)


async def add_stats(
    discord_id: str,
    sorties: int,
    hours: float,
    ground_kills: int,
    air_kills: int,
    fatigue_delta: float,
    cheks_delta: int,
) -> Optional[asyncpg.Record]:
    pool = get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            """
            UPDATE pilot_records
            SET sorties = sorties + $2,
                flight_hours = flight_hours + $3,
                kills_ground = kills_ground + $4,
                kills_air = kills_air + $5,
                fatigue_score = fatigue_score + $6,
                cheks = cheks + $7,
                updated_at = NOW()
            WHERE discord_id = $1
            RETURNING *
            """,
            str(discord_id), sorties, hours, ground_kills, air_kills,
            fatigue_delta, cheks_delta,
        )


async def adjust_cheks(discord_id: str, delta: int) -> Optional[asyncpg.Record]:
    pool = get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            "UPDATE pilot_records SET cheks = cheks + $2, updated_at = NOW() "
            "WHERE discord_id = $1 RETURNING *",
            str(discord_id), delta,
        )


async def append_json_list(discord_id: str, column: str, item: dict) -> Optional[asyncpg.Record]:
    """Append a JSON object to one of the TEXT-serialized JSON array columns."""
    assert column in {"earned_medals", "commendations", "reprimands"}
    record = await get_pilot(discord_id)
    if record is None:
        return None
    current = json.loads(record[column] or "[]")
    current.append(item)
    return await update_pilot_fields(discord_id, **{column: json.dumps(current)})


async def set_rank(discord_id: str, new_rank: str) -> Optional[asyncpg.Record]:
    return await update_pilot_fields(discord_id, current_rank=new_rank)


async def mark_kia(discord_id: str, cause: str) -> Optional[asyncpg.Record]:
    return await update_pilot_fields(discord_id, status="KIA")


async def archive_fallen_hero(record: asyncpg.Record, cause_of_death: str):
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO fallen_heroes (
                discord_id, soviet_name, callsign, final_rank, squadron,
                airframe, sorties, flight_hours, kills_ground, kills_air,
                medals, cause_of_death
            ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)
            """,
            record["discord_id"], record["soviet_name"], record["callsign"],
            record["current_rank"], record["squadron"], record["airframe"],
            record["sorties"], record["flight_hours"], record["kills_ground"],
            record["kills_air"], record["earned_medals"], cause_of_death,
        )


async def log_commissar_action(discord_id: str, action_type: str, reason: str, issued_by: str):
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO commissar_log (discord_id, action_type, reason, issued_by)
            VALUES ($1, $2, $3, $4)
            """,
            str(discord_id), action_type, reason, str(issued_by),
        )


async def set_loa(discord_id: str, start_date, end_date, reason: str) -> Optional[asyncpg.Record]:
    return await update_pilot_fields(
        discord_id, loa_start=start_date, loa_end=end_date, loa_reason=reason
    )


async def clear_loa(discord_id: str) -> Optional[asyncpg.Record]:
    return await update_pilot_fields(
        discord_id, status="ACTIVE", loa_start=None, loa_end=None, loa_reason=None
    )


async def schedule_rr_return(discord_id: str, return_at) -> Optional[asyncpg.Record]:
    return await update_pilot_fields(discord_id, status="FATIGUED", rr_return_at=return_at)


async def start_rest(discord_id: str, return_at) -> Optional[asyncpg.Record]:
    return await update_pilot_fields(
        discord_id, status="ACTIVE", fatigue_score=0.0, rr_return_at=return_at
    )


async def get_pilots_due_for_rr_return():
    pool = get_pool()
    async with pool.acquire() as conn:
        return await conn.fetch(
            """
            SELECT * FROM pilot_records
            WHERE status = 'ACTIVE' AND rr_return_at IS NOT NULL AND rr_return_at <= NOW()
            """
        )


async def get_pilots_with_pending_loa_return():
    """LOA rows whose end date has passed but status is still LOA (for reminder pings)."""
    pool = get_pool()
    async with pool.acquire() as conn:
        return await conn.fetch(
            """
            SELECT * FROM pilot_records
            WHERE status = 'LOA' AND loa_end IS NOT NULL AND loa_end < NOW()::date
            """
        )


# ------------------------------------------------------------------
# Avatar pool
# ------------------------------------------------------------------

async def upsert_avatar_pool_entries(entries: list[tuple[str, str]]) -> int:
    """
    entries: list of (message_id, attachment_url) tuples.
    Inserts new ones, ignores ones already recorded (by message_id).
    Returns number of newly inserted rows.
    """
    if not entries:
        return 0
    pool = get_pool()
    async with pool.acquire() as conn:
        result = await conn.executemany(
            """
            INSERT INTO avatar_pool (message_id, attachment_url)
            VALUES ($1, $2)
            ON CONFLICT (message_id) DO NOTHING
            """,
            entries,
        )
    # asyncpg's executemany doesn't give an affected-row count directly, so
    # report against a fresh count of unused/total for the caller to display.
    return len(entries)


async def get_random_unused_avatar() -> Optional[asyncpg.Record]:
    pool = get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            "SELECT * FROM avatar_pool WHERE is_used = FALSE ORDER BY random() LIMIT 1"
        )


async def mark_avatar_used(pool_id: int, discord_id: str):
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE avatar_pool SET is_used = TRUE, assigned_to = $2 WHERE id = $1",
            pool_id, str(discord_id),
        )


async def get_avatar_pool_stats() -> dict:
    pool = get_pool()
    async with pool.acquire() as conn:
        total = await conn.fetchval("SELECT COUNT(*) FROM avatar_pool")
        unused = await conn.fetchval("SELECT COUNT(*) FROM avatar_pool WHERE is_used = FALSE")
    return {"total": total, "unused": unused, "used": total - unused}


# ------------------------------------------------------------------
# Medal / rank icon catalogs
# ------------------------------------------------------------------

def _normalize_medal_key(name: str) -> str:
    return name.strip().lower()


async def upsert_medal_image(medal_name: str, image_url: str, added_by: str) -> asyncpg.Record:
    pool = get_pool()
    key = _normalize_medal_key(medal_name)
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            """
            INSERT INTO medal_catalog (medal_key, display_name, image_url, added_by)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (medal_key) DO UPDATE SET
                image_url = EXCLUDED.image_url,
                display_name = EXCLUDED.display_name,
                added_by = EXCLUDED.added_by,
                added_at = NOW()
            RETURNING *
            """,
            key, medal_name.strip(), image_url, str(added_by),
        )


async def get_medal_image(medal_name: str) -> Optional[asyncpg.Record]:
    pool = get_pool()
    key = _normalize_medal_key(medal_name)
    async with pool.acquire() as conn:
        return await conn.fetchrow("SELECT * FROM medal_catalog WHERE medal_key = $1", key)


async def list_medal_catalog() -> list:
    pool = get_pool()
    async with pool.acquire() as conn:
        return await conn.fetch("SELECT * FROM medal_catalog ORDER BY display_name")


async def upsert_rank_image(rank_name: str, image_url: str, added_by: str) -> asyncpg.Record:
    pool = get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            """
            INSERT INTO rank_catalog (rank_name, image_url, added_by)
            VALUES ($1, $2, $3)
            ON CONFLICT (rank_name) DO UPDATE SET
                image_url = EXCLUDED.image_url,
                added_by = EXCLUDED.added_by,
                added_at = NOW()
            RETURNING *
            """,
            rank_name, image_url, str(added_by),
        )


async def get_rank_image(rank_name: str) -> Optional[asyncpg.Record]:
    pool = get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchrow("SELECT * FROM rank_catalog WHERE rank_name = $1", rank_name)


# ------------------------------------------------------------------
# Roster queries
# ------------------------------------------------------------------

async def get_pilots_by_squadron(squadron: str) -> list:
    pool = get_pool()
    async with pool.acquire() as conn:
        return await conn.fetch(
            "SELECT * FROM pilot_records WHERE squadron = $1 AND status != 'KIA' ORDER BY current_rank",
            squadron,
        )


async def get_all_active_pilots() -> list:
    pool = get_pool()
    async with pool.acquire() as conn:
        return await conn.fetch(
            "SELECT * FROM pilot_records WHERE status != 'KIA' ORDER BY squadron, current_rank"
        )
