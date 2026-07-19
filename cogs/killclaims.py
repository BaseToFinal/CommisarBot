"""
#killclaims workflow: an enlisted member posts a guncam screenshot (from
the community's guncam application) in the designated channel, and it's
automatically picked up as a pending kill claim routed to the admin
approval channel. A Commissar/Admin then classifies it Air/Ground or
denies it via buttons; approval credits the kill (and Cheks) to the
poster's service record via the same add_stats() path /logstats uses.

Claims are persisted in the kill_claims table (not just held in memory),
and pending claims' review views are re-registered on cog load, so the
approve/deny buttons keep working across bot restarts — unlike the
plain in-memory LOAApprovalView pattern, this survives a redeploy
because the view's only state is the claim_id baked into each button's
custom_id, and the rest is fetched fresh from the DB.
"""

import logging

import discord
from discord.ext import commands

import data
import db
from config import Config, has_commissar_perms
from utils import store_attachment, strip_discord_cdn_signature

logger = logging.getLogger("vvs.killclaims")

PENDING_EMOJI = "\u23f3"   # hourglass
APPROVED_EMOJI = "\u2705"  # check mark
DENIED_EMOJI = "\u274c"    # cross mark


class KillClaimReviewView(discord.ui.View):
    """
    Approve (Air/Ground) or Deny buttons for a single kill claim. custom_id
    encodes the claim_id so this view can be reconstructed from nothing
    but that id — no per-instance state is required to resolve a claim,
    which is what makes re-registration on cog_load work after a restart.
    """

    def __init__(self, claim_id: int):
        super().__init__(timeout=None)
        self.claim_id = claim_id

        air_btn = discord.ui.Button(
            label="Approve — Air Kill",
            style=discord.ButtonStyle.success,
            emoji="\u2708",
            custom_id=f"kc_air_{claim_id}",
        )
        air_btn.callback = self._make_callback("APPROVED_AIR", "Air", 1, 0)
        self.add_item(air_btn)

        ground_btn = discord.ui.Button(
            label="Approve — Ground Kill",
            style=discord.ButtonStyle.primary,
            emoji="\U0001f4a5",
            custom_id=f"kc_ground_{claim_id}",
        )
        ground_btn.callback = self._make_callback("APPROVED_GROUND", "Ground", 0, 1)
        self.add_item(ground_btn)

        deny_btn = discord.ui.Button(
            label="Deny",
            style=discord.ButtonStyle.danger,
            custom_id=f"kc_deny_{claim_id}",
        )
        deny_btn.callback = self._make_callback("DENIED", "Denied", 0, 0)
        self.add_item(deny_btn)

    def _make_callback(self, status: str, label: str, air_kills: int, ground_kills: int):
        async def callback(interaction: discord.Interaction):
            await self._resolve(interaction, status, label, air_kills, ground_kills)
        return callback

    async def _resolve(
        self, interaction: discord.Interaction, status: str, label: str,
        air_kills: int, ground_kills: int,
    ):
        if not has_commissar_perms(interaction.user):
            await interaction.response.send_message(
                "Only Admins/Commissars may action kill claims.", ephemeral=True
            )
            return
        await interaction.response.defer()

        claim = await db.resolve_kill_claim(self.claim_id, status, interaction.user.id)
        if claim is None:
            await interaction.followup.send(
                "This claim was already resolved (or doesn't exist).", ephemeral=True
            )
            return

        if status != "DENIED":
            await db.add_stats(
                claim["discord_id"],
                sorties=0,
                hours=0.0,
                ground_kills=ground_kills,
                air_kills=air_kills,
                fatigue_delta=0.0,
                cheks_delta=data.CHEKS_PER_KILL,
            )
            await db.log_commissar_action(
                claim["discord_id"], "KILL_CLAIM_APPROVE",
                f"{label} kill claim #{self.claim_id} approved (+{data.CHEKS_PER_KILL} Cheks)",
                interaction.user.id,
            )
        else:
            await db.log_commissar_action(
                claim["discord_id"], "KILL_CLAIM_DENY",
                f"Kill claim #{self.claim_id} denied", interaction.user.id,
            )

        for child in self.children:
            child.disabled = True
        result_line = f"**{label}** — actioned by {interaction.user.mention}"
        try:
            embed = interaction.message.embeds[0]
            embed.color = discord.Color.green() if status != "DENIED" else discord.Color.dark_grey()
            embed.add_field(name="Result", value=result_line, inline=False)
            await interaction.message.edit(embed=embed, view=self)
        except (IndexError, discord.HTTPException):
            await interaction.message.edit(view=self)

        await self._update_source_reaction(interaction.client, claim, approved=(status != "DENIED"))
        await interaction.followup.send(
            f"Claim #{self.claim_id} for <@{claim['discord_id']}> — {result_line}", ephemeral=True
        )

    async def _update_source_reaction(self, bot: discord.Client, claim, approved: bool):
        channel = bot.get_channel(int(claim["channel_id"]))
        if channel is None:
            try:
                channel = await bot.fetch_channel(int(claim["channel_id"]))
            except discord.HTTPException:
                return
        try:
            source_msg = await channel.fetch_message(int(claim["message_id"]))
        except discord.HTTPException:
            return
        try:
            await source_msg.remove_reaction(PENDING_EMOJI, bot.user)
        except discord.HTTPException:
            pass
        try:
            await source_msg.add_reaction(APPROVED_EMOJI if approved else DENIED_EMOJI)
        except discord.HTTPException:
            pass


class KillClaims(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self):
        # Re-attach live views to any claims still awaiting review so the
        # buttons keep working after a restart/redeploy.
        pending = await db.get_pending_kill_claims()
        for claim in pending:
            if not claim["review_message_id"]:
                continue
            try:
                self.bot.add_view(
                    KillClaimReviewView(claim["id"]),
                    message_id=int(claim["review_message_id"]),
                )
            except Exception:
                logger.exception("Failed to re-register kill claim view for claim #%s", claim["id"])
        if pending:
            logger.info("Re-registered %d pending kill claim review view(s).", len(pending))

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or message.guild is None:
            return
        if not Config.KILLCLAIMS_CHANNEL_ID or message.channel.id != Config.KILLCLAIMS_CHANNEL_ID:
            return

        image_attachments = [
            a for a in message.attachments if (a.content_type or "").startswith("image/")
        ]
        if not image_attachments:
            return

        record = await db.get_pilot(message.author.id)
        if record is None or record["status"] == "KIA":
            try:
                await message.add_reaction("\u2753")  # question mark: no active service record
            except discord.HTTPException:
                pass
            return

        admin_channel = self.bot.get_channel(Config.ADMIN_APPROVAL_CHANNEL_ID)
        if admin_channel is None:
            try:
                admin_channel = await self.bot.fetch_channel(Config.ADMIN_APPROVAL_CHANNEL_ID)
            except discord.HTTPException:
                logger.warning("ADMIN_APPROVAL_CHANNEL_ID not configured/reachable; cannot route kill claim.")
                return

        try:
            await message.add_reaction(PENDING_EMOJI)
        except discord.HTTPException:
            pass

        for attachment in image_attachments:
            # Re-host to a durable channel so the review embed's image
            # doesn't die when Discord's signed CDN URL expires (~24h) —
            # same pattern used for avatars/medal icons.
            stored_url = await store_attachment(self.bot, attachment, attachment.filename)
            if not stored_url:
                stored_url = strip_discord_cdn_signature(attachment.url)

            claim = await db.create_kill_claim(
                message.author.id, message.id, message.channel.id, stored_url
            )

            embed = discord.Embed(
                title="Kill Claim — Pending Review",
                description=(
                    f'**{record["soviet_name"]}** "{record["callsign"]}" ({message.author.mention})\n'
                    f"[Jump to claim]({message.jump_url})"
                ),
                color=discord.Color.orange(),
            )
            embed.set_image(url=stored_url)
            embed.set_footer(text=f"Claim #{claim['id']}")

            view = KillClaimReviewView(claim["id"])
            review_msg = await admin_channel.send(embed=embed, view=view)
            await db.set_kill_claim_review_message(claim["id"], review_msg.id)


async def setup(bot: commands.Bot):
    await bot.add_cog(KillClaims(bot))
