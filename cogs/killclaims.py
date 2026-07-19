"""
#killclaims workflow: an enlisted member posts a guncam screenshot (from
the community's guncam application) in the designated channel. Before it
goes anywhere near a Commissar, the poster must fill in a short modal
(Enemy Aircraft Type, Location, Weapon Used) via a button the bot posts
alongside their screenshot -- only once that's submitted does the claim get
routed to the admin approval channel. A Commissar/Admin then classifies it
Air/Ground or denies it via buttons; approval credits the kill (and Cheks)
to the poster's service record via the same add_stats() path /logstats
uses.

A claim moves through three states, all under status='PENDING' until
resolved (the two PENDING sub-states are distinguished purely by whether
enemy_aircraft_type is still NULL -- there's no separate status value for
this, to avoid a wider status enum for what's really just "has the modal
been submitted yet"):
  1. Awaiting details -- claim exists, prompt_message_id set, waiting on
     the poster to click the button and submit the modal.
  2. Awaiting review -- details submitted, review_message_id set, waiting
     on a Commissar to click Approve/Deny in the admin channel.
  3. Resolved -- status is APPROVED_AIR / APPROVED_GROUND / DENIED.

Claims are persisted in the kill_claims table (not just held in memory),
and both the details-prompt and review views are re-registered on cog
load based on which state each still-open claim is in, so every button
keeps working across bot restarts -- unlike the plain in-memory
LOAApprovalView pattern, this survives a redeploy because each view's
only state is the claim_id baked into its buttons' custom_ids, and the
rest is fetched fresh from the DB.
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


def _build_review_embed(claim, jump_url: str, mention: str, soviet_name: str, callsign: str) -> discord.Embed:
    embed = discord.Embed(
        title="Kill Claim -- Pending Review",
        description=(
            f'**{soviet_name}** "{callsign}" ({mention})\n'
            f"[Jump to claim]({jump_url})"
        ),
        color=discord.Color.orange(),
    )
    embed.set_image(url=claim["image_url"])
    embed.add_field(name="Enemy Aircraft Type", value=claim["enemy_aircraft_type"] or "--", inline=True)
    embed.add_field(name="Location", value=claim["location"] or "--", inline=True)
    embed.add_field(name="Weapon Used", value=claim["weapon_used"] or "--", inline=True)
    embed.set_footer(text=f"Claim #{claim['id']}")
    return embed


class KillClaimDetailsModal(discord.ui.Modal, title="Kill Claim Details"):
    """
    Collects the three required fields for a kill claim. Submitting this
    is what actually routes the claim to the admin approval channel --
    nothing is sent for Commissar review until this is filled in.
    """

    enemy_aircraft_type = discord.ui.TextInput(
        label="Enemy Aircraft Type", placeholder="e.g. F-15C, F-5E, UH-60", max_length=100, required=True
    )
    location = discord.ui.TextInput(
        label="Location", placeholder="e.g. near Bagram, grid AB1234", max_length=100, required=True
    )
    weapon_used = discord.ui.TextInput(
        label="Weapon Used", placeholder="e.g. R-60M, GSh-23L cannon, S-24B", max_length=100, required=True
    )

    def __init__(self, claim_id: int, prompt_message: discord.Message, cog: "KillClaims"):
        super().__init__()
        self.claim_id = claim_id
        self.prompt_message = prompt_message
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        claim = await db.set_kill_claim_details(
            self.claim_id, str(self.enemy_aircraft_type), str(self.location), str(self.weapon_used)
        )
        if claim is None:
            await interaction.followup.send(
                "This claim's details were already submitted, or it no longer exists.", ephemeral=True
            )
            return

        await self.cog.post_kill_claim_for_review(claim, source_message_ref=self.prompt_message)

        try:
            await self.prompt_message.edit(
                content=f'Details submitted by {interaction.user.mention} -- awaiting Commissar review.',
                view=None,
            )
        except discord.HTTPException:
            pass

        await interaction.followup.send("Kill claim details submitted for review.", ephemeral=True)


class KillClaimDetailsPromptView(discord.ui.View):
    """
    Single "Enter Kill Details" button attached to the bot's reply under a
    freshly-posted screenshot. Only the original poster can use it -- the
    kill claim is their claim to substantiate, not anyone else's to fill
    in on their behalf.
    """

    def __init__(self, claim_id: int, cog: "KillClaims"):
        super().__init__(timeout=None)
        self.claim_id = claim_id
        self.cog = cog

        btn = discord.ui.Button(
            label="Enter Kill Details",
            style=discord.ButtonStyle.primary,
            emoji="\U0001f4dd",
            custom_id=f"kc_details_{claim_id}",
        )
        btn.callback = self._callback
        self.add_item(btn)

    async def _callback(self, interaction: discord.Interaction):
        claim = await db.get_kill_claim(self.claim_id)
        if claim is None or claim["status"] != "PENDING" or claim["enemy_aircraft_type"] is not None:
            await interaction.response.send_message(
                "This claim is no longer awaiting details.", ephemeral=True
            )
            return
        if str(interaction.user.id) != claim["discord_id"]:
            await interaction.response.send_message(
                "Only the pilot who posted this claim can fill in its details.", ephemeral=True
            )
            return
        await interaction.response.send_modal(
            KillClaimDetailsModal(self.claim_id, interaction.message, self.cog)
        )


class KillClaimReviewView(discord.ui.View):
    """
    Approve (Air/Ground) or Deny buttons for a single kill claim. custom_id
    encodes the claim_id so this view can be reconstructed from nothing
    but that id -- no per-instance state is required to resolve a claim,
    which is what makes re-registration on cog_load work after a restart.
    """

    def __init__(self, claim_id: int):
        super().__init__(timeout=None)
        self.claim_id = claim_id

        air_btn = discord.ui.Button(
            label="Approve -- Air Kill",
            style=discord.ButtonStyle.success,
            emoji="\u2708",
            custom_id=f"kc_air_{claim_id}",
        )
        air_btn.callback = self._make_callback("APPROVED_AIR", "Air", 1, 0)
        self.add_item(air_btn)

        ground_btn = discord.ui.Button(
            label="Approve -- Ground Kill",
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
        result_line = f"**{label}** -- actioned by {interaction.user.mention}"
        try:
            embed = interaction.message.embeds[0]
            embed.color = discord.Color.green() if status != "DENIED" else discord.Color.dark_grey()
            embed.add_field(name="Result", value=result_line, inline=False)
            await interaction.message.edit(embed=embed, view=self)
        except (IndexError, discord.HTTPException):
            await interaction.message.edit(view=self)

        await self._update_source_reaction(interaction.client, claim, approved=(status != "DENIED"))
        await interaction.followup.send(
            f"Claim #{self.claim_id} for <@{claim['discord_id']}> -- {result_line}", ephemeral=True
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
        # Re-attach live views to any claim still open, in whichever state
        # it's actually in, so every button keeps working after a
        # restart/redeploy.
        pending = await db.get_pending_kill_claims()
        awaiting_details, awaiting_review = 0, 0
        for claim in pending:
            try:
                if claim["enemy_aircraft_type"] is None:
                    if claim["prompt_message_id"]:
                        self.bot.add_view(
                            KillClaimDetailsPromptView(claim["id"], self),
                            message_id=int(claim["prompt_message_id"]),
                        )
                        awaiting_details += 1
                elif claim["review_message_id"]:
                    self.bot.add_view(
                        KillClaimReviewView(claim["id"]),
                        message_id=int(claim["review_message_id"]),
                    )
                    awaiting_review += 1
            except Exception:
                logger.exception("Failed to re-register kill claim view for claim #%s", claim["id"])
        if pending:
            logger.info(
                "Re-registered kill claim views: %d awaiting details, %d awaiting review.",
                awaiting_details, awaiting_review,
            )

    async def post_kill_claim_for_review(self, claim, source_message_ref=None):
        """
        Sends the admin-review embed for a claim whose details have just
        been submitted. Separated out from on_message since it's now
        triggered by the modal's on_submit, not directly by the image
        post.
        """
        admin_channel = self.bot.get_channel(Config.ADMIN_APPROVAL_CHANNEL_ID)
        if admin_channel is None:
            try:
                admin_channel = await self.bot.fetch_channel(Config.ADMIN_APPROVAL_CHANNEL_ID)
            except discord.HTTPException:
                logger.warning("ADMIN_APPROVAL_CHANNEL_ID not configured/reachable; cannot route kill claim.")
                return

        record = await db.get_pilot(claim["discord_id"])
        soviet_name = record["soviet_name"] if record else "Unknown"
        callsign = record["callsign"] if record else "?"
        mention = f'<@{claim["discord_id"]}>'
        jump_url = source_message_ref.jump_url if source_message_ref else ""

        embed = _build_review_embed(claim, jump_url, mention, soviet_name, callsign)
        view = KillClaimReviewView(claim["id"])
        review_msg = await admin_channel.send(embed=embed, view=view)
        await db.set_kill_claim_review_message(claim["id"], review_msg.id)

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

        try:
            await message.add_reaction(PENDING_EMOJI)
        except discord.HTTPException:
            pass

        for attachment in image_attachments:
            # Re-host to a durable channel so the review embed's image
            # doesn't die when Discord's signed CDN URL expires (~24h) --
            # same pattern used for avatars/medal icons.
            stored_url = await store_attachment(self.bot, attachment, attachment.filename)
            if not stored_url:
                stored_url = strip_discord_cdn_signature(attachment.url)

            claim = await db.create_kill_claim(
                message.author.id, message.id, message.channel.id, stored_url
            )

            prompt_msg = await message.reply(
                f'{message.author.mention} -- before this can go to Commissar review, '
                f'enter the enemy aircraft type, location, and weapon used.',
                view=KillClaimDetailsPromptView(claim["id"], self),
                mention_author=True,
            )
            await db.set_kill_claim_prompt_message(claim["id"], prompt_msg.id)


async def setup(bot: commands.Bot):
    await bot.add_cog(KillClaims(bot))
