import logging
import random

import discord
from discord import app_commands
from discord.ext import commands

import db
import data
from utils import format_nickname, assign_pilot_avatar
from config import Config

logger = logging.getLogger("vvs.enlistment")


class AirframeSelect(discord.ui.Select):
    """Shared airframe/squadron dropdown used by both /enlist and /transfer."""

    def __init__(self, on_select_callback, placeholder="Select your airframe..."):
        options = [
            discord.SelectOption(label=airframe, description=squadron[:100])
            for airframe, squadron in data.AIRFRAME_SQUADRONS.items()
        ]
        super().__init__(
            placeholder=placeholder,
            min_values=1,
            max_values=1,
            options=options,
            custom_id="vvs_airframe_select",
        )
        self._on_select_callback = on_select_callback

    async def callback(self, interaction: discord.Interaction):
        airframe = self.values[0]
        await self._on_select_callback(interaction, airframe)


class EnlistmentView(discord.ui.View):
    def __init__(self, cog: "Enlistment", first_name: str, last_name: str, callsign: str, timeout=180):
        super().__init__(timeout=timeout)
        self.cog = cog
        self.first_name = first_name
        self.last_name = last_name
        self.callsign = callsign
        self.add_item(AirframeSelect(self._handle_select))

    async def _handle_select(self, interaction: discord.Interaction, airframe: str):
        await self.cog.finalize_enlistment(
            interaction, self.first_name, self.last_name, self.callsign, airframe
        )
        self.stop()


class Enlistment(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _swap_squadron_role(self, member: discord.Member, new_airframe: str, old_airframe: str = None):
        """Remove the old squadron role (if any) and add the new one."""
        guild = member.guild
        new_role_id = Config.SQUADRON_ROLE_IDS.get(new_airframe)
        if old_airframe:
            old_role_id = Config.SQUADRON_ROLE_IDS.get(old_airframe)
            if old_role_id:
                old_role = guild.get_role(old_role_id)
                if old_role and old_role in member.roles:
                    try:
                        await member.remove_roles(old_role, reason="Squadron transfer")
                    except discord.Forbidden:
                        logger.warning("Missing permission to remove squadron role for %s", member.id)
        if new_role_id:
            new_role = guild.get_role(new_role_id)
            if new_role:
                try:
                    await member.add_roles(new_role, reason="Squadron assignment")
                except discord.Forbidden:
                    logger.warning("Missing permission to add squadron role for %s", member.id)

    async def finalize_enlistment(
        self,
        interaction: discord.Interaction,
        first_name: str,
        last_name: str,
        callsign: str,
        airframe: str,
    ):
        await interaction.response.defer(ephemeral=True, thinking=True)

        squadron = data.AIRFRAME_SQUADRONS[airframe]
        soviet_name = f"{first_name} {last_name}"
        avatar_url = await assign_pilot_avatar(soviet_name, interaction.user.id, self.bot)
        bio = data.generate_backstory(first_name, last_name, airframe)

        record = await db.create_pilot(
            discord_id=interaction.user.id,
            guild_id=interaction.guild_id,
            soviet_name=soviet_name,
            callsign=callsign,
            airframe=airframe,
            squadron=squadron,
            avatar_url=avatar_url,
            birth_place=bio["birth_place"],
            birth_date=bio["birth_date"],
            backstory=bio["backstory"],
            service_record_details=bio["service_record_details"],
        )

        if record is None:
            await interaction.followup.send(
                "Enlistment failed — you may already have an active service record. "
                "Contact a Commissar if this seems wrong.",
                ephemeral=True,
            )
            return

        member = interaction.user
        nickname = format_nickname("Junior Lieutenant", callsign, last_name)
        try:
            await member.edit(nick=nickname, reason="VVS enlistment")
        except discord.Forbidden:
            logger.warning("Missing permission to rename %s on enlist", member.id)

        await self._swap_squadron_role(member, airframe)
        if Config.ACTIVE_FLYER_ROLE_ID:
            role = interaction.guild.get_role(Config.ACTIVE_FLYER_ROLE_ID)
            if role:
                try:
                    await member.add_roles(role, reason="VVS enlistment")
                except discord.Forbidden:
                    pass

        embed = discord.Embed(
            title="Enlistment Complete — Добро пожаловать",
            description=(
                f'**{soviet_name}** "{callsign}" has been inducted into the '
                f"Soviet Air Force as a Junior Lieutenant."
            ),
            color=discord.Color.dark_red(),
        )
        embed.add_field(name="Airframe", value=airframe, inline=True)
        embed.add_field(name="Squadron", value=squadron, inline=True)
        embed.add_field(name="Born", value=f'{bio["birth_date"].isoformat()} — {bio["birth_place"]}', inline=False)
        embed.add_field(name="Service Record", value=bio["service_record_details"], inline=False)
        embed.add_field(name="Personal File", value=bio["backstory"], inline=False)
        embed.set_thumbnail(url=avatar_url)
        embed.set_footer(text="Your service record begins now. Fly well, Comrade.")

        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="enlist", description="Enlist in the Soviet Air Force and begin your service record.")
    async def enlist(self, interaction: discord.Interaction):
        existing = await db.get_pilot(interaction.user.id)
        if existing and existing["status"] in ("ACTIVE", "LOA", "FATIGUED"):
            await interaction.response.send_message(
                "You already hold an active service record. Use `/transfer` to change "
                "airframe or contact a Commissar if you believe this is an error.",
                ephemeral=True,
            )
            return

        first_name = random.choice(data.SOVIET_FIRST_NAMES)
        last_name = random.choice(data.SOVIET_LAST_NAMES)
        callsign = random.choice(data.CALLSIGNS)

        embed = discord.Embed(
            title="Soviet Air Force — Induction",
            description=(
                f'Assigned identity: **{first_name} {last_name}**\n'
                f'Assigned callsign: **"{callsign}"**\n\n'
                f"Select your airframe below to complete enlistment. Your squadron "
                f"assignment will be determined automatically."
            ),
            color=discord.Color.dark_red(),
        )
        view = EnlistmentView(self, first_name, last_name, callsign)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Enlistment(bot))
