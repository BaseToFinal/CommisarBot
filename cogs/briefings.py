import random

import discord
from discord import app_commands
from discord.ext import commands

import data


class Briefings(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="weather", description="Get the daily weather briefing for the Kabul/Bagram region.")
    async def weather(self, interaction: discord.Interaction):
        wind = random.choice(data.WEATHER_WIND)
        vis = random.choice(data.WEATHER_VISIBILITY)
        sky = random.choice(data.WEATHER_SKY)
        low, high = random.choice(data.WEATHER_TEMP_RANGES_C)
        temp = random.randint(low, high)

        embed = discord.Embed(
            title="Метеосводка — Kabul / Bagram Region",
            description="0600Z Meteorological Briefing",
            color=discord.Color.dark_teal(),
        )
        embed.add_field(name="Wind", value=wind.capitalize(), inline=False)
        embed.add_field(name="Visibility", value=vis.capitalize(), inline=False)
        embed.add_field(name="Sky Condition", value=sky.capitalize(), inline=False)
        embed.add_field(name="Temperature", value=f"{temp}°C", inline=False)

        if "dust storm" in vis:
            embed.set_footer(text="⚠ Dust storm advisory in effect. Exercise caution on approach.")
        else:
            embed.set_footer(text="Conditions suitable for scheduled operations.")

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="intel", description="Get today's intelligence briefing.")
    async def intel(self, interaction: discord.Interaction):
        report = random.choice(data.INTEL_TOPICS)
        threat_level = random.choice(["LOW", "MODERATE", "ELEVATED", "HIGH"])
        colors = {
            "LOW": discord.Color.green(),
            "MODERATE": discord.Color.gold(),
            "ELEVATED": discord.Color.orange(),
            "HIGH": discord.Color.red(),
        }

        embed = discord.Embed(
            title="Разведывательная сводка — Daily Intelligence Summary",
            description=report,
            color=colors[threat_level],
        )
        embed.add_field(name="Threat Level", value=threat_level, inline=True)
        embed.set_footer(text="Classified — for VVS operational personnel only.")

        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Briefings(bot))
