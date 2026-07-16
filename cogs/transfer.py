import logging

import discord
from discord import app_commands
from discord.ext import commands

import db
import data

logger = logging.getLogger("vvs.transfer")


class TransferSelect(discord.ui.Select):
    def __init__(self, cog: "Transfer", current_airframe: str):
        options = [
            discord.SelectOption(
                label=airframe,
                description=squadron[:100],
                default=(airframe == current_airframe),
            )
            for airframe, squadron in data.AIRFRAME_SQUADRONS.items()
        ]
        super().__init__(
            placeholder="Select your new airframe...",
            min_values=1,
            max_values=1,
            options=options,
        )
        self.cog = cog
        self.current_airframe = current_airframe

    async def callback(self, interaction: discord.Interaction):
        new_airframe = self.values[0]
        await self.cog.finalize_transfer(interaction, new_airframe, self.current_airframe)


class TransferView(discord.ui.View):
    def __init__(self, cog: "Transfer", current_airframe: str, timeout=180):
        super().__init__(timeout=timeout)
        self.add_item(TransferSelect(cog, current_airframe))


class Transfer(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def finalize_transfer(self, interaction: discord.Interaction, new_airframe: str, old_airframe: str):
        await interaction.response.defer(ephemeral=True, thinking=True)

        record = await db.get_pilot(interaction.user.id)
        if record is None or record["status"] == "KIA":
            await interaction.followup.send(
                "You do not have an active service record to transfer.", ephemeral=True
            )
            return

        if new_airframe == old_airframe:
            await interaction.followup.send(
                f"You are already assigned to the {new_airframe} squadron.", ephemeral=True
            )
            return

        new_squadron = data.AIRFRAME_SQUADRONS[new_airframe]

        # Role swap first, then DB update — flight hours, sorties, medals,
        # currency, and name are all left completely untouched here.
        enlistment_cog = self.bot.get_cog("Enlistment")
        if enlistment_cog:
            await enlistment_cog._swap_squadron_role(interaction.user, new_airframe, old_airframe)

        updated = await db.transfer_airframe(interaction.user.id, new_airframe, new_squadron)

        embed = discord.Embed(
            title="Squadron Transfer Order",
            description=(
                f'**{updated["soviet_name"]}** "{updated["callsign"]}" has been reassigned.'
            ),
            color=discord.Color.dark_blue(),
        )
        embed.add_field(name="Previous Airframe", value=old_airframe or "None", inline=True)
        embed.add_field(name="New Airframe", value=new_airframe, inline=True)
        embed.add_field(name="New Squadron", value=new_squadron, inline=False)
        embed.set_footer(
            text=f'Flight hours ({updated["flight_hours"]:.1f}), sorties ({updated["sorties"]}), '
                 f'and Cheks balance carried over unchanged.'
        )

        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="transfer", description="Transfer to a new airframe / squadron.")
    async def transfer(self, interaction: discord.Interaction):
        record = await db.get_pilot(interaction.user.id)
        if record is None or record["status"] == "KIA":
            await interaction.response.send_message(
                "You do not have an active service record. Use `/enlist` first.",
                ephemeral=True,
            )
            return
        prefix = ""
        if record["status"] == "FATIGUED":
            prefix = (
                "You are currently listed as FATIGUED and grounded. You may still "
                "transfer, but you will not be cleared to fly until you `/rest`.\n\n"
            )

        view = TransferView(self, record["airframe"])
        await interaction.response.send_message(
            f"{prefix}Select your new airframe assignment:", view=view, ephemeral=True
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(Transfer(bot))
