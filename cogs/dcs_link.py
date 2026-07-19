"""
Self-service commands that connect a pilot's Discord service record to the
Cold War EFB's sortie tracker.

/efb_token issues the bearer token the EFB's bridge.js uses to authenticate
sortie reports to the standalone ingest service — the token IS the identity
for that purpose, so this is the security-relevant command. /link_dcs_name
is purely informational (shown on the dossier, useful for cross-checking
against guncam claims) and carries no auth weight on its own.
"""

import logging
import secrets

import discord
from discord import app_commands
from discord.ext import commands

import db

logger = logging.getLogger("vvs.dcs_link")


class DCSLink(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="link_dcs_name",
        description="Set your in-game DCS player name on your service profile.",
    )
    @app_commands.describe(dcs_name="Your exact DCS multiplayer player name")
    async def link_dcs_name(self, interaction: discord.Interaction, dcs_name: str):
        record = await db.get_pilot(interaction.user.id)
        if record is None or record["status"] == "KIA":
            await interaction.response.send_message(
                "You do not have an active service record. Use `/enlist` first.",
                ephemeral=True,
            )
            return

        cleaned = dcs_name.strip()
        if not cleaned:
            await interaction.response.send_message(
                "That name is empty.", ephemeral=True
            )
            return

        await db.set_dcs_player_name(interaction.user.id, cleaned)
        await interaction.response.send_message(
            f'DCS player name set to **{cleaned}**.',
            ephemeral=True,
        )

    @app_commands.command(
        name="efb_token",
        description="Get (or regenerate) your Cold War EFB sortie-tracker token.",
    )
    async def efb_token(self, interaction: discord.Interaction):
        record = await db.get_pilot(interaction.user.id)
        if record is None or record["status"] == "KIA":
            await interaction.response.send_message(
                "You do not have an active service record. Use `/enlist` first.",
                ephemeral=True,
            )
            return

        # 32 bytes of randomness, URL-safe — plenty of entropy for a bearer
        # token that's only ever compared against a DB column, never guessed.
        token = secrets.token_urlsafe(32)
        await db.issue_efb_token(interaction.user.id, token)
        await db.log_commissar_action(
            interaction.user.id, "EFB_TOKEN_ISSUED",
            "EFB sortie-tracker token (re)generated", interaction.user.id,
        )

        embed = discord.Embed(
            title="Cold War EFB — sortie tracker token",
            description=(
                "Paste this into your EFB's `config.json` as `efbApiToken`. "
                "Requesting a new token immediately invalidates any old one — "
                "do this if you think yours leaked.\n\n"
                "This message is only visible to you."
            ),
            color=discord.Color.blue(),
        )
        embed.add_field(name="Token", value=f"```{token}```", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(DCSLink(bot))
