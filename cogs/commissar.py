import datetime
import logging

import discord
from discord import app_commands
from discord.ext import commands

import db
import data
from config import has_commissar_perms

logger = logging.getLogger("vvs.commissar")


class Commissar(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="reprimand", description="[Admin] Issue a disciplinary reprimand.")
    @app_commands.describe(user="The pilot to reprimand", reason="Reason for the reprimand")
    async def reprimand(self, interaction: discord.Interaction, user: discord.Member, reason: str):
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

        entry = {
            "reason": reason,
            "by": str(interaction.user.id),
            "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }
        await db.append_json_list(user.id, "reprimands", entry)
        await db.update_pilot_fields(
            user.id, reprimand_count_active=record["reprimand_count_active"] + 1
        )
        await db.log_commissar_action(user.id, "REPRIMAND", reason, interaction.user.id)

        embed = discord.Embed(
            title="Commissar's Log — Reprimand Entered",
            description=f'{user.mention} has received a formal reprimand.',
            color=discord.Color.dark_orange(),
        )
        embed.add_field(name="Reason", value=reason, inline=False)
        embed.add_field(
            name="Effect",
            value=(
                f"Next promotion now requires an additional "
                f"{data.REPRIMAND_PROMOTION_PENALTY_HOURS:.0f} flight hours."
            ),
            inline=False,
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="commend", description="[Admin] Issue a commendation and Cheks bonus.")
    @app_commands.describe(user="The pilot to commend", reason="Reason for the commendation")
    async def commend(self, interaction: discord.Interaction, user: discord.Member, reason: str):
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

        entry = {
            "reason": reason,
            "by": str(interaction.user.id),
            "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }
        await db.append_json_list(user.id, "commendations", entry)
        await db.adjust_cheks(user.id, data.COMMEND_BONUS_CHEKS)
        await db.log_commissar_action(user.id, "COMMEND", reason, interaction.user.id)

        embed = discord.Embed(
            title="Commissar's Log — Commendation Entered",
            description=f'{user.mention} has been commended for exemplary performance.',
            color=discord.Color.green(),
        )
        embed.add_field(name="Reason", value=reason, inline=False)
        embed.add_field(name="Bonus", value=f"+{data.COMMEND_BONUS_CHEKS} Cheks", inline=False)
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Commissar(bot))
