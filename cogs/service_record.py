import discord
from discord import app_commands
from discord.ext import commands

import db
from utils import build_dossier_embed


class ServiceRecord(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.ctx_menu = app_commands.ContextMenu(
            name="View Service Record",
            callback=self.view_service_record,
        )
        bot.tree.add_command(self.ctx_menu)

    async def cog_unload(self):
        self.bot.tree.remove_command(self.ctx_menu.name, type=self.ctx_menu.type)

    async def view_service_record(self, interaction: discord.Interaction, member: discord.Member):
        await self._send_profile(interaction, member)

    @app_commands.command(name="profile", description="View a pilot's service record (Личное дело).")
    @app_commands.describe(user="Pilot to look up (defaults to yourself)")
    async def profile(self, interaction: discord.Interaction, user: discord.Member = None):
        member = user or interaction.user
        await self._send_profile(interaction, member)

    async def _send_profile(self, interaction: discord.Interaction, member: discord.Member):
        record = await db.get_pilot(member.id)
        if record is None:
            await interaction.response.send_message(
                f"{member.mention} has no service record on file.", ephemeral=True
            )
            return

        embed = build_dossier_embed(record, member)
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(ServiceRecord(bot))
