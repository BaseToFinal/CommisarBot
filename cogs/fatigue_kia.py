import datetime
import json
import logging

import discord
from discord import app_commands
from discord.ext import commands, tasks

import db
import data
from config import Config, has_commissar_perms

logger = logging.getLogger("vvs.fatigue_kia")


class FatigueKIA(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.rr_check_loop.start()

    def cog_unload(self):
        self.rr_check_loop.cancel()

    # ------------------------------------------------------------------
    # /mark_kia — admin-only permadeath
    # ------------------------------------------------------------------

    @app_commands.command(name="mark_kia", description="[Admin] Mark a pilot KIA/MIA. Permanent.")
    @app_commands.describe(user="The pilot to mark KIA", details="Details of the crash / loss")
    async def mark_kia(self, interaction: discord.Interaction, user: discord.Member, details: str):
        if not has_commissar_perms(interaction.user):
            await interaction.response.send_message(
                "Only Admins/Commissars may use this command.", ephemeral=True
            )
            return

        record = await db.get_pilot(user.id)
        if record is None or record["status"] == "KIA":
            await interaction.response.send_message(
                "That pilot does not have an active service record.", ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)

        # Archive the full service record before it gets wiped by re-enlistment.
        await db.archive_fallen_hero(record, details)
        await db.mark_kia(user.id, details)
        await db.log_commissar_action(user.id, "KIA", details, interaction.user.id)

        # Nickname + role cleanup
        try:
            new_nick = f'[KIA] {user.display_name}'[:32]
            await user.edit(nick=new_nick, reason="Marked KIA")
        except discord.Forbidden:
            logger.warning("Missing permission to rename %s on KIA", user.id)

        guild = interaction.guild
        roles_to_remove = []
        for role_id in list(Config.SQUADRON_ROLE_IDS.values()) + [Config.ACTIVE_FLYER_ROLE_ID]:
            if not role_id:
                continue
            role = guild.get_role(role_id)
            if role and role in user.roles:
                roles_to_remove.append(role)
        if roles_to_remove:
            try:
                await user.remove_roles(*roles_to_remove, reason="Marked KIA")
            except discord.Forbidden:
                logger.warning("Missing permission to remove roles for %s on KIA", user.id)

        # Memorial embed
        memorial_channel = self.bot.get_channel(Config.FALLEN_HEROES_CHANNEL_ID)
        medals = json.loads(record["earned_medals"] or "[]")
        embed = discord.Embed(
            title="ПАМЯТИ ПАВШЕГО ТОВАРИЩА",
            description=(
                f'**{record["soviet_name"]}** "{record["callsign"]}"\n'
                f'{record["current_rank"]}, {record["squadron"] or "Unassigned"}'
            ),
            color=discord.Color.dark_red(),
        )
        if record["avatar_url"]:
            embed.set_thumbnail(url=record["avatar_url"])
        embed.add_field(name="Airframe", value=record["airframe"] or "Unknown", inline=True)
        embed.add_field(name="Flight Hours", value=f'{record["flight_hours"]:.1f}', inline=True)
        embed.add_field(name="Sorties", value=str(record["sorties"]), inline=True)
        embed.add_field(
            name="Kills (Air / Ground)",
            value=f'{record["kills_air"]} / {record["kills_ground"]}',
            inline=True,
        )
        embed.add_field(name="Medals", value=", ".join(medals) if medals else "None", inline=False)
        embed.add_field(name="Cause of Loss", value=details, inline=False)
        embed.set_footer(text=f"Service record archived. Rest in peace, Comrade.")

        if memorial_channel:
            await memorial_channel.send(embed=embed)

        await interaction.followup.send(
            f"{user.mention} has been marked KIA. Their memorial has been posted. "
            f"They may `/enlist` again to begin a new service record.",
            ephemeral=True,
        )

    # ------------------------------------------------------------------
    # /rest — self-service R&R
    # ------------------------------------------------------------------

    @app_commands.command(name="rest", description="Begin a mandatory 48-hour R&R period to clear fatigue.")
    async def rest(self, interaction: discord.Interaction):
        record = await db.get_pilot(interaction.user.id)
        if record is None or record["status"] == "KIA":
            await interaction.response.send_message(
                "You do not have an active service record.", ephemeral=True
            )
            return

        return_at = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(
            hours=data.RR_DURATION_HOURS
        )
        await db.start_rest(interaction.user.id, return_at)

        await interaction.response.send_message(
            f"You have been granted {data.RR_DURATION_HOURS}-hour R&R leave. Your fatigue score "
            f"has been reset to 0 and your status is ACTIVE. Fly safe, Comrade.",
            ephemeral=True,
        )

    @tasks.loop(minutes=15)
    async def rr_check_loop(self):
        """Background sweep — kept for symmetry/logging even though /rest
        already clears fatigue immediately. Also useful if R&R is later
        changed to block flying for the full 48 hours rather than resetting
        instantly."""
        try:
            due = await db.get_pilots_due_for_rr_return()
            for record in due:
                await db.update_pilot_fields(record["discord_id"], rr_return_at=None)
        except Exception:
            logger.exception("Error in rr_check_loop")

    @rr_check_loop.before_loop
    async def before_rr_check_loop(self):
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot):
    await bot.add_cog(FatigueKIA(bot))
