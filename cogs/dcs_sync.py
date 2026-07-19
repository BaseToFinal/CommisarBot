"""
Applies auto-tracked DCS sortie reports (from the Cold War EFB's bridge.js
sortie tracker, via the standalone ingest service) to pilot_records.

Deliberately no approval step here, unlike kill_claims — sorties, flight
hours, takeoffs, and landings are auto-credited immediately per Donald's
call. Kills stay human-verified through the existing #killclaims workflow;
this cog never touches kills_ground/kills_air.

This cog only reads from the DB (dcs_sortie_reports) — it never receives
network traffic directly. The standalone ingest service is the only thing
that talks to the EFB in the field, and it writes PENDING rows into the
same Postgres database CommissarBot already uses. That split exists
because CommissarBot runs as a Railway worker (no exposed port) rather
than a web service; polling avoids needing to change that.
"""

import logging

import discord
from discord.ext import commands, tasks

import db
from config import Config

logger = logging.getLogger("vvs.dcs_sync")

POLL_INTERVAL_SECONDS = 30


class DCSSync(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.sync_loop.start()

    def cog_unload(self):
        self.sync_loop.cancel()

    @tasks.loop(seconds=POLL_INTERVAL_SECONDS)
    async def sync_loop(self):
        try:
            pending = await db.get_pending_sortie_reports()
        except Exception:
            logger.exception("Error fetching pending sortie reports")
            return

        for report in pending:
            try:
                await self._apply_report(report)
            except Exception:
                logger.exception("Error applying sortie report #%s", report["id"])

    async def _apply_report(self, report):
        discord_id = report["discord_id"]
        pilot = await db.get_pilot(discord_id)
        if pilot is None or pilot["status"] == "KIA":
            # No active service record to credit (e.g. token belongs to a
            # pilot who's since gone KIA/re-enlisted) — reject rather than
            # leave it PENDING forever, so a bad token can't wedge the loop.
            await db.reject_sortie_report(report["id"])
            logger.info(
                "Rejected sortie report #%s: no active pilot for discord_id=%s",
                report["id"], discord_id,
            )
            return

        updated = await db.apply_sortie_report(
            report["id"],
            discord_id,
            sorties=report["sorties_delta"],
            hours=report["flight_hours_delta"],
            takeoffs=report["takeoffs_delta"],
            landings=report["landings_delta"],
        )
        if updated is None:
            # Already processed by a prior tick — nothing to do.
            return

        logger.info(
            "Applied sortie report #%s for %s: +%s sortie(s), +%.1fh, +%s T/O, +%s landing(s)",
            report["id"], discord_id, report["sorties_delta"],
            report["flight_hours_delta"], report["takeoffs_delta"], report["landings_delta"],
        )

        if Config.COMMISSAR_LOG_CHANNEL_ID:
            channel = self.bot.get_channel(Config.COMMISSAR_LOG_CHANNEL_ID)
            if channel is not None:
                airframe = report["airframe"] or "unknown airframe"
                try:
                    await channel.send(
                        f'Sortie logged for <@{discord_id}> ({airframe}): '
                        f'+{report["sorties_delta"]} sortie, '
                        f'+{report["flight_hours_delta"]:.1f}h, '
                        f'+{report["takeoffs_delta"]} T/O, '
                        f'+{report["landings_delta"]} landing(s).'
                    )
                except discord.HTTPException:
                    logger.warning("Could not post sortie log message.")

    @sync_loop.before_loop
    async def before_sync_loop(self):
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot):
    await bot.add_cog(DCSSync(bot))
