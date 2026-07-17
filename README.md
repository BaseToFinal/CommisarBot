# Soviet VVS Enlistment Bot

A Discord bot (discord.py 2.x) for a DCS World Cold War MILSIM server simulating
a Soviet Air Force enlistment and administrative system during the
Soviet-Afghan War (circa 1984).

## Features

- **`/enlist`** — Randomly generated Soviet identity + callsign, airframe/squadron
  select menu, automatic nickname formatting (32-char safe), mock avatar generation.
- **`/transfer`** — Change airframe/squadron; stats, medals, currency, and name untouched.
- **`/loa request` / `/loa return`** — LOA workflow with admin Approve/Deny buttons.
- **`/mark_kia`** — Admin-only permadeath: locks the profile, posts a memorial embed
  in #fallen-heroes, archives the full record, strips roles. Must `/enlist` fresh after.
- **`/rest`** — 48-hour R&R that resets fatigue; `/logstats` auto-applies fatigue and
  auto-grounds pilots who cross the fatigue threshold.
- **`/reprimand` / `/commend`** — Commissar discipline log; reprimands add +5 hours
  to the next promotion threshold, commendations grant a Cheks bonus.
- **`/baza`** — Cheks shop: custom callsign unlock, cosmetic role badges.
- **`/weather` / `/intel`** — Atmospheric 1980s-style briefings.
- **`/promote` / `/award` / `/logstats`** — Admin record management.
- **`/profile`** and **"View Service Record"** — Slash command and right-click/long-press
  context menu, both showing the full "Личное дело" dossier embed: name, callsign,
  rank, squadron, airframe, flight hours/sorties/kills, fatigue, Cheks balance,
  medals, and recent commendations/reprimands, with the pilot's generated photo
  as the embed thumbnail.

## Project layout

```
main.py              # entrypoint, cog loader, slash command sync
config.py            # env-var driven configuration + permission check
data.py              # names, callsigns, ranks, squadron mapping, flavor text
db.py                # asyncpg data access layer (all SQL lives here)
utils.py             # nickname formatting, embed builders, avatar mock
schema.sql           # PostgreSQL schema (applied automatically on boot)
cogs/
  enlistment.py       # /enlist
  transfer.py         # /transfer
  loa.py              # /loa request, /loa return
  fatigue_kia.py       # /mark_kia, /rest
  commissar.py        # /reprimand, /commend
  economy.py          # /baza, /custom_callsign
  briefings.py         # /weather, /intel
  admin.py             # /promote, /award, /logstats
  service_record.py    # "View Service Record" context menu
```

## Setup

1. Copy `.env.example` to `.env` (for local dev) and fill in `DISCORD_TOKEN` and
   a local/dev `DATABASE_URL`. On Railway, attach a Postgres plugin instead —
   `DATABASE_URL` is injected automatically.
2. Install dependencies:
   ```
   pip install -r requirements.txt
   ```
3. Run locally:
   ```
   python main.py
   ```
   `schema.sql` is applied automatically (idempotent — safe on every boot).

## Railway deployment

1. Push this repo to GitHub and create a new Railway project from it.
2. Add a **PostgreSQL** plugin to the project — `DATABASE_URL` is set automatically.
3. In the service's **Variables** tab, set `DISCORD_TOKEN` plus the channel/role
   IDs listed in `.env.example` (squadron roles, admin approval channel,
   fallen-heroes channel, commissar/admin roles, active-flyer role).
4. Railway will use the `Procfile` (`worker: python main.py`) to start the bot.
5. Leave `GUILD_ID` unset for a global slash-command sync (~1 hour to propagate),
   or set it during development for instant guild-scoped sync.

## Discord application setup

- Enable the **Server Members Intent** in the Discord Developer Portal (required
  for nickname edits and role management) — the bot requests `Intents.members`.
- Invite the bot with `applications.commands` + `bot` scopes and these permissions:
  Manage Nicknames, Manage Roles, Send Messages, Embed Links, Manage Threads (if
  used), Use Application Commands.
- Make sure the bot's role sits **above** the squadron/cosmetic/active-flyer roles
  it needs to assign, and above the ranks it needs to rename.

## Reusing your existing pilot photos (avatar pool)

If you already have a Discord channel full of AI-generated pilot portraits,
the bot can pull from that pool automatically instead of generating a new
image every time someone enlists.

1. Set `PILOT_PHOTO_POOL_CHANNEL_ID` to that channel's ID.
2. Run `/sync_avatar_pool` (Admin/Commissar only) once — it scans the
   channel's message history, finds every image attachment, and registers
   them in the database. Safe to re-run any time you add more images; it
   skips ones it's already indexed.
3. Check `/avatar_pool_stats` any time to see how many photos are available
   vs. already assigned.

From then on, every `/enlist` draws a random **unused** photo from that pool
first, marks it used, and assigns it to the new pilot — no two pilots get
the same photo. Once the pool runs out, the bot automatically falls back to
generating a new AI portrait (if `IMAGE_GEN_API_KEY` is set), and finally to
a placeholder image if neither is available. Nothing needs to be reconfigured
when the pool empties — it degrades gracefully on its own.

## AI-generated pilot portraits (fallback / supplement)

## Rank and medal icons on service profiles

Ranks and medals can have icons attached, stored once and automatically
reused everywhere that rank or medal appears — you never have to re-upload
the same image twice.

- **`/set_rank_image [rank] [image]`** (Admin) — upload the icon for one of
  the 5 ranks. It appears next to the pilot's name at the top of their
  `/profile`.
- **`/set_medal_image [medal_id] [image]`** (Admin) — pre-register an icon
  for a medal name before it's ever awarded.
- **`/award @user [medal_id] [image]`** — the `image` parameter is optional.
  The *first* time a given medal name is awarded, attach its icon and it's
  saved permanently; every later `/award` using that same name (matched
  case-insensitively) automatically pulls the stored icon — no need to
  re-attach it.
- **`/medal_catalog`** (Admin) — lists every medal with a registered icon.

On `/profile`, the main dossier card shows the pilot's photo as usual, plus
the rank icon next to their name, and one small icon card per earned medal
that has a registered icon (medals without one still show up in the text
list, just without an icon). Discord limits a message to 10 embeds total,
so if a pilot has an unusually large number of medals, the icon gallery
caps at 9 and the rest still appear in the text-only medals field.

`utils.generate_avatar()` generates a unique black-and-white 1984-style Soviet
pilot portrait for every enlisted member using OpenAI's DALL-E 3 API, then
uploads it to a dedicated Discord channel to get a stable, permanent CDN URL
(no separate image-hosting service needed).

To enable it:
1. Get an OpenAI API key with image-generation access.
2. Set `IMAGE_GEN_API_KEY` in your environment/Railway variables.
3. Create a private text channel (e.g. `#avatar-archive`) that only the bot
   can see, and set its ID as `AVATAR_STORAGE_CHANNEL_ID`.

If `IMAGE_GEN_API_KEY` is left blank, or generation fails for any reason
(rate limit, content filter, network error), the bot automatically falls
back to a deterministic placeholder image so `/enlist` never breaks.

Swapping providers: the generation call is isolated in `_build_avatar_prompt`
and the `AsyncOpenAI` block inside `generate_avatar()` in `utils.py` — replacing
it with Stability AI, Azure OpenAI, or another provider only requires editing
that one function; everything downstream (avatar_url column, dossier embed
thumbnail, memorial embed thumbnail) is provider-agnostic.

## Personnel Office panel (one-click profile access)

Rather than relying on people remembering `/profile`, an admin can post a
persistent panel with buttons anyone can click at any time:

- **`/post_personnel_office`** (Admin) — posts the panel in the current
  channel. Consider pinning it in a channel like `#personnel-office`.
- 🪖 **View My Profile** button — shows the clicker's own dossier (ephemeral,
  only they see it).
- ⭐ **Rank Structure** button — shows the full rank hierarchy reference.

The panel survives bot restarts (it's registered as a persistent view on
every boot), so you only need to post it once.

Also available as direct commands for anyone who prefers typing:
- **`/ranks`** — same rank structure reference
- **`/roster [airframe]`** — squadron roster (or the whole server's active
  roster if no airframe is specified), sorted by status then rank, with
  🟢/🟠/🟡/⚫ status markers for at-a-glance accountability

## Editing pilot records as an admin

Three ways to modify a pilot's record, depending on what you're doing:

- **`/logstats @user [sorties] [hours] [ground_kills] [air_kills]`** — the
  normal "log a mission" tool. **Adds** to existing totals and
  auto-calculates fatigue/Cheks earned.
- **`/edit_pilot @user [rank] [flight_hours] [sorties] [kills_ground] [kills_air] [cheks] [fatigue_score]`** —
  directly **sets** any of these to an exact value instead of adding to
  them. All parameters are optional — only pass the ones you want to
  change. Use this for corrections (a mistyped `/logstats` entry) or
  backdating (a pilot joining partway through a campaign with prior
  hours). Changing rank here also updates their nickname, same as
  `/promote`.
- **`/promote`** and **`/award`** — dedicated commands for rank and medals
  specifically (see above), since those also handle nickname updates and
  icon assignment respectively.

Every change through any of these is logged to the `commissar_log` table
for an audit trail.

## Live DCS server status & Daily Orders

**Important constraint this was built around:** if your DCS server is
managed by a third-party host that runs its own DCSServerBot in *their*
Discord server (not yours), your bot has no way to read that data — bots
can only see channels in servers they've been added to, and Discord's
"Follow Channel" feature requires admin permissions on the source server
that a renter typically won't have. This system is designed around that
reality rather than assuming access you may not have.

**How it actually works:**
- **`/set_daily_conditions [text]`** (Admin) — the primary, always-reliable
  path. Paste whatever server/mission/weather info you can see (e.g. from
  your host's status page or Discord channel) and it gets staged for the
  next Daily Orders post.
- **Real-world reference weather** — fully automatic and independent of
  the DCS server entirely. Pulls live METAR from NOAA's public
  aviationweather.gov API for a real-world airport (`METAR_ICAO_CODE`,
  defaults to Kabul/OAKB to match the Soviet-Afghan War setting). This is
  genuinely real *current* weather for that real location — not a read of
  your mission's actual scripted DCS weather, and the Daily Orders embed
  labels it clearly as a reference rather than claiming otherwise.
- **DCSServerBot channel reading** (dormant unless configured) — if
  `DCS_STATUS_CHANNEL_ID` is set AND your bot happens to have access to
  that channel (e.g. you self-host DCSServerBot in your own server), this
  takes priority as an automatic source and the manual staging becomes a
  fallback. Most third-party-hosted setups won't have this access, and
  the system works completely fine without it.

**Setup:**
1. Set `DAILY_ORDERS_CHANNEL_ID` to where you want Daily Orders posted.
2. Optionally set `DAILY_ORDERS_POST_HOUR_UTC` (default 12, UTC) for the
   daily auto-post time.
3. Optionally set `METAR_ICAO_CODE` if you want reference weather for a
   different real-world airport (e.g. matching a different DCS map).
4. Leave `DCS_STATUS_CHANNEL_ID` unset unless you specifically have bot
   access to a channel where DCSServerBot posts.

**Commands:**
- **`/server_status`** — anyone, on-demand check (staged conditions +
  real-world METAR, plus live DCSServerBot data if that access exists)
- **`/daily_orders`** (Admin) — generate and post Daily Orders immediately
- **`/set_daily_conditions [text]`** (Admin) — stage server/mission/weather
  info manually
- **`/set_mission_objective [text]`** (Admin) — stage the mission objective
- **`/set_readiness [condition]`** (Admin) — stage readiness (Combat
  Readiness №1/2/3, Soviet VVS style)
- **`/assign_crew [user]`** / **`/unassign_crew [user]`** (Admin) —
  hand-pick crew for the next Daily Orders, overriding the default full
  active roster
- **`/clear_crew_override`** (Admin) — revert to auto (full active roster)

Daily Orders posts automatically once per day at the configured hour using
whatever's staged (or defaults/full roster if nothing was set), then
resets objective/conditions/readiness/crew override and increments the
mission number for the next cycle. `/daily_orders` follows the same
staging/reset behavior for a forced post.



## Pilot backstories & service records

Every enlisted pilot gets a full, procedurally generated personal file
(similar in depth to a real Soviet личное дело) shown on `/profile`:

**Service Record** (structured):
- Nationality (correlated with birth republic, with realistic minority
  representation — the USSR was multi-ethnic)
- Social origin (из рабочих / из крестьян / из служащих — a real Soviet
  bureaucratic category)
- Party/Komsomol status
- Marital status, with a named spouse and children where applicable
- Military education — a real historical Soviet aviation academy, matched
  to fixed-wing vs. helicopter airframe, with a graduation year
- Pilot qualification class (Military Pilot 3rd/2nd/1st Class — "Sniper
  Pilot" is deliberately excluded from auto-generation since it's a
  veteran-only honor, not something a fresh 20-something would hold)
- A distinguishing physical feature
- Next of kin (mother or father, named, at the same birthplace)

**Personal File** (narrative): birthplace (any of the 15 real Soviet
republics), birthdate (skewed early-20s as of 1986), family background,
how they joined DOSAAF/aviation, and a personal trait, combined into a
brief unique paragraph.

This was built for differentiation at scale — tested with 500 generated
backstories (zero grammar/logic errors) and 150 simulated enlistments with
random names (zero duplicate narratives, zero duplicate service records).
One caveat found during testing: the *name* pool itself (300 combinations)
will produce some duplicate first+last names past ~100 pilots, even though
their birthdate/backstory/service record stay fully unique — let me know
if you'd like the name pool expanded to reduce that.

- **`/edit_pilot_bio [user] [birthplace] [birthdate] [backstory] [service_record]`**
  (Admin) — manually override any of these fields. All optional; only pass
  what you want to change. `birthdate` must be `YYYY-MM-DD`.
- **`/regenerate_backstory [user]`** (Admin) — throw out the current bio
  and roll a completely new random one (including service record).

## Extensibility note (DCSDiscordBot integration)

`db.py` isolates all SQL behind plain async functions, and `config.py` isolates
all Discord IDs behind env vars — both are intentionally decoupled from the
cogs so that a future integration layer (e.g. reading server/mission stats from
DCSDiscordBot and feeding them into `/logstats`-equivalent calls) can be added
as a new cog without touching existing command logic.
