"""
Static reference data for the Soviet VVS Enlistment Bot.

Naming, rank, and unit data is drawn from general open-source research on
Soviet Air Force (VVS/VTA/PVO) structure and the Soviet-Afghan War (1979-1989)
order of battle. Regiment assignments below are the well-documented units
that historically rotated through Afghanistan on the airframes listed; treat
them as thematically authentic MILSIM flavor rather than a claim of exact
squadron/date lineage.
"""

import random

# ------------------------------------------------------------------
# Names
# ------------------------------------------------------------------

SOVIET_FIRST_NAMES = [
    "Aleksandr", "Dmitri", "Ivan", "Mikhail", "Sergei",
    "Nikolai", "Viktor", "Pavel", "Yevgeni", "Andrei",
    "Boris", "Gennadi", "Konstantin", "Leonid", "Oleg",
    "Vladimir", "Yuri", "Anatoli", "Igor", "Stepan",
]

SOVIET_LAST_NAMES = [
    "Volkov", "Sokolov", "Petrov", "Ivanov", "Kuznetsov",
    "Morozov", "Popov", "Fedorov", "Belov", "Orlov",
    "Zaitsev", "Bogdanov", "Vasiliev", "Semyonov", "Gromov",
    "Novikov", "Lebedev", "Kozlov", "Stepanov", "Ershov",
]

# Authentic Russian tactical-noun callsigns (translations for reference)
CALLSIGNS = [
    "Burya",    # Storm
    "Granit",   # Granite
    "Sokol",    # Falcon
    "Zvezda",   # Star
    "Groza",    # Thunderstorm
    "Orel",     # Eagle
    "Yastreb",  # Hawk
    "Molniya",  # Lightning
    "Skala",    # Cliff/Rock
    "Vikhr",    # Whirlwind
    "Kremen",   # Flint
    "Buran",    # Blizzard
    "Kondor",   # Condor
    "Shtorm",   # Storm (heavy)
    "Klinok",   # Blade
    "Yantar",   # Amber
    "Almaz",    # Diamond
    "Rubin",    # Ruby
]

# ------------------------------------------------------------------
# Rank progression (nickname short-form used in the 32-char prefix)
# ------------------------------------------------------------------

RANK_PROGRESSION = [
    "Junior Lieutenant",
    "Lieutenant",
    "Senior Lieutenant",
    "Captain",
    "Major",
]

RANK_SHORTFORM = {
    "Junior Lieutenant": "Jg.Lt.",
    "Lieutenant": "Lt.",
    "Senior Lieutenant": "Sr.Lt.",
    "Captain": "Capt.",
    "Major": "Major",
}

# Base flight-hours-to-next-rank thresholds (cumulative). Reprimands add
# +5 hours each to the NEXT threshold only (see economy/promotion logic).
PROMOTION_HOUR_THRESHOLDS = {
    "Junior Lieutenant": 15.0,   # hours needed to be eligible for Lieutenant
    "Lieutenant": 40.0,          # -> Senior Lieutenant
    "Senior Lieutenant": 80.0,   # -> Captain
    "Captain": 140.0,            # -> Major
}

# ------------------------------------------------------------------
# Airframe -> Historical Squadron mapping
# ------------------------------------------------------------------

AIRFRAME_SQUADRONS = {
    "MiG-21 Bis": "115th Guards Fighter Aviation Regiment",
    "MiG-29": "168th Fighter Aviation Regiment",
    "Su-17 Fitter": "136th Fighter-Bomber Aviation Regiment",
    "Su-25 Frogfoot": "378th Separate Assault Aviation Regiment",
    "Mi-8 Hip": "280th Helicopter Regiment (Transport)",
    "Mi-24 Hind": "280th Helicopter Regiment (Attack)",
}

AIRFRAME_OPTIONS = list(AIRFRAME_SQUADRONS.keys())

# ------------------------------------------------------------------
# Baza (shop) cosmetic role badges
# ------------------------------------------------------------------

BAZA_LUXURIES = {
    "cassette_player": {"label": "Sony Cassette Player", "cost": 100},
    "cigarettes": {"label": "Pack of West German Cigarettes", "cost": 50},
    "jeans": {"label": "Genuine Blue Jeans", "cost": 75},
    "chocolate": {"label": "Imported Swiss Chocolate", "cost": 60},
    "radio": {"label": "Shortwave Radio Set", "cost": 90},
}

BAZA_CUSTOM_CALLSIGN_COST = 150
COMMEND_BONUS_CHEKS = 100
REPRIMAND_PROMOTION_PENALTY_HOURS = 5.0

# ------------------------------------------------------------------
# Fatigue / R&R
# ------------------------------------------------------------------

FATIGUE_PER_HOUR = 15.0
FATIGUE_THRESHOLD = 100.0
RR_DURATION_HOURS = 48

# ------------------------------------------------------------------
# Cheks (currency) earn rates
# ------------------------------------------------------------------

CHEKS_PER_SORTIE = 10
CHEKS_PER_KILL = 5

# ------------------------------------------------------------------
# Weather / Intel flavor text pools
# ------------------------------------------------------------------

WEATHER_WIND = [
    "light and variable, 5-8 knots out of the northwest",
    "gusting 20-25 knots from the Hindu Kush with moderate wind shear below 3,000 ft AGL",
    "calm at the surface, but 35-knot shear reported by returning Su-17 flight",
    "steady 12 knots out of the south, kicking up dust along the valley floor",
]

WEATHER_VISIBILITY = [
    "visibility unrestricted, 10+ km",
    "visibility reduced to 3-4 km in blowing dust",
    "visibility 6 km, haze layer at 8,000 ft",
    "visibility below 2 km — dust storm warning in effect for the Bagram approach corridor",
]

WEATHER_SKY = [
    "clear skies, no significant cloud",
    "scattered cumulus at 12,000 ft, tops to 18,000",
    "broken stratus deck at 6,000 ft over the mountains",
    "high cirrus overcast, no precipitation expected",
]

WEATHER_TEMP_RANGES_C = [(-5, 5), (0, 12), (10, 24), (18, 34)]

INTEL_TOPICS = [
    "Suspected Mujahideen mortar teams repositioning along the Panjshir approaches; recommend armed recce prior to transport sorties.",
    "Increased radio chatter near the Salang Pass consistent with a resupply caravan moving under cover of darkness.",
    "Unconfirmed reports of MANPADS (Stinger-pattern) activity near the eastern ridgeline; helicopter crews advised to vary approach headings.",
    "Local informants report a fighting position being dug into the ridge overlooking the southern MSR; artillery spotting requested.",
    "Convoy of unknown composition reported moving through the Kunar valley; fast-mover flight recommended for visual ID.",
    "Signals intelligence suggests a rest/regroup posture in the northern sector; expect reduced contact through 0600Z.",
]
