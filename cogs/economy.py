import logging

import discord
from discord import app_commands
from discord.ext import commands

import db
import data
from utils import format_nickname

logger = logging.getLogger("vvs.economy")


class BazaSelect(discord.ui.Select):
    def __init__(self, cog: "Economy"):
        options = [
            discord.SelectOption(
                label=f'{item["label"]} — {item["cost"]} Cheks',
                value=key,
                description="Purchase this cosmetic badge",
            )
            for key, item in data.BAZA_LUXURIES.items()
        ]
        options.append(
            discord.SelectOption(
                label=f"Custom Callsign — {data.BAZA_CUSTOM_CALLSIGN_COST} Cheks",
                value="custom_callsign",
                description="Unlocks /custom_callsign (one-time use)",
            )
        )
        super().__init__(placeholder="Browse the Baza...", min_values=1, max_values=1, options=options)
        self.cog = cog

    async def callback(self, interaction: discord.Interaction):
        await self.cog.handle_purchase(interaction, self.values[0])


class BazaView(discord.ui.View):
    def __init__(self, cog: "Economy", timeout=180):
        super().__init__(timeout=timeout)
        self.add_item(BazaSelect(cog))


class Economy(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def handle_purchase(self, interaction: discord.Interaction, item_key: str):
        record = await db.get_pilot(interaction.user.id)
        if record is None or record["status"] == "KIA":
            await interaction.response.send_message(
                "You do not have an active service record.", ephemeral=True
            )
            return

        if item_key == "custom_callsign":
            cost = data.BAZA_CUSTOM_CALLSIGN_COST
            if record["custom_callsign_used"]:
                await interaction.response.send_message(
                    "You have already used your one-time custom callsign purchase.",
                    ephemeral=True,
                )
                return
            if record["cheks"] < cost:
                await interaction.response.send_message(
                    f"Insufficient Cheks. You need {cost}, you have {record['cheks']}.",
                    ephemeral=True,
                )
                return
            await db.adjust_cheks(interaction.user.id, -cost)
            await db.update_pilot_fields(interaction.user.id, custom_callsign_used=True)
            await interaction.response.send_message(
                f"Purchase complete. You may now run `/custom_callsign [new_name]` once "
                f"to set your new callsign.",
                ephemeral=True,
            )
            return

        item = data.BAZA_LUXURIES.get(item_key)
        if item is None:
            await interaction.response.send_message("Unknown item.", ephemeral=True)
            return

        cost = item["cost"]
        if record["cheks"] < cost:
            await interaction.response.send_message(
                f"Insufficient Cheks. You need {cost}, you have {record['cheks']}.",
                ephemeral=True,
            )
            return

        await db.adjust_cheks(interaction.user.id, -cost)

        # Cosmetic badge role — created on-demand if it doesn't exist yet,
        # since these are flavor items rather than pre-provisioned roles.
        guild = interaction.guild
        role_name = f'🎖 {item["label"]}'
        role = discord.utils.get(guild.roles, name=role_name)
        if role is None:
            try:
                role = await guild.create_role(name=role_name, reason="Baza cosmetic badge", mentionable=False)
            except discord.Forbidden:
                logger.warning("Missing permission to create cosmetic role in %s", guild.id)
                role = None
        if role:
            try:
                await interaction.user.add_roles(role, reason="Baza purchase")
            except discord.Forbidden:
                logger.warning("Missing permission to assign cosmetic role to %s", interaction.user.id)

        await interaction.response.send_message(
            f'Purchase complete: **{item["label"]}** for {cost} Cheks.', ephemeral=True
        )

    @app_commands.command(name="baza", description="Browse the Baza (shop) and spend your Cheks.")
    async def baza(self, interaction: discord.Interaction):
        record = await db.get_pilot(interaction.user.id)
        if record is None or record["status"] == "KIA":
            await interaction.response.send_message(
                "You do not have an active service record.", ephemeral=True
            )
            return

        embed = discord.Embed(
            title="Военторг — The Baza",
            description=f'Balance: **{record["cheks"]} Cheks**',
            color=discord.Color.blurple(),
        )
        for item in data.BAZA_LUXURIES.values():
            embed.add_field(name=item["label"], value=f'{item["cost"]} Cheks', inline=True)
        embed.add_field(
            name="Custom Callsign",
            value=f'{data.BAZA_CUSTOM_CALLSIGN_COST} Cheks (one-time)',
            inline=True,
        )

        view = BazaView(self)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @app_commands.command(name="custom_callsign", description="Set a custom callsign (requires Baza purchase).")
    @app_commands.describe(new_name="Your new callsign")
    async def custom_callsign(self, interaction: discord.Interaction, new_name: str):
        record = await db.get_pilot(interaction.user.id)
        if record is None or record["status"] == "KIA":
            await interaction.response.send_message(
                "You do not have an active service record.", ephemeral=True
            )
            return
        if not record["custom_callsign_used"]:
            await interaction.response.send_message(
                "You haven't purchased a custom callsign yet. Visit `/baza` first.",
                ephemeral=True,
            )
            return

        new_name = new_name.strip()
        if not (2 <= len(new_name) <= 20):
            await interaction.response.send_message(
                "Callsign must be between 2 and 20 characters.", ephemeral=True
            )
            return

        # Consume the one-time purchase now that it's being used.
        await db.update_pilot_fields(interaction.user.id, callsign=new_name, custom_callsign_used=False)

        last_name = record["soviet_name"].split()[-1]
        new_nick = format_nickname(record["current_rank"], new_name, last_name)
        try:
            await interaction.user.edit(nick=new_nick, reason="Custom callsign purchase")
        except discord.Forbidden:
            logger.warning("Missing permission to rename %s on custom callsign", interaction.user.id)

        await interaction.response.send_message(
            f'Your callsign has been updated to "{new_name}".', ephemeral=True
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(Economy(bot))
