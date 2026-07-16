import datetime
import logging

import discord
from discord import app_commands
from discord.ext import commands

import db
from utils import format_nickname
from config import Config

logger = logging.getLogger("vvs.loa")


def _parse_date(value: str) -> datetime.date:
    """Accepts YYYY-MM-DD."""
    return datetime.datetime.strptime(value.strip(), "%Y-%m-%d").date()


class LOAApprovalView(discord.ui.View):
    """Persistent view attached to the admin-channel approval embed."""

    def __init__(self, cog: "LOA", discord_id: str, start_date, end_date, reason: str):
        super().__init__(timeout=None)
        self.cog = cog
        self.discord_id = discord_id
        self.start_date = start_date
        self.end_date = end_date
        self.reason = reason

    async def _authorized(self, interaction: discord.Interaction) -> bool:
        from config import has_commissar_perms
        if not has_commissar_perms(interaction.user):
            await interaction.response.send_message(
                "Only Admins/Commissars may action LOA requests.", ephemeral=True
            )
            return False
        return True

    @discord.ui.button(label="Approve", style=discord.ButtonStyle.success, custom_id="loa_approve")
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._authorized(interaction):
            return
        await interaction.response.defer()

        await db.set_status(self.discord_id, "LOA")
        await db.set_loa(self.discord_id, self.start_date, self.end_date, self.reason)
        await db.log_commissar_action(self.discord_id, "LOA_APPROVE", self.reason, interaction.user.id)

        member = interaction.guild.get_member(int(self.discord_id))
        record = await db.get_pilot(self.discord_id)
        if member and record:
            last_name = record["soviet_name"].split()[-1]
            new_nick = format_nickname(record["current_rank"], record["callsign"], last_name, prefix_tag="[LOA]")
            try:
                await member.edit(nick=new_nick, reason="LOA approved")
            except discord.Forbidden:
                logger.warning("Missing permission to rename %s on LOA approval", self.discord_id)

        for child in self.children:
            child.disabled = True
        await interaction.message.edit(view=self)
        await interaction.followup.send(
            f"LOA approved for <@{self.discord_id}> ({self.start_date} to {self.end_date})."
        )

    @discord.ui.button(label="Deny", style=discord.ButtonStyle.danger, custom_id="loa_deny")
    async def deny(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._authorized(interaction):
            return
        await interaction.response.defer()
        for child in self.children:
            child.disabled = True
        await interaction.message.edit(view=self)
        await interaction.followup.send(f"LOA request for <@{self.discord_id}> denied.")


class LOAGroup(app_commands.Group):
    def __init__(self, cog: "LOA"):
        super().__init__(name="loa", description="Leave of Absence commands.")
        self.cog = cog

    @app_commands.command(name="request", description="Request a Leave of Absence.")
    @app_commands.describe(
        start_date="Start date, YYYY-MM-DD",
        end_date="End date, YYYY-MM-DD",
        reason="Reason for leave",
    )
    async def request(self, interaction: discord.Interaction, start_date: str, end_date: str, reason: str):
        record = await db.get_pilot(interaction.user.id)
        if record is None or record["status"] == "KIA":
            await interaction.response.send_message(
                "You do not have an active service record.", ephemeral=True
            )
            return
        if record["status"] == "LOA":
            await interaction.response.send_message(
                "You are already on LOA.", ephemeral=True
            )
            return

        try:
            start = _parse_date(start_date)
            end = _parse_date(end_date)
        except ValueError:
            await interaction.response.send_message(
                "Dates must be in YYYY-MM-DD format.", ephemeral=True
            )
            return
        if end < start:
            await interaction.response.send_message(
                "End date must be on or after the start date.", ephemeral=True
            )
            return

        await interaction.response.send_message(
            "Your LOA request has been submitted for Commissar review.", ephemeral=True
        )

        admin_channel = interaction.client.get_channel(Config.ADMIN_APPROVAL_CHANNEL_ID)
        if admin_channel is None:
            logger.warning("ADMIN_APPROVAL_CHANNEL_ID not configured or channel not found.")
            return

        embed = discord.Embed(
            title="Leave of Absence Request",
            description=f'**{record["soviet_name"]}** "{record["callsign"]}" ({interaction.user.mention})',
            color=discord.Color.gold(),
        )
        embed.add_field(name="Start", value=str(start), inline=True)
        embed.add_field(name="End", value=str(end), inline=True)
        embed.add_field(name="Reason", value=reason, inline=False)

        view = LOAApprovalView(self.cog, str(interaction.user.id), start, end, reason)
        await admin_channel.send(embed=embed, view=view)

    @app_commands.command(name="return", description="Return from Leave of Absence.")
    async def return_(self, interaction: discord.Interaction):
        record = await db.get_pilot(interaction.user.id)
        if record is None or record["status"] != "LOA":
            await interaction.response.send_message(
                "You are not currently on LOA.", ephemeral=True
            )
            return

        await db.clear_loa(interaction.user.id)
        await db.log_commissar_action(interaction.user.id, "LOA_RETURN", "Returned from LOA", interaction.user.id)

        last_name = record["soviet_name"].split()[-1]
        new_nick = format_nickname(record["current_rank"], record["callsign"], last_name)
        try:
            await interaction.user.edit(nick=new_nick, reason="Returned from LOA")
        except discord.Forbidden:
            logger.warning("Missing permission to rename %s on LOA return", interaction.user.id)

        await interaction.response.send_message(
            f'Welcome back, {record["current_rank"]} "{record["callsign"]}". '
            f"Your status has been restored to ACTIVE.",
            ephemeral=True,
        )


class LOA(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.group = LOAGroup(self)
        bot.tree.add_command(self.group)


async def setup(bot: commands.Bot):
    await bot.add_cog(LOA(bot))
