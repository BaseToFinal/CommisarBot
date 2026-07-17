"""
Static reference data for the Soviet VVS Enlistment Bot.

Naming, rank, and unit data is drawn from general open-source research on
Soviet Air Force (VVS/VTA/PVO) structure and the Soviet-Afghan War (1979-1989)
order of battle. Regiment assignments below are the well-documented units
that historically rotated through Afghanistan on the airframes listed; treat
them as thematically authentic MILSIM flavor rather than a claim of exact
squadron/date lineage.
"""

import datetime
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
    "Lieutenant Colonel",
    "Colonel",
    "Major General",
    "Lieutenant General",
    "Colonel General",
    "General of the Army",
    "Marshal of the Soviet Union",
]

RANK_SHORTFORM = {
    "Junior Lieutenant": "Jr.Lt.",
    "Lieutenant": "Lt.",
    "Senior Lieutenant": "Sr.Lt.",
    "Captain": "Capt.",
    "Major": "Maj.",
    "Lieutenant Colonel": "Lt.Col.",
    "Colonel": "Col.",
    "Major General": "Maj.Gen.",
    "Lieutenant General": "Lt.Gen.",
    "Colonel General": "Col.Gen.",
    "General of the Army": "Gen.Army",
    "Marshal of the Soviet Union": "Marshal SU",
}

# Base flight-hours-to-next-rank thresholds (cumulative). Reprimands add
# +5 hours each to the NEXT threshold only (see economy/promotion logic).
# Marshal of the Soviet Union has no entry — it's the top of the hierarchy
# (historically a distinguished/political appointment rather than something
# earned purely by hours), so there's nothing beyond it to threshold against.
PROMOTION_HOUR_THRESHOLDS = {
    "Junior Lieutenant": 15.0,            # -> Lieutenant
    "Lieutenant": 40.0,                   # -> Senior Lieutenant
    "Senior Lieutenant": 80.0,            # -> Captain
    "Captain": 140.0,                     # -> Major
    "Major": 220.0,                       # -> Lieutenant Colonel
    "Lieutenant Colonel": 320.0,          # -> Colonel
    "Colonel": 450.0,                     # -> Major General
    "Major General": 600.0,               # -> Lieutenant General
    "Lieutenant General": 800.0,          # -> Colonel General
    "Colonel General": 1050.0,            # -> General of the Army
    "General of the Army": 1350.0,        # -> Marshal of the Soviet Union
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

# ------------------------------------------------------------------
# Daily Orders — readiness conditions (Soviet VVS combat readiness levels)
# ------------------------------------------------------------------

READINESS_CONDITIONS = [
    "Боевая готовность №1 — Immediate Launch",
    "Боевая готовность №2 — Standby (15 min)",
    "Боевая готовность №3 — Rest / Maintenance",
]

DEFAULT_READINESS = READINESS_CONDITIONS[1]
DEFAULT_MISSION_OBJECTIVE = "Awaiting orders from Group Command — objective not yet set."

# ------------------------------------------------------------------
# Pilot backstory generation
# ------------------------------------------------------------------
# The server is set in 1986; pilots are generated as if born in one of the
# 15 real Soviet Socialist Republics of the era, mostly in their early
# 20s at the time of enlistment (i.e. born early-to-mid 1960s). City names
# are real historical Soviet-era names for the period.

SOVIET_FEMALE_FIRST_NAMES = [
    "Yelena", "Natalia", "Svetlana", "Irina", "Olga", "Tatiana", "Galina",
    "Lyudmila", "Marina", "Nina", "Vera", "Anna", "Larisa", "Valentina", "Zoya",
]

SSR_BIRTHPLACES = {
    "Russian SFSR": ["Moscow", "Leningrad", "Novosibirsk", "Rostov-on-Don", "Volgograd", "Sverdlovsk", "Kazan"],
    "Ukrainian SSR": ["Kiev", "Kharkov", "Odessa", "Dnepropetrovsk", "Lvov", "Donetsk"],
    "Byelorussian SSR": ["Minsk", "Gomel", "Vitebsk", "Mogilev"],
    "Uzbek SSR": ["Tashkent", "Samarkand", "Bukhara"],
    "Kazakh SSR": ["Alma-Ata", "Karaganda", "Chimkent"],
    "Georgian SSR": ["Tbilisi", "Kutaisi", "Batumi"],
    "Azerbaijan SSR": ["Baku", "Ganja", "Sumgait"],
    "Lithuanian SSR": ["Vilnius", "Kaunas", "Klaipeda"],
    "Moldavian SSR": ["Kishinev", "Tiraspol", "Beltsy"],
    "Latvian SSR": ["Riga", "Daugavpils", "Liepaja"],
    "Kirghiz SSR": ["Frunze", "Osh"],
    "Tajik SSR": ["Dushanbe", "Khujand"],
    "Armenian SSR": ["Yerevan", "Gyumri"],
    "Turkmen SSR": ["Ashkhabad", "Chardzhou"],
    "Estonian SSR": ["Tallinn", "Tartu"],
}

# Nationality (национальность) — a mandatory field on real Soviet internal
# documents, distinct from citizenship. Weighted toward each republic's
# titular nationality (listed multiple times) with realistic minority
# possibilities mixed in, since the USSR was multi-ethnic throughout.
REPUBLIC_NATIONALITIES = {
    "Russian SFSR": ["Russian", "Russian", "Russian", "Tatar", "Chuvash", "Bashkir"],
    "Ukrainian SSR": ["Ukrainian", "Ukrainian", "Ukrainian", "Russian"],
    "Byelorussian SSR": ["Belorussian", "Belorussian", "Belorussian", "Russian"],
    "Uzbek SSR": ["Uzbek", "Uzbek", "Uzbek", "Russian", "Tajik"],
    "Kazakh SSR": ["Kazakh", "Kazakh", "Kazakh", "Russian"],
    "Georgian SSR": ["Georgian", "Georgian", "Georgian", "Armenian", "Russian"],
    "Azerbaijan SSR": ["Azerbaijani", "Azerbaijani", "Azerbaijani", "Russian", "Armenian"],
    "Lithuanian SSR": ["Lithuanian", "Lithuanian", "Lithuanian", "Russian", "Polish"],
    "Moldavian SSR": ["Moldavian", "Moldavian", "Moldavian", "Ukrainian", "Russian"],
    "Latvian SSR": ["Latvian", "Latvian", "Latvian", "Russian"],
    "Kirghiz SSR": ["Kirghiz", "Kirghiz", "Kirghiz", "Russian"],
    "Tajik SSR": ["Tajik", "Tajik", "Tajik", "Uzbek", "Russian"],
    "Armenian SSR": ["Armenian", "Armenian", "Armenian", "Russian"],
    "Turkmen SSR": ["Turkmen", "Turkmen", "Turkmen", "Russian"],
    "Estonian SSR": ["Estonian", "Estonian", "Estonian", "Russian"],
}

# Social origin (социальное происхождение) — a standard bureaucratic
# category on Soviet personal-file questionnaires (anketa).
SOCIAL_ORIGINS = [
    ("из рабочих", "worker family"),
    ("из крестьян", "peasant family"),
    ("из служащих", "family of office employees"),
]

PARTY_STATUS_OPTIONS = [
    "Member of the Komsomol",
    "Candidate Member, CPSU",
    "Non-Party",
]
# Most pilots this age are Komsomol members; CPSU candidacy and non-party
# status are both realistic but less common for junior officers.
PARTY_STATUS_WEIGHTS = [70, 15, 15]

# Real historical Soviet higher military aviation schools, split by
# fixed-wing vs. helicopter training pipelines.
FIXED_WING_ACADEMIES = [
    "Kachin Higher Military Aviation School of Pilots",
    "Armavir Higher Military Aviation School of Pilots",
    "Chernigov Higher Military Aviation School of Pilots",
    "Barnaul Higher Military Aviation School of Pilots",
]
HELICOPTER_ACADEMIES = [
    "Syzran Higher Military Aviation School of Pilots",
]

# Soviet VVS pilot qualification classes. "Sniper Pilot" (летчик-снайпер),
# the most elite distinction, is deliberately excluded from generation —
# it's a veteran-only honor that wouldn't realistically be auto-assigned
# to a freshly commissioned pilot in his early 20s. Weighted heavily
# toward 3rd class, the standard starting qualification.
PILOT_CLASSIFICATIONS = [
    "Military Pilot, 3rd Class",
    "Military Pilot, 2nd Class",
    "Military Pilot, 1st Class",
]
PILOT_CLASSIFICATION_WEIGHTS = [70, 25, 5]

DISTINGUISHING_FEATURES = [
    "a small scar above the left eyebrow from a childhood accident",
    "a faded tattoo of an anchor on his forearm from a summer spent near the Black Sea",
    "notably tall for his squadron, often the subject of jokes about cockpit legroom",
    "a habit of tapping his class ring against the canopy rail before every flight",
    "a slight limp from a training injury, not enough to ground him",
    "keeps his hair regulation-short but is known to grumble about it",
    "a burn scar on his right hand from an engine fire during flight school",
    "unusually good eyesight, noted favorably in his flight school evaluations",
    "no distinguishing marks of note",
    "a birthmark on his neck that his mother always said brought good luck",
]

BACKSTORY_FAMILY_BACKGROUNDS = [
    "the son of a factory foreman",
    "raised by a schoolteacher mother after his father's early death",
    "from a family of collective farmers",
    "the youngest of four brothers in a railway worker's household",
    "raised in a military family, his father a decorated infantry veteran",
    "the son of a coal miner",
    "from a family of dockworkers",
    "raised by his grandparents after his parents moved for factory work",
    "the son of a local Party committee official",
    "from a family with a long tradition of military service",
    "the son of a shipyard engineer",
    "raised in a household of schoolteachers",
]

BACKSTORY_JOIN_REASONS = [
    'joined DOSAAF as a teenager, drawn in by a glider demonstration at a regional youth festival',
    "was recommended for flight school after excelling in his local DOSAAF aviation club",
    "applied to the aviation academy after his older brother's stories of VVS service",
    "was inspired to fly after watching interceptors overhead during childhood",
    "enrolled in a DOSAAF parachute club before transferring to powered flight training",
    "was selected for pilot training during his mandatory military service",
    "grew up near an airfield and spent his youth watching the aircraft come and go",
    "followed a cousin's path into military aviation after finishing secondary school",
    "won a regional aeromodelling competition that caught the eye of a DOSAAF instructor",
]

BACKSTORY_TRAITS = [
    "known among his squadron mates for his dry sense of humor",
    "quiet and methodical, rarely speaking unless it matters",
    "a passionate chess player who keeps a travel set in his flight bag",
    "known for an easy confidence that steadies newer pilots before a sortie",
    "known for writing letters home every week without fail",
    "a keen amateur mechanic who tinkers with radios in his off hours",
    "rarely without a well-worn paperback novel in his flight bag",
    "known to hum old folk songs while pre-flighting his aircraft",
    "an avid football fan who never misses a chance to talk about it",
    "meticulous about his gear, to the point of good-natured teasing from others",
]


def generate_backstory(first_name: str, last_name: str, airframe: str = None) -> dict:
    """
    Generates a full Soviet-style personal file (личное дело) for a newly
    enlisted pilot: birthplace/birthdate, nationality, social origin, Party/
    Komsomol status, marital status, military education, pilot
    qualification class, a distinguishing feature, next of kin, and a
    brief unique narrative backstory. Ages skew early 20s as of 1986
    (server setting). With 15 republics x ~4 cities each, correlated
    nationality options, 3 social origins, ~5 party statuses, marital
    status with named spouses/children, 5 academies, 3 qualification
    classes, 10 distinguishing features, 12 family backgrounds, 9 join
    reasons, 10 traits, and a near-continuous birthdate — the combined
    space is large enough that 100+ pilots will not read as copies of
    each other.
    """
    republic = random.choice(list(SSR_BIRTHPLACES.keys()))
    city = random.choice(SSR_BIRTHPLACES[republic])
    birth_place = f"{city}, {republic}"

    age = random.randint(20, 25)
    birth_year = 1986 - age
    birth_month = random.randint(1, 12)
    birth_day = random.randint(1, 28)  # avoids month-length edge cases
    birth_date = datetime.date(birth_year, birth_month, birth_day)

    nationality = random.choice(REPUBLIC_NATIONALITIES.get(republic, ["Russian"]))

    social_origin_ru, social_origin_en = random.choice(SOCIAL_ORIGINS)

    party_status = random.choices(
        PARTY_STATUS_OPTIONS, weights=PARTY_STATUS_WEIGHTS, k=1
    )[0]

    # Marital status: ~65% single, ~35% married (with a chance of children).
    if random.random() < 0.65:
        marital_status = "Single"
    else:
        spouse_first = random.choice(SOVIET_FEMALE_FIRST_NAMES)
        children = random.choices([0, 1, 2], weights=[50, 35, 15])[0]
        if children == 0:
            marital_status = f"Married; wife {spouse_first} {last_name}"
        else:
            child_word = "child" if children == 1 else "children"
            marital_status = f"Married; wife {spouse_first} {last_name}, {children} {child_word}"

    is_helicopter = bool(airframe) and airframe.startswith("Mi-")
    academy = random.choice(HELICOPTER_ACADEMIES if is_helicopter else FIXED_WING_ACADEMIES)
    commission_age = random.randint(21, 23)
    graduation_year = min(birth_year + commission_age, 1986)

    qualification = random.choices(
        PILOT_CLASSIFICATIONS, weights=PILOT_CLASSIFICATION_WEIGHTS, k=1
    )[0]

    distinguishing_feature = random.choice(DISTINGUISHING_FEATURES)

    kin_relation = random.choice(["Mother", "Father"])
    kin_first = random.choice(SOVIET_FEMALE_FIRST_NAMES) if kin_relation == "Mother" else random.choice(SOVIET_FIRST_NAMES)
    next_of_kin = f"{kin_relation}, {kin_first} {last_name}, {birth_place}"

    service_record_details = (
        f"Nationality: {nationality}\n"
        f"Social Origin: {social_origin_ru} ({social_origin_en})\n"
        f"Party Status: {party_status}\n"
        f"Marital Status: {marital_status}\n"
        f"Military Education: {academy} ({graduation_year})\n"
        f"Qualification: {qualification}\n"
        f"Distinguishing Features: {distinguishing_feature}\n"
        f"Next of Kin: {next_of_kin}"
    )

    family = random.choice(BACKSTORY_FAMILY_BACKGROUNDS)
    join_reason = random.choice(BACKSTORY_JOIN_REASONS)
    trait = random.choice(BACKSTORY_TRAITS)

    backstory = (
        f"Born in {birth_place}, {first_name} {last_name} is {family}. "
        f"He {join_reason}. Now {age}, he is {trait}."
    )

    return {
        "birth_place": birth_place,
        "birth_date": birth_date,
        "backstory": backstory,
        "service_record_details": service_record_details,
    }
