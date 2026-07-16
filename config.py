"""
Central configuration, loaded from environment variables.

All Discord IDs (channels, roles) are configured via env vars rather than
hardcoded so the same codebase can be redeployed to a new guild without
code changes — set these in the Railway service's Variables tab.
"""

import os


def _get_int(name: str, default: int = 0) -> int:
    val = os.environ.get(name)
    return int(val) if val else default


class Config:
    DISCORD_TOKEN = os.environ.get("DISCORD_TOKEN", "")
    DATABASE_URL = os.environ.get("DATABASE_URL", "")

    GUILD_ID = _get_int("GUILD_ID")  # optional: for instant (non-global) slash sync during dev

    # Channels
    ADMIN_APPROVAL_CHANNEL_ID = _get_int("ADMIN_APPROVAL_CHANNEL_ID")
    FALLEN_HEROES_CHANNEL_ID = _get_int("FALLEN_HEROES_CHANNEL_ID")
    COMMISSAR_LOG_CHANNEL_ID = _get_int("COMMISSAR_LOG_CHANNEL_ID")
    AVATAR_STORAGE_CHANNEL_ID = _get_int("AVATAR_STORAGE_CHANNEL_ID")

    # Roles
    COMMISSAR_ROLE_ID = _get_int("COMMISSAR_ROLE_ID")
    ADMIN_ROLE_ID = _get_int("ADMIN_ROLE_ID")

    # Per-airframe squadron role IDs, keyed by airframe name.
    # Set as env vars like SQUADRON_ROLE_MIG21, SQUADRON_ROLE_MIG29, etc.
    SQUADRON_ROLE_IDS = {
        "MiG-21 Bis": _get_int("SQUADRON_ROLE_MIG21"),
        "MiG-29": _get_int("SQUADRON_ROLE_MIG29"),
        "Su-17 Fitter": _get_int("SQUADRON_ROLE_SU17"),
        "Su-25 Frogfoot": _get_int("SQUADRON_ROLE_SU25"),
        "Mi-8 Hip": _get_int("SQUADRON_ROLE_MI8"),
        "Mi-24 Hind": _get_int("SQUADRON_ROLE_MI24"),
    }

    # Role granted to ACTIVE pilots and removed when FATIGUED/KIA/LOA
    ACTIVE_FLYER_ROLE_ID = _get_int("ACTIVE_FLYER_ROLE_ID")

    # OpenAI API key used for real avatar generation (utils.generate_avatar).
    # If unset, the bot falls back to a deterministic placeholder image.
    IMAGE_GEN_API_KEY = os.environ.get("IMAGE_GEN_API_KEY", "")


def has_commissar_perms(member) -> bool:
    """Admins/Commissars gate used across restricted commands."""
    role_ids = {r.id for r in getattr(member, "roles", [])}
    if member.guild_permissions.administrator:
        return True
    return Config.COMMISSAR_ROLE_ID in role_ids or Config.ADMIN_ROLE_ID in role_ids
