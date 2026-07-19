"""
Soviet VVS Enlistment Bot — main entrypoint.

Deployment (Railway):
    1. Provision a PostgreSQL plugin — Railway sets DATABASE_URL automatically.
    2. Set DISCORD_TOKEN and the channel/role ID variables (see config.py)
       in the service's Variables tab.
    3. Start command: python main.py
       (requirements.txt / Procfile drive the build+start on Railway)
"""

import asyncio
import logging
import sys

import discord
from discord.ext import commands

try:
    from dotenv import load_dotenv
    load_dotenv()  # no-op in prod if no .env file is present; Railway injects env vars directly
except ImportError:
    pass

import db
from config import Config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("vvs.main")

INTENTS = discord.Intents.default()
INTENTS.members = True  # required for nickname edits / role management
INTENTS.message_content = True  # required to read attachments/embeds on messages
                                  # the bot didn't author itself (e.g. scanning
                                  # #pilot_photo_pool via /sync_avatar_pool) —
                                  # without this, Discord returns those fields
                                  # empty even though channel.history() still
                                  # succeeds. Also requires enabling "Message
                                  # Content Intent" in the Developer Portal.

COGS = [
    "cogs.enlistment",
    "cogs.transfer",
    "cogs.loa",
    "cogs.fatigue_kia",
    "cogs.commissar",
    "cogs.economy",
    "cogs.briefings",
    "cogs.admin",
    "cogs.service_record",
    "cogs.personnel_office",
    "cogs.daily_orders",
    "cogs.killclaims",
    "cogs.dcs_link",
    "cogs.dcs_sync",
]


class VVSBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!vvs-unused-", intents=INTENTS)

    async def setup_hook(self):
        if not Config.DATABASE_URL:
            logger.error("DATABASE_URL is not set. Set it in your environment / Railway variables.")
        else:
            await db.init_pool()
            await db.run_schema("schema.sql")

        for cog in COGS:
            try:
                await self.load_extension(cog)
                logger.info("Loaded extension: %s", cog)
            except Exception:
                logger.exception("Failed to load extension: %s", cog)

        if Config.GUILD_ID:
            guild = discord.Object(id=Config.GUILD_ID)
            self.tree.copy_global_to(guild=guild)
            synced = await self.tree.sync(guild=guild)
            logger.info("Synced %d commands to guild %s (dev mode).", len(synced), Config.GUILD_ID)

            # If GUILD_ID was added after commands were previously synced
            # globally (or vice versa), Discord keeps both registrations
            # around independently, which shows up as duplicate entries in
            # the slash command picker. Clearing + syncing an empty global
            # command set here tells Discord to remove any stale global
            # registration, so only the guild-scoped copy remains visible.
            # This runs on every boot while GUILD_ID is set; it's a no-op
            # once the global set is already empty.
            self.tree.clear_commands(guild=None)
            global_synced = await self.tree.sync()
            logger.info(
                "Cleared global command registration (guild-scoped dev mode active); %d remain globally.",
                len(global_synced),
            )
        else:
            synced = await self.tree.sync()
            logger.info("Synced %d global commands.", len(synced))

    async def close(self):
        await db.close_pool()
        await super().close()


bot = VVSBot()


@bot.event
async def on_ready():
    logger.info("Logged in as %s (ID: %s)", bot.user, bot.user.id)
    logger.info("Connected to %d guild(s).", len(bot.guilds))


def main():
    if not Config.DISCORD_TOKEN:
        logger.error("DISCORD_TOKEN is not set. Aborting startup.")
        sys.exit(1)
    bot.run(Config.DISCORD_TOKEN, log_handler=None)


if __name__ == "__main__":
    main()
