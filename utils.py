"""
Shared helpers: nickname formatting, embed builders, and avatar generation.
"""

import io
import json
import logging

import discord

from data import RANK_SHORTFORM
from config import Config

logger = logging.getLogger("vvs.utils")


def format_nickname(rank: str, callsign: str, last_name: str, prefix_tag: str = "") -> str:
    """
    Build the guild nickname using the 32-character safety formula:
        [Rank Shortform] "[Callsign]" [Last Name]
    e.g. Jg.Lt. "Burya" Volkov

    prefix_tag (e.g. "[LOA]" or "[KIA]") is prepended and the rest is
    truncated as needed to respect Discord's 32-character nickname limit.
    """
    shortform = RANK_SHORTFORM.get(rank, rank[:6])
    base = f'{shortform} "{callsign}" {last_name}'
    if prefix_tag:
        candidate = f"{prefix_tag} {base}"
    else:
        candidate = base

    if len(candidate) <= 32:
        return candidate

    # Truncate the last name first, then the callsign, to fit the limit
    # while preserving rank and tag (the identifying/administrative parts).
    overflow = len(candidate) - 32
    if prefix_tag:
        fixed = f'{prefix_tag} {shortform} "{callsign}" '
    else:
        fixed = f'{shortform} "{callsign}" '
    room_for_name = max(1, len(last_name) - overflow)
    truncated_name = last_name[:room_for_name]
    candidate = f"{fixed}{truncated_name}"

    if len(candidate) > 32:
        candidate = candidate[:32]
    return candidate


def _build_avatar_prompt(pilot_name: str) -> str:
    return (
        f"A 1984 vintage black and white grainy photograph portrait of a Soviet VVS "
        f"fighter/attack pilot, service ID photo style, worn film grain, slight motion "
        f"blur, Cold War era military uniform with flight helmet or garrison cap, "
        f"neutral studio backdrop, realistic photographic style, no text or watermark. "
        f"The subject is an individual airman (not a specific real person)."
    )


async def _fetch_placeholder(pilot_name: str) -> str:
    slug = pilot_name.lower().replace(" ", "-").replace('"', "")
    return f"https://placehold.co/512x512/1a1a1a/cccccc?text={slug}"


async def _store_bytes_to_discord(bot: discord.Client, image_bytes: bytes, filename: str) -> str | None:
    """
    Upload generated image bytes to a dedicated storage channel so we end up
    with a stable Discord CDN URL to persist in avatar_url. Requires
    AVATAR_STORAGE_CHANNEL_ID to be configured; returns None if it isn't
    (caller should fall back to the placeholder in that case).
    """
    if not Config.AVATAR_STORAGE_CHANNEL_ID:
        logger.warning("AVATAR_STORAGE_CHANNEL_ID not configured; cannot persist generated avatar.")
        return None

    channel = bot.get_channel(Config.AVATAR_STORAGE_CHANNEL_ID)
    if channel is None:
        try:
            channel = await bot.fetch_channel(Config.AVATAR_STORAGE_CHANNEL_ID)
        except discord.HTTPException:
            logger.warning("Could not resolve AVATAR_STORAGE_CHANNEL_ID.")
            return None

    file = discord.File(io.BytesIO(image_bytes), filename=filename)
    try:
        message = await channel.send(content=f"Avatar archive: {filename}", file=file)
    except discord.Forbidden:
        logger.warning("Missing permission to post in avatar storage channel.")
        return None

    if message.attachments:
        return message.attachments[0].url
    return None


async def generate_avatar(pilot_name: str, bot: discord.Client = None) -> str:
    """
    Generates a unique black-and-white 1984-style Soviet pilot portrait for
    the given pilot name using OpenAI's image API (DALL-E 3), then archives
    it to a Discord channel for a stable, permanent URL.

    Falls back to a deterministic placeholder image if IMAGE_GEN_API_KEY is
    not configured, generation fails, or bot is not supplied (e.g. in
    contexts where we don't have a client to store the result). This keeps
    the bot fully functional even before an image-gen provider is wired up.
    """
    if not Config.IMAGE_GEN_API_KEY:
        return await _fetch_placeholder(pilot_name)

    prompt = _build_avatar_prompt(pilot_name)

    try:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=Config.IMAGE_GEN_API_KEY)
        result = await client.images.generate(
            model="dall-e-3",
            prompt=prompt,
            size="1024x1024",
            quality="standard",
            style="natural",
            n=1,
            response_format="b64_json",
        )
        b64_data = result.data[0].b64_json
        import base64
        image_bytes = base64.b64decode(b64_data)
    except Exception:
        logger.exception("Avatar generation failed for %s; falling back to placeholder.", pilot_name)
        return await _fetch_placeholder(pilot_name)

    if bot is None:
        logger.warning("No bot instance supplied to generate_avatar(); cannot archive image, using placeholder.")
        return await _fetch_placeholder(pilot_name)

    slug = pilot_name.lower().replace(" ", "_").replace('"', "")
    stored_url = await _store_bytes_to_discord(bot, image_bytes, f"{slug}.png")
    if stored_url:
        return stored_url

    return await _fetch_placeholder(pilot_name)


def build_dossier_embed(record, member: discord.Member) -> discord.Embed:
    """'Личное дело' (Dossier) embed for the View Service Record context menu."""
    status = record["status"]
    status_colors = {
        "ACTIVE": discord.Color.dark_green(),
        "LOA": discord.Color.gold(),
        "FATIGUED": discord.Color.orange(),
        "KIA": discord.Color.dark_red(),
    }
    embed = discord.Embed(
        title=f'Личное дело — {record["soviet_name"]}',
        description=f'"{record["callsign"]}" — {record["current_rank"]}',
        color=status_colors.get(status, discord.Color.greyple()),
    )
    if record["avatar_url"]:
        embed.set_thumbnail(url=record["avatar_url"])

    embed.add_field(name="Squadron", value=record["squadron"] or "Unassigned", inline=True)
    embed.add_field(name="Airframe", value=record["airframe"] or "Unassigned", inline=True)
    embed.add_field(name="Status", value=status, inline=True)

    embed.add_field(name="Flight Hours", value=f'{record["flight_hours"]:.1f}', inline=True)
    embed.add_field(name="Sorties", value=str(record["sorties"]), inline=True)
    embed.add_field(
        name="Kills (Air / Ground)",
        value=f'{record["kills_air"]} / {record["kills_ground"]}',
        inline=True,
    )

    embed.add_field(name="Fatigue Level", value=f'{record["fatigue_score"]:.0f} / 100', inline=True)
    embed.add_field(name="Cheks Balance", value=f'{record["cheks"]} ₽', inline=True)
    embed.add_field(name="\u200b", value="\u200b", inline=True)

    medals = json.loads(record["earned_medals"] or "[]")
    embed.add_field(
        name="Medals",
        value=", ".join(medals) if medals else "None awarded",
        inline=False,
    )

    commendations = json.loads(record["commendations"] or "[]")
    if commendations:
        recent = commendations[-3:]
        text = "\n".join(f'• {c["reason"]}' for c in recent)
    else:
        text = "None"
    embed.add_field(name="Commendations (recent)", value=text, inline=False)

    reprimands = json.loads(record["reprimands"] or "[]")
    if reprimands:
        recent = reprimands[-3:]
        text = "\n".join(f'• {r["reason"]}' for r in recent)
    else:
        text = "None"
    embed.add_field(name="Reprimands (recent)", value=text, inline=False)

    embed.set_footer(text=f"Discord: {member.display_name}")
    return embed
