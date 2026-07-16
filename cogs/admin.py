import logging

import discord
from discord import app_commands
from discord.ext import commands

import db
import data
from utils import format_nickname
from config import has_commissar_perms

logger = logging.getLogger("vvs.admin")


class AdminCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="promote", description="[Admin] Promote a pilot to a new rank.")
    @app_commands.describe(user="The pilot to promote", new_rank="The new rank")
    @app_commands.choices(
        new_rank=[app_commands.Choice(name=r, value=r) for r in data.RANK_PROGRESSION]
    )
    async def promote(self, interaction: discord.Interaction, user: discord.Member, new_rank: app_commands.Choice[str]):
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

        rank_value = new_rank.value
        await db.set_rank(user.id, rank_value)
        await db.log_commissar_action(user.id, "PROMOTE", f"Promoted to {rank_value}", interaction.user.id)

        last_name = record["soviet_name"].split()[-1]
        prefix_tag = "[LOA]" if record["status"] == "LOA" else ""
        new_nick = format_nickname(rank_value, record["callsign"], last_name, prefix_tag=prefix_tag)
        try:
            await user.edit(nick=new_nick, reason=f"Promoted to {rank_value}")
        except discord.Forbidden:
            logger.warning("Missing permission to rename %s on promotion", user.id)

        embed = discord.Embed(
            title="Promotion Order",
            description=f'{user.mention} has been promoted to **{rank_value}**.',
            color=discord.Color.blue(),
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="award", description="[Admin] Award a medal to a pilot.")
    @app_commands.describe(user="The pilot to award", medal_id="Medal identifier (e.g. 'Red Star', 'Order of Lenin')")
    async def award(self, interaction: discord.Interaction, user: discord.Member, medal_id: str):
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

        import json
        medals = json.loads(record["earned_medals"] or "[]")
        medals.append(medal_id)
        await db.update_pilot_fields(user.id, earned_medals=json.dumps(medals))
        await db.log_commissar_action(user.id, "AWARD", medal_id, interaction.user.id)

        embed = discord.Embed(
            title="Decoration Awarded",
            description=f'{user.mention} has been awarded the **{medal_id}**.',
            color=discord.Color.gold(),
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="logstats", description="[Admin] Log sortie/flight-hour/kill stats for a pilot.")
    @app_commands.describe(
        user="The pilot to update",
        sorties="Sorties flown to add",
        hours="Flight hours to add",
        ground_kills="Ground kills to add",
        air_kills="Air kills to add",
    )
    async def logstats(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        sorties: int,
        hours: float,
        ground_kills: int = 0,
        air_kills: int = 0,
    ):
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

        if sorties < 0 or hours < 0 or ground_kills < 0 or air_kills < 0:
            await interaction.response.send_message("Values must be non-negative.", ephemeral=True)
            return

        fatigue_delta = hours * data.FATIGUE_PER_HOUR
        cheks_delta = (sorties * data.CHEKS_PER_SORTIE) + (
            (ground_kills + air_kills) * data.CHEKS_PER_KILL
        )

        updated = await db.add_stats(
            user.id, sorties, hours, ground_kills, air_kills, fatigue_delta, cheks_delta
        )

        newly_fatigued = False
        if updated["fatigue_score"] >= data.FATIGUE_THRESHOLD and updated["status"] == "ACTIVE":
            await db.set_status(user.id, "FATIGUED")
            newly_fatigued = True

            guild = interaction.guild
            from config import Config
            roles_to_remove = []
            for role_id in list(Config.SQUADRON_ROLE_IDS.values()) + [Config.ACTIVE_FLYER_ROLE_ID]:
                if not role_id:
                    continue
                role = guild.get_role(role_id)
                if role and role in user.roles:
                    roles_to_remove.append(role)
            if roles_to_remove:
                try:
                    await user.remove_roles(*roles_to_remove, reason="Combat fatigue threshold reached")
                except discord.Forbidden:
                    logger.warning("Missing permission to remove flying roles from %s", user.id)

        embed = discord.Embed(
            title="Stats Logged",
            description=f'Updated service record for {user.mention}.',
            color=discord.Color.dark_blue(),
        )
        embed.add_field(name="Sorties Added", value=str(sorties), inline=True)
        embed.add_field(name="Hours Added", value=f"{hours:.1f}", inline=True)
        embed.add_field(name="Kills Added (A/G)", value=f"{air_kills}/{ground_kills}", inline=True)
        embed.add_field(name="Cheks Earned", value=f"+{cheks_delta}", inline=True)
        embed.add_field(
            name="Fatigue",
            value=f'{updated["fatigue_score"]:.0f} / {data.FATIGUE_THRESHOLD:.0f}',
            inline=True,
        )

        if newly_fatigued:
            embed.add_field(
                name="⚠ Status Change",
                value=(
                    "This pilot has reached the fatigue threshold and is now **FATIGUED**. "
                    "Flying roles removed. They must use `/rest` to return to ACTIVE."
                ),
                inline=False,
            )

        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(AdminCog(bot))
