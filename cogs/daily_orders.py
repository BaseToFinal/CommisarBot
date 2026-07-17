import datetime
import json
import logging

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands, tasks

import db
import data
from config import Config, has_commissar_perms

logger = logging.getLogger("vvs.daily_orders")


# ------------------------------------------------------------------
# Real-world METAR (independent of the DCS server entirely — this is
# genuinely automatic and doesn't depend on any access we don't have)
# ------------------------------------------------------------------

async def fetch_real_metar(icao_code: str):
    """
    Fetches the current raw METAR for a real-world airport from NOAA's
    public aviationweather.gov API (no key required, no rate-limit auth
    needed for light use). Returns the raw METAR string, or None on any
    failure — callers should treat None as "unavailable" and degrade
    gracefully rather than erroring the whole command.
    """
    url = f"https://aviationweather.gov/api/data/metar?ids={icao_code}&format=raw"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status != 200:
                    logger.warning("METAR fetch returned status %s for %s", resp.status, icao_code)
                    return None
                text = (await resp.text()).strip()
                return text if text else None
    except Exception:
        logger.exception("METAR fetch failed for %s", icao_code)
        return None


# ------------------------------------------------------------------
# DCSServerBot status embed parsing (DORMANT unless DCS_STATUS_CHANNEL_ID
# is configured and reachable — most setups won't have this, since it
# requires the bot to be a member of whatever server hosts DCSServerBot's
# status channel. Left in place in case that ever changes; falls back
# gracefully to the manual /set_daily_conditions staging otherwise.)
# ------------------------------------------------------------------

async def fetch_dcs_status_fields(bot: discord.Client):
    """
    Reads DCSServerBot's live status embed from the configured channel and
    returns a dict of {normalized_field_name: value}. DCSServerBot edits a
    single persistent message rather than posting new ones, so this scans
    the most recent messages in the channel for the first one with embeds.

    Returns None if the channel isn't configured/reachable, or no embed is
    found. Field-name matching downstream is done via fuzzy substring
    lookup (see _get_field) since exact DCSServerBot embed formatting may
    shift between versions.
    """
    if not Config.DCS_STATUS_CHANNEL_ID:
        return None

    channel = bot.get_channel(Config.DCS_STATUS_CHANNEL_ID)
    if channel is None:
        try:
            channel = await bot.fetch_channel(Config.DCS_STATUS_CHANNEL_ID)
        except discord.HTTPException:
            logger.warning("Could not access DCS_STATUS_CHANNEL_ID.")
            return None

    try:
        async for message in channel.history(limit=20):
            if message.embeds:
                embed = message.embeds[0]
                fields = {}
                if embed.title:
                    fields["_title"] = embed.title
                if embed.description:
                    fields["_description"] = embed.description
                for f in embed.fields:
                    fields[f.name.strip().lower()] = f.value.strip()
                return fields
    except discord.Forbidden:
        logger.warning("Missing permission to read DCS_STATUS_CHANNEL_ID history.")
        return None

    return None


def _get_field(fields, candidates):
    """Exact-name lookup first, then substring fallback. Returns 'N/A' if
    nothing matches any candidate."""
    for c in candidates:
        if c in fields:
            return fields[c]
    for name, value in fields.items():
        if any(c in name for c in candidates):
            return value
    return "N/A"


def summarize_dcs_status(fields):
    """Extract the specific values we care about from the raw field dict."""
    return {
        "server_name": fields.get("_title", "Unknown Server"),
        "map": _get_field(fields, ["map"]),
        "mission_datetime": _get_field(fields, ["date / time in mission", "date/time in mission"]),
        "slots": _get_field(fields, ["slots"]),
        "runtime": _get_field(fields, ["runtime"]),
        "server_ip": _get_field(fields, ["server-ip / port", "server-ip/port"]),
        "temperature": _get_field(fields, ["temperature"]),
        "clouds": _get_field(fields, ["clouds"]),
        "visibility": _get_field(fields, ["visibility"]),
        "qnh": _get_field(fields, ["qnh (qff)", "qnh"]),
        "cloudbase": _get_field(fields, ["cloudbase"]),
        "wind": _get_field(fields, ["wind"]),
    }


# ------------------------------------------------------------------
# Daily Orders embed construction
# ------------------------------------------------------------------

async def build_daily_orders_embed(bot: discord.Client) -> discord.Embed:
    state = await db.get_daily_orders_state()

    # Primary conditions source: manually staged text (reliable, always
    # available). The DCSServerBot channel read is a bonus if configured
    # and reachable, but most setups won't have that access.
    raw_fields = await fetch_dcs_status_fields(bot)
    if raw_fields:
        s = summarize_dcs_status(raw_fields)
        map_name = s["map"]
        mission_datetime = s["mission_datetime"]
        auto_weather_text = (
            f"Temp: {s['temperature']} | Wind: {s['wind']}\n"
            f"Clouds: {s['clouds']} (base {s['cloudbase']})\n"
            f"Visibility: {s['visibility']} | QNH: {s['qnh']}"
        )
    else:
        map_name = None
        mission_datetime = None
        auto_weather_text = None

    conditions_text = state["conditions_text"]
    if auto_weather_text:
        conditions_display = f"Map: **{map_name}** | Mission Time: **{mission_datetime}**\n{auto_weather_text}"
    elif conditions_text:
        conditions_display = conditions_text
    else:
        conditions_display = (
            "Not set. Use `/set_daily_conditions` to add server/mission/weather "
            "info before the next post."
        )

    # Real-world METAR — fully independent of the DCS server, genuinely
    # automatic, but clearly a real-world reference rather than in-game
    # scripted weather.
    metar = await fetch_real_metar(Config.METAR_ICAO_CODE)
    metar_display = metar if metar else "Unavailable"

    manual_crew_ids = json.loads(state["manual_crew_ids"] or "[]")
    if manual_crew_ids:
        records = []
        for uid in manual_crew_ids:
            r = await db.get_pilot(uid)
            if r:
                records.append(r)
        crew_source_note = "Manually Assigned"
    else:
        records = await db.get_all_active_pilots()
        crew_source_note = "Full Active Roster"

    crew_lines = [
        f'• {r["soviet_name"]} "{r["callsign"]}" — {r["airframe"] or "Unassigned"}'
        for r in records
    ]
    crew_text = "\n".join(crew_lines) if crew_lines else "No pilots assigned."
    if len(crew_text) > 1000:
        crew_text = crew_text[:1000] + "\n…(truncated)"

    objective = state["objective"] or data.DEFAULT_MISSION_OBJECTIVE
    readiness = state["readiness_condition"] or data.DEFAULT_READINESS

    embed = discord.Embed(
        title=f"Боевой приказ №{state['mission_number']} — Daily Orders",
        color=discord.Color.dark_red(),
    )
    embed.add_field(name="Server / Mission Conditions", value=conditions_display, inline=False)
    embed.add_field(name=f"Real-World Reference Weather ({Config.METAR_ICAO_CODE})", value=metar_display, inline=False)
    embed.add_field(name="Readiness Condition", value=readiness, inline=False)
    embed.add_field(name="Mission Objective", value=objective, inline=False)
    embed.add_field(name=f"Assigned Crews ({crew_source_note})", value=crew_text, inline=False)
    embed.set_footer(text=f"Generated {datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    return embed


class DailyOrders(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        if Config.DAILY_ORDERS_CHANNEL_ID:
            self.scheduled_daily_orders.change_interval(
                time=datetime.time(hour=Config.DAILY_ORDERS_POST_HOUR_UTC, tzinfo=datetime.timezone.utc)
            )
            self.scheduled_daily_orders.start()

    def cog_unload(self):
        if self.scheduled_daily_orders.is_running():
            self.scheduled_daily_orders.cancel()

    @tasks.loop(hours=24)
    async def scheduled_daily_orders(self):
        if not Config.DAILY_ORDERS_CHANNEL_ID:
            return
        channel = self.bot.get_channel(Config.DAILY_ORDERS_CHANNEL_ID)
        if channel is None:
            logger.warning("DAILY_ORDERS_CHANNEL_ID not reachable; skipping scheduled post.")
            return
        try:
            embed = await build_daily_orders_embed(self.bot)
            await channel.send(embed=embed)
            state = await db.get_daily_orders_state()
            await db.reset_daily_orders_state_after_post(state["mission_number"] + 1)
            logger.info("Posted scheduled Daily Orders.")
        except Exception:
            logger.exception("Failed to post scheduled Daily Orders.")

    @scheduled_daily_orders.before_loop
    async def before_scheduled_daily_orders(self):
        await self.bot.wait_until_ready()

    # ------------------------------------------------------------------
    # On-demand server status
    # ------------------------------------------------------------------

    @app_commands.command(name="server_status", description="Check DCS server conditions and real-world reference weather.")
    async def server_status(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)

        raw_fields = await fetch_dcs_status_fields(self.bot)
        metar = await fetch_real_metar(Config.METAR_ICAO_CODE)

        embed = discord.Embed(title="Server Status", color=discord.Color.dark_teal())

        if raw_fields:
            s = summarize_dcs_status(raw_fields)
            embed.add_field(name="Map", value=s["map"], inline=True)
            embed.add_field(name="Mission Time", value=s["mission_datetime"], inline=True)
            embed.add_field(name="Slots", value=s["slots"], inline=True)
            embed.add_field(name="Runtime", value=s["runtime"], inline=True)
            embed.add_field(name="Server", value=s["server_ip"], inline=True)
            embed.add_field(name="\u200b", value="\u200b", inline=True)
            embed.add_field(
                name="Weather",
                value=(
                    f"Temp: {s['temperature']} | Wind: {s['wind']}\n"
                    f"Clouds: {s['clouds']} (base {s['cloudbase']})\n"
                    f"Visibility: {s['visibility']} | QNH: {s['qnh']}"
                ),
                inline=False,
            )
        else:
            state = await db.get_daily_orders_state()
            embed.add_field(
                name="Server / Mission Conditions",
                value=state["conditions_text"] or "Not set. Use `/set_daily_conditions` to add it manually.",
                inline=False,
            )

        embed.add_field(
            name=f"Real-World Reference Weather ({Config.METAR_ICAO_CODE})",
            value=metar if metar else "Unavailable",
            inline=False,
        )
        await interaction.followup.send(embed=embed)

    # ------------------------------------------------------------------
    # Daily Orders staging commands (admin)
    # ------------------------------------------------------------------

    @app_commands.command(name="set_mission_objective", description="[Admin] Set the objective for the next Daily Orders.")
    async def set_mission_objective(self, interaction: discord.Interaction, objective: str):
        if not has_commissar_perms(interaction.user):
            await interaction.response.send_message("Only Admins/Commissars may use this command.", ephemeral=True)
            return
        await db.update_daily_orders_state(objective=objective)
        await interaction.response.send_message(f"Mission objective staged:\n> {objective}", ephemeral=True)

    @app_commands.command(
        name="set_daily_conditions",
        description="[Admin] Manually stage server/mission/weather info for the next Daily Orders.",
    )
    async def set_daily_conditions(self, interaction: discord.Interaction, conditions: str):
        if not has_commissar_perms(interaction.user):
            await interaction.response.send_message("Only Admins/Commissars may use this command.", ephemeral=True)
            return
        await db.update_daily_orders_state(conditions_text=conditions)
        await interaction.response.send_message(f"Conditions staged:\n> {conditions}", ephemeral=True)

    @app_commands.command(name="set_readiness", description="[Admin] Set the readiness condition for the next Daily Orders.")
    @app_commands.choices(
        condition=[app_commands.Choice(name=c, value=c) for c in data.READINESS_CONDITIONS]
    )
    async def set_readiness(self, interaction: discord.Interaction, condition: app_commands.Choice[str]):
        if not has_commissar_perms(interaction.user):
            await interaction.response.send_message("Only Admins/Commissars may use this command.", ephemeral=True)
            return
        await db.update_daily_orders_state(readiness_condition=condition.value)
        await interaction.response.send_message(f"Readiness condition staged: {condition.value}", ephemeral=True)

    @app_commands.command(name="assign_crew", description="[Admin] Manually assign a pilot to the next Daily Orders crew list.")
    async def assign_crew(self, interaction: discord.Interaction, user: discord.Member):
        if not has_commissar_perms(interaction.user):
            await interaction.response.send_message("Only Admins/Commissars may use this command.", ephemeral=True)
            return
        state = await db.get_daily_orders_state()
        crew_ids = json.loads(state["manual_crew_ids"] or "[]")
        uid = str(user.id)
        if uid not in crew_ids:
            crew_ids.append(uid)
        await db.update_daily_orders_state(manual_crew_ids=json.dumps(crew_ids))
        await interaction.response.send_message(
            f"{user.mention} added to the manual crew list for the next Daily Orders "
            f"({len(crew_ids)} assigned).",
            ephemeral=True,
        )

    @app_commands.command(name="unassign_crew", description="[Admin] Remove a pilot from the manual Daily Orders crew list.")
    async def unassign_crew(self, interaction: discord.Interaction, user: discord.Member):
        if not has_commissar_perms(interaction.user):
            await interaction.response.send_message("Only Admins/Commissars may use this command.", ephemeral=True)
            return
        state = await db.get_daily_orders_state()
        crew_ids = json.loads(state["manual_crew_ids"] or "[]")
        uid = str(user.id)
        if uid in crew_ids:
            crew_ids.remove(uid)
        await db.update_daily_orders_state(manual_crew_ids=json.dumps(crew_ids))
        await interaction.response.send_message(f"{user.mention} removed from the manual crew list.", ephemeral=True)

    @app_commands.command(name="clear_crew_override", description="[Admin] Revert to auto (full active roster) for the next Daily Orders.")
    async def clear_crew_override(self, interaction: discord.Interaction):
        if not has_commissar_perms(interaction.user):
            await interaction.response.send_message("Only Admins/Commissars may use this command.", ephemeral=True)
            return
        await db.update_daily_orders_state(manual_crew_ids="[]")
        await interaction.response.send_message(
            "Crew override cleared — next Daily Orders will use the full active roster.",
            ephemeral=True,
        )

    @app_commands.command(name="daily_orders", description="[Admin] Generate and post Daily Orders now.")
    async def daily_orders(self, interaction: discord.Interaction):
        if not has_commissar_perms(interaction.user):
            await interaction.response.send_message("Only Admins/Commissars may use this command.", ephemeral=True)
            return
        if not Config.DAILY_ORDERS_CHANNEL_ID:
            await interaction.response.send_message(
                "DAILY_ORDERS_CHANNEL_ID is not configured.", ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)

        channel = self.bot.get_channel(Config.DAILY_ORDERS_CHANNEL_ID)
        if channel is None:
            await interaction.followup.send("Could not access DAILY_ORDERS_CHANNEL_ID.", ephemeral=True)
            return

        embed = await build_daily_orders_embed(self.bot)
        await channel.send(embed=embed)

        state = await db.get_daily_orders_state()
        await db.reset_daily_orders_state_after_post(state["mission_number"] + 1)

        await interaction.followup.send(f"Daily Orders posted to {channel.mention}.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(DailyOrders(bot))
