import logging

import discord
from discord import app_commands
from discord.ext import commands

import db
import data
from utils import build_dossier_embeds, build_rank_structure_embeds, build_roster_embed
from config import has_commissar_perms

logger = logging.getLogger("vvs.personnel_office")


class PersonnelOfficeView(discord.ui.View):
    """
    Persistent panel (custom_id-based, timeout=None) so a single posted
    message keeps working across bot restarts — pin this in a channel like
    #personnel-office so pilots always have a one-click way to check their
    own record without needing to remember a slash command.
    """

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="View My Profile",
        style=discord.ButtonStyle.primary,
        emoji="🪖",
        custom_id="vvs_panel_view_profile",
    )
    async def view_profile(self, interaction: discord.Interaction, button: discord.ui.Button):
        record = await db.get_pilot(interaction.user.id)
        if record is None:
            await interaction.response.send_message(
                "You don't have a service record yet. Use `/enlist` to begin.",
                ephemeral=True,
            )
            return
        embeds = await build_dossier_embeds(record, interaction.user)
        await interaction.response.send_message(embeds=embeds, ephemeral=True)

    @discord.ui.button(
        label="Rank Structure",
        style=discord.ButtonStyle.secondary,
        emoji="⭐",
        custom_id="vvs_panel_view_ranks",
    )
    async def view_ranks(self, interaction: discord.Interaction, button: discord.ui.Button):
        embeds = await build_rank_structure_embeds()
        await interaction.response.send_message(embeds=embeds, ephemeral=True)


class PersonnelOffice(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Registering here (rather than only in on_ready) means the view is
        # attached as soon as the cog loads, so buttons on a previously
        # posted panel message keep working immediately after a restart.
        self.bot.add_view(PersonnelOfficeView())

    @app_commands.command(
        name="post_personnel_office",
        description="[Admin] Post the Personnel Office panel (profile/rank buttons) in this channel.",
    )
    async def post_personnel_office(self, interaction: discord.Interaction):
        if not has_commissar_perms(interaction.user):
            await interaction.response.send_message(
                "Only Admins/Commissars may use this command.", ephemeral=True
            )
            return

        embed = discord.Embed(
            title="Отдел кадров — Personnel Office",
            description=(
                "Use the buttons below anytime:\n"
                "🪖 **View My Profile** — your full service record\n"
                "⭐ **Rank Structure** — the full VVS rank hierarchy"
            ),
            color=discord.Color.dark_red(),
        )
        await interaction.response.send_message(embed=embed, view=PersonnelOfficeView())

    @app_commands.command(name="ranks", description="View the full VVS rank hierarchy.")
    async def ranks(self, interaction: discord.Interaction):
        embeds = await build_rank_structure_embeds()
        await interaction.response.send_message(embeds=embeds, ephemeral=True)

    @app_commands.command(name="roster", description="View pilots in a squadron, or the whole roster.")
    @app_commands.describe(airframe="Filter to one airframe's squadron (leave blank for everyone)")
    @app_commands.choices(
        airframe=[app_commands.Choice(name=a, value=a) for a in data.AIRFRAME_OPTIONS]
    )
    async def roster(self, interaction: discord.Interaction, airframe: app_commands.Choice[str] = None):
        await interaction.response.defer(ephemeral=True, thinking=True)

        if airframe:
            squadron = data.AIRFRAME_SQUADRONS[airframe.value]
            records = await db.get_pilots_by_squadron(squadron)
            label = squadron
        else:
            records = await db.get_all_active_pilots()
            label = "All Squadrons"

        embed = await build_roster_embed(records, label)
        await interaction.followup.send(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(PersonnelOffice(bot))
