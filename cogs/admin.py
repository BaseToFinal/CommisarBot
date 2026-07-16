import logging

import discord
from discord import app_commands
from discord.ext import commands

import db
import data
from utils import format_nickname, store_attachment
from config import has_commissar_perms

logger = logging.getLogger("vvs.admin")


class AdminCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="promote", description="[Admin] Promote a pilot to a new rank.")
    @app_commands.describe(user="The pilot to promote", new_rank="The new rank")
    @app_commands.choices(
        new_rank=[app_commands.Choice(name=r, value=r) for r in data.RANK_PROGRESSION]
    )
    async def promote(self, interaction: discord.Interaction, user: discord.Member, new_rank: app_commands.Choice[str]):
        if not has_commissar_perms(interaction.user):
            await interaction.response.send_message(
                "Only Admins/Commissars may use this command.", ephemeral=True
            )
            return

        record = await db.get_pilot(user.id)
        if record is None or record["status"] == "KIA":
            await interaction.response.send_message(
                "That pilot does not have an active service record.", ephemeral=True
            )
            return

        rank_value = new_rank.value
        await db.set_rank(user.id, rank_value)
        await db.log_commissar_action(user.id, "PROMOTE", f"Promoted to {rank_value}", interaction.user.id)

        last_name = record["soviet_name"].split()[-1]
        prefix_tag = "[LOA]" if record["status"] == "LOA" else ""
        new_nick = format_nickname(rank_value, record["callsign"], last_name, prefix_tag=prefix_tag)
        try:
            await user.edit(nick=new_nick, reason=f"Promoted to {rank_value}")
        except discord.Forbidden:
            logger.warning("Missing permission to rename %s on promotion", user.id)

        embed = discord.Embed(
            title="Promotion Order",
            description=f'{user.mention} has been promoted to **{rank_value}**.',
            color=discord.Color.blue(),
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="award", description="[Admin] Award a medal to a pilot.")
    @app_commands.describe(
        user="The pilot to award",
        medal_id="Medal identifier (e.g. 'Red Star', 'Order of Lenin')",
        image="Optional icon for this medal. First award of a given medal name sets its permanent icon.",
    )
    async def award(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        medal_id: str,
        image: discord.Attachment = None,
    ):
        if not has_commissar_perms(interaction.user):
            await interaction.response.send_message(
                "Only Admins/Commissars may use this command.", ephemeral=True
            )
            return

        record = await db.get_pilot(user.id)
        if record is None or record["status"] == "KIA":
            await interaction.response.send_message(
                "That pilot does not have an active service record.", ephemeral=True
            )
            return

        await interaction.response.defer(thinking=True)

        import json
        medals = json.loads(record["earned_medals"] or "[]")
        medals.append(medal_id)
        await db.update_pilot_fields(user.id, earned_medals=json.dumps(medals))
        await db.log_commissar_action(user.id, "AWARD", medal_id, interaction.user.id)

        icon_note = ""
        if image is not None:
            stored_url = await store_attachment(self.bot, image, f"medal_{medal_id}".replace(" ", "_"))
            if stored_url:
                await db.upsert_medal_image(medal_id, stored_url, interaction.user.id)
                icon_note = " (icon registered for this medal)"
            else:
                icon_note = " (icon upload failed — check AVATAR_STORAGE_CHANNEL_ID)"
        else:
            existing_icon = await db.get_medal_image(medal_id)
            if existing_icon:
                icon_note = " (using existing catalog icon)"

        embed = discord.Embed(
            title="Decoration Awarded",
            description=f'{user.mention} has been awarded the **{medal_id}**.{icon_note}',
            color=discord.Color.gold(),
        )
        catalog_icon = await db.get_medal_image(medal_id)
        if catalog_icon:
            embed.set_thumbnail(url=catalog_icon["image_url"])
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="logstats", description="[Admin] Log sortie/flight-hour/kill stats for a pilot.")
    @app_commands.describe(
        user="The pilot to update",
        sorties="Sorties flown to add",
        hours="Flight hours to add",
        ground_kills="Ground kills to add",
        air_kills="Air kills to add",
    )
    async def logstats(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        sorties: int,
        hours: float,
        ground_kills: int = 0,
        air_kills: int = 0,
    ):
        if not has_commissar_perms(interaction.user):
            await interaction.response.send_message(
                "Only Admins/Commissars may use this command.", ephemeral=True
            )
            return

        record = await db.get_pilot(user.id)
        if record is None or record["status"] == "KIA":
            await interaction.response.send_message(
                "That pilot does not have an active service record.", ephemeral=True
            )
            return

        if sorties < 0 or hours < 0 or ground_kills < 0 or air_kills < 0:
            await interaction.response.send_message("Values must be non-negative.", ephemeral=True)
            return

        fatigue_delta = hours * data.FATIGUE_PER_HOUR
        cheks_delta = (sorties * data.CHEKS_PER_SORTIE) + (
            (ground_kills + air_kills) * data.CHEKS_PER_KILL
        )

        updated = await db.add_stats(
            user.id, sorties, hours, ground_kills, air_kills, fatigue_delta, cheks_delta
        )

        newly_fatigued = False
        if updated["fatigue_score"] >= data.FATIGUE_THRESHOLD and updated["status"] == "ACTIVE":
            await db.set_status(user.id, "FATIGUED")
            newly_fatigued = True

            guild = interaction.guild
            from config import Config
            roles_to_remove = []
            for role_id in list(Config.SQUADRON_ROLE_IDS.values()) + [Config.ACTIVE_FLYER_ROLE_ID]:
                if not role_id:
                    continue
                role = guild.get_role(role_id)
                if role and role in user.roles:
                    roles_to_remove.append(role)
            if roles_to_remove:
                try:
                    await user.remove_roles(*roles_to_remove, reason="Combat fatigue threshold reached")
                except discord.Forbidden:
                    logger.warning("Missing permission to remove flying roles from %s", user.id)

        embed = discord.Embed(
            title="Stats Logged",
            description=f'Updated service record for {user.mention}.',
            color=discord.Color.dark_blue(),
        )
        embed.add_field(name="Sorties Added", value=str(sorties), inline=True)
        embed.add_field(name="Hours Added", value=f"{hours:.1f}", inline=True)
        embed.add_field(name="Kills Added (A/G)", value=f"{air_kills}/{ground_kills}", inline=True)
        embed.add_field(name="Cheks Earned", value=f"+{cheks_delta}", inline=True)
        embed.add_field(
            name="Fatigue",
            value=f'{updated["fatigue_score"]:.0f} / {data.FATIGUE_THRESHOLD:.0f}',
            inline=True,
        )

        if newly_fatigued:
            embed.add_field(
                name="⚠ Status Change",
                value=(
                    "This pilot has reached the fatigue threshold and is now **FATIGUED**. "
                    "Flying roles removed. They must use `/rest` to return to ACTIVE."
                ),
                inline=False,
            )

        await interaction.response.send_message(embed=embed)


    @app_commands.command(
        name="sync_avatar_pool",
        description="[Admin] Scan the pilot photo pool channel and register new images.",
    )
    async def sync_avatar_pool(self, interaction: discord.Interaction):
        if not has_commissar_perms(interaction.user):
            await interaction.response.send_message(
                "Only Admins/Commissars may use this command.", ephemeral=True
            )
            return

        from config import Config
        if not Config.PILOT_PHOTO_POOL_CHANNEL_ID:
            await interaction.response.send_message(
                "PILOT_PHOTO_POOL_CHANNEL_ID is not configured. Set it in your "
                "Railway variables and redeploy first.",
                ephemeral=True,
            )
            return

        channel = self.bot.get_channel(Config.PILOT_PHOTO_POOL_CHANNEL_ID)
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(Config.PILOT_PHOTO_POOL_CHANNEL_ID)
            except discord.HTTPException:
                await interaction.response.send_message(
                    "Could not access the configured photo pool channel. Check the ID "
                    "and make sure the bot can view it.",
                    ephemeral=True,
                )
                return

        await interaction.response.defer(ephemeral=True, thinking=True)

        image_exts = (".png", ".jpg", ".jpeg", ".webp", ".gif")
        entries = []
        scanned = 0
        raw_attachment_count = 0
        raw_embed_count = 0
        sample_debug = []
        async for message in channel.history(limit=None):
            scanned += 1
            raw_attachment_count += len(message.attachments)
            raw_embed_count += len(message.embeds)

            # Real uploaded file attachments — keyed by the attachment's own
            # unique ID, NOT message.id, since a single message can hold up
            # to 10 images and message.id would collide across all of them.
            for attachment in message.attachments:
                is_image = (
                    (attachment.content_type or "").startswith("image/")
                    or attachment.filename.lower().endswith(image_exts)
                )
                if is_image:
                    entries.append((f"att-{attachment.id}", attachment.url))
                elif len(sample_debug) < 3:
                    sample_debug.append(
                        f"filename={attachment.filename!r} content_type={attachment.content_type!r}"
                    )

            # Pasted image URLs that Discord auto-unfurled into an embed
            # (e.g. a link to an externally-hosted image, rather than a
            # direct file upload) — keyed by message+index since embeds
            # don't carry their own persistent ID.
            for i, embed in enumerate(message.embeds):
                url = None
                if embed.image and embed.image.url:
                    url = embed.image.url
                elif embed.thumbnail and embed.thumbnail.url:
                    url = embed.thumbnail.url
                if url and url.split("?")[0].lower().endswith(image_exts):
                    entries.append((f"embed-{message.id}-{i}", url))
                elif url and len(sample_debug) < 3:
                    sample_debug.append(f"embed_url={url!r} (extension not recognized)")
                elif embed.type and len(sample_debug) < 3:
                    sample_debug.append(f"embed_type={embed.type!r} no image/thumbnail url")

        await db.upsert_avatar_pool_entries(entries)
        stats = await db.get_avatar_pool_stats()

        embed = discord.Embed(
            title="Avatar Pool Sync Complete",
            description=f"Scanned {scanned} messages in {channel.mention}.",
            color=discord.Color.blurple(),
        )
        embed.add_field(name="Images Found This Scan", value=str(len(entries)), inline=True)
        embed.add_field(name="Total In Pool", value=str(stats["total"]), inline=True)
        embed.add_field(name="Available (Unused)", value=str(stats["unused"]), inline=True)
        embed.add_field(name="Raw Attachments Seen", value=str(raw_attachment_count), inline=True)
        embed.add_field(name="Raw Embeds Seen", value=str(raw_embed_count), inline=True)
        embed.add_field(name="\u200b", value="\u200b", inline=True)
        if sample_debug:
            embed.add_field(name="Debug: unmatched samples", value="\n".join(sample_debug), inline=False)
        embed.set_footer(text="Duplicate images (already-synced messages) are skipped automatically.")

        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="avatar_pool_stats", description="[Admin] Show pilot photo pool availability.")
    async def avatar_pool_stats(self, interaction: discord.Interaction):
        if not has_commissar_perms(interaction.user):
            await interaction.response.send_message(
                "Only Admins/Commissars may use this command.", ephemeral=True
            )
            return

        stats = await db.get_avatar_pool_stats()
        embed = discord.Embed(
            title="Avatar Pool Status",
            color=discord.Color.blurple(),
        )
        embed.add_field(name="Total Photos", value=str(stats["total"]), inline=True)
        embed.add_field(name="Available", value=str(stats["unused"]), inline=True)
        embed.add_field(name="Already Assigned", value=str(stats["used"]), inline=True)
        if stats["unused"] == 0:
            embed.set_footer(text="Pool exhausted — new enlistees will get an AI-generated or placeholder photo.")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="set_rank_image", description="[Admin] Set the icon shown for a rank on service profiles.")
    @app_commands.describe(rank="Which rank to set the icon for", image="The icon image to use")
    @app_commands.choices(
        rank=[app_commands.Choice(name=r, value=r) for r in data.RANK_PROGRESSION]
    )
    async def set_rank_image(
        self, interaction: discord.Interaction, rank: app_commands.Choice[str], image: discord.Attachment
    ):
        if not has_commissar_perms(interaction.user):
            await interaction.response.send_message(
                "Only Admins/Commissars may use this command.", ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)

        stored_url = await store_attachment(self.bot, image, f"rank_{rank.value}".replace(" ", "_"))
        if stored_url is None:
            await interaction.followup.send(
                "Failed to store the image. Check that AVATAR_STORAGE_CHANNEL_ID is configured "
                "and the bot can post there.",
                ephemeral=True,
            )
            return

        await db.upsert_rank_image(rank.value, stored_url, interaction.user.id)

        embed = discord.Embed(
            title="Rank Icon Updated",
            description=f"**{rank.value}** now displays this icon on service profiles.",
            color=discord.Color.blue(),
        )
        embed.set_thumbnail(url=stored_url)
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(
        name="set_medal_image",
        description="[Admin] Pre-register an icon for a medal name (without awarding it to anyone).",
    )
    @app_commands.describe(medal_id="Medal name — must match what you'll use with /award", image="The icon image to use")
    async def set_medal_image(self, interaction: discord.Interaction, medal_id: str, image: discord.Attachment):
        if not has_commissar_perms(interaction.user):
            await interaction.response.send_message(
                "Only Admins/Commissars may use this command.", ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)

        stored_url = await store_attachment(self.bot, image, f"medal_{medal_id}".replace(" ", "_"))
        if stored_url is None:
            await interaction.followup.send(
                "Failed to store the image. Check that AVATAR_STORAGE_CHANNEL_ID is configured "
                "and the bot can post there.",
                ephemeral=True,
            )
            return

        await db.upsert_medal_image(medal_id, stored_url, interaction.user.id)

        embed = discord.Embed(
            title="Medal Icon Registered",
            description=f'**{medal_id}** icon saved. Future `/award` calls using this exact '
                         f'name (case-insensitive) will automatically use this icon.',
            color=discord.Color.blue(),
        )
        embed.set_thumbnail(url=stored_url)
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="medal_catalog", description="[Admin] List all registered medal icons.")
    async def medal_catalog(self, interaction: discord.Interaction):
        if not has_commissar_perms(interaction.user):
            await interaction.response.send_message(
                "Only Admins/Commissars may use this command.", ephemeral=True
            )
            return

        entries = await db.list_medal_catalog()
        if not entries:
            await interaction.response.send_message(
                "No medal icons registered yet. Use `/set_medal_image` or attach an image "
                "the first time you `/award` a medal.",
                ephemeral=True,
            )
            return

        embed = discord.Embed(
            title="Medal Icon Catalog",
            description="\n".join(f'• {e["display_name"]}' for e in entries),
            color=discord.Color.blue(),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(
        name="edit_pilot",
        description="[Admin] Directly set exact pilot stats (corrections/backdating), unlike /logstats which adds.",
    )
    @app_commands.describe(
        user="The pilot to edit",
        rank="Set their rank exactly (also updates nickname)",
        flight_hours="Set total flight hours to this exact value",
        sorties="Set total sorties to this exact value",
        kills_ground="Set total ground kills to this exact value",
        kills_air="Set total air kills to this exact value",
        cheks="Set Cheks balance to this exact value",
        fatigue_score="Set fatigue score to this exact value (0-100+)",
    )
    @app_commands.choices(
        rank=[app_commands.Choice(name=r, value=r) for r in data.RANK_PROGRESSION]
    )
    async def edit_pilot(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        rank: app_commands.Choice[str] = None,
        flight_hours: float = None,
        sorties: int = None,
        kills_ground: int = None,
        kills_air: int = None,
        cheks: int = None,
        fatigue_score: float = None,
    ):
        if not has_commissar_perms(interaction.user):
            await interaction.response.send_message(
                "Only Admins/Commissars may use this command.", ephemeral=True
            )
            return

        record = await db.get_pilot(user.id)
        if record is None or record["status"] == "KIA":
            await interaction.response.send_message(
                "That pilot does not have an active service record.", ephemeral=True
            )
            return

        fields = {}
        changes = []
        if rank is not None:
            fields["current_rank"] = rank.value
            changes.append(f'Rank: {record["current_rank"]} → {rank.value}')
        if flight_hours is not None:
            fields["flight_hours"] = flight_hours
            changes.append(f'Flight Hours: {record["flight_hours"]:.1f} → {flight_hours:.1f}')
        if sorties is not None:
            fields["sorties"] = sorties
            changes.append(f'Sorties: {record["sorties"]} → {sorties}')
        if kills_ground is not None:
            fields["kills_ground"] = kills_ground
            changes.append(f'Ground Kills: {record["kills_ground"]} → {kills_ground}')
        if kills_air is not None:
            fields["kills_air"] = kills_air
            changes.append(f'Air Kills: {record["kills_air"]} → {kills_air}')
        if cheks is not None:
            fields["cheks"] = cheks
            changes.append(f'Cheks: {record["cheks"]} → {cheks}')
        if fatigue_score is not None:
            fields["fatigue_score"] = fatigue_score
            changes.append(f'Fatigue: {record["fatigue_score"]:.0f} → {fatigue_score:.0f}')

        if not fields:
            await interaction.response.send_message(
                "No fields provided — nothing to change. Pass at least one value to set.",
                ephemeral=True,
            )
            return

        updated = await db.update_pilot_fields(user.id, **fields)
        await db.log_commissar_action(
            user.id, "EDIT", "; ".join(changes), interaction.user.id
        )

        if rank is not None:
            last_name = record["soviet_name"].split()[-1]
            prefix_tag = "[LOA]" if record["status"] == "LOA" else ""
            new_nick = format_nickname(rank.value, record["callsign"], last_name, prefix_tag=prefix_tag)
            try:
                await user.edit(nick=new_nick, reason="Rank corrected via /edit_pilot")
            except discord.Forbidden:
                logger.warning("Missing permission to rename %s on edit_pilot", user.id)

        embed = discord.Embed(
            title="Service Record Corrected",
            description=f'Updated record for {user.mention}:',
            color=discord.Color.blue(),
        )
        embed.add_field(name="Changes", value="\n".join(changes), inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(
        name="set_pilot_photo",
        description="[Admin] Manually set a specific pilot's portrait (fallback for pool/AI generation).",
    )
    @app_commands.describe(user="The pilot whose portrait to set", image="The portrait image to use")
    async def set_pilot_photo(self, interaction: discord.Interaction, user: discord.Member, image: discord.Attachment):
        if not has_commissar_perms(interaction.user):
            await interaction.response.send_message(
                "Only Admins/Commissars may use this command.", ephemeral=True
            )
            return

        record = await db.get_pilot(user.id)
        if record is None or record["status"] == "KIA":
            await interaction.response.send_message(
                "That pilot does not have an active service record.", ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)

        stored_url = await store_attachment(self.bot, image, f"portrait_{user.id}")
        if stored_url is None:
            await interaction.followup.send(
                "Failed to store the image. Check that AVATAR_STORAGE_CHANNEL_ID is configured "
                "and the bot can post there.",
                ephemeral=True,
            )
            return

        await db.update_pilot_fields(user.id, avatar_url=stored_url)

        embed = discord.Embed(
            title="Portrait Updated",
            description=f'{user.mention}\'s portrait has been set manually.',
            color=discord.Color.blue(),
        )
        embed.set_thumbnail(url=stored_url)
        await interaction.followup.send(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(AdminCog(bot))
