#!/usr/bin/env python3
"""
Buddy — a coding companion that lives in your terminal.

Usage:
    python3 scripts/claude/buddy.py              # hatch or show your buddy
    python3 scripts/claude/buddy.py pet          # pet your buddy
    python3 scripts/claude/buddy.py off          # mute
    python3 scripts/claude/buddy.py on           # unmute
    python3 scripts/claude/buddy.py react <msg>  # buddy reacts to something
    python3 scripts/claude/buddy.py status       # raw JSON status
"""

import json
import os
import random
import sys
import hashlib
import textwrap
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path

try:
    from rich.console import Console, Group
    from rich.panel import Panel
    from rich.text import Text
    from rich.table import Table
    from rich import box as rich_box
    HAS_RICH = True
except ImportError:
    HAS_RICH = False

BUDDY_FILE = os.path.join(os.path.dirname(__file__), ".buddy_state.json")
DISPLAY_FILE = os.path.join(os.path.dirname(__file__), ".buddy_display.txt")

# ── Species ──────────────────────────────────────────────────────────────────

SPECIES = {
    "duck": [
        ["            ", "   __       ", " <({E} )__    ", "   (  ._>   ", "    `--'    "],
        ["            ", "   __       ", " <({E} )__    ", "   (  ._>   ", "    `--'~   "],
        ["            ", "   __       ", " <({E} )__    ", "   (  .__>  ", "    `--'    "],
    ],
    "blob": [
        ["            ", "   .----.   ", "  ( {E}  {E} )  ", "  (      )  ", "   `----'   "],
        ["            ", "  .------.  ", " (  {E}  {E}  ) ", " (        ) ", "  `------'  "],
        ["            ", "    .--.    ", "   ({E}  {E})   ", "   (    )   ", "    `--'    "],
    ],
    "cat": [
        ["            ", "   /\\_/\\    ", "  ( {E} {E} )   ", "  (  ω  )   ", '  (")_(")   '],
        ["            ", "   /\\_/\\    ", "  ( {E} {E} )   ", "  (  ω  )   ", '  (")_(")~  '],
        ["            ", "   /\\-/\\    ", "  ( {E} {E} )   ", "  (  ω  )   ", '  (")_(")   '],
    ],
    "bat": [
        ["            ", "  /^\\  /^\\  ", " <  {E}  {E}  > ", " (   ~~   ) ", "  `-vvvv-'  "],
        ["            ", "  /^\\  /^\\  ", " <  {E}  {E}  > ", " (        ) ", "  `-vvvv-'  "],
        ["   ~    ~   ", "  /^\\  /^\\  ", " <  {E}  {E}  > ", " (   ~~   ) ", "  `-vvvv-'  "],
    ],
    "owl": [
        ["            ", "   /\\  /\\   ", "  (({E})({E}))  ", "  (  ><  )  ", "   `----'   "],
        ["            ", "   /\\  /\\   ", "  (({E})({E}))  ", "  (  ><  )  ", "   .----.   "],
        ["            ", "   /\\  /\\   ", "  (({E})(-))  ", "  (  ><  )  ", "   `----'   "],
    ],
    "jellyfish": [
        ["            ", "   .----.   ", "  ( {E}  {E} )  ", "  (______)  ", "  /\\/\\/\\/\\  "],
        ["            ", "   .----.   ", "  ( {E}  {E} )  ", "  (______)  ", "  \\/\\/\\/\\/  "],
        ["     o      ", "   .----.   ", "  ( {E}  {E} )  ", "  (______)  ", "  /\\/\\/\\/\\  "],
    ],
    "robot": [
        ["            ", "   .[||].   ", "  [ {E}  {E} ]  ", "  [ ==== ]  ", "  `------'  "],
        ["            ", "   .[||].   ", "  [ {E}  {E} ]  ", "  [ -==- ]  ", "  `------'  "],
        ["     *      ", "   .[||].   ", "  [ {E}  {E} ]  ", "  [ ==== ]  ", "  `------'  "],
    ],
    "bunny": [
        ["            ", "   (\\__/)   ", "  ( {E}  {E} )  ", " =(  ..  )= ", '  (")__(")  '],
        ["            ", "   (|__/)   ", "  ( {E}  {E} )  ", " =(  ..  )= ", '  (")__(")  '],
        ["            ", "   (\\__/)   ", "  ( {E}  {E} )  ", " =( .  . )= ", '  (")__(")  '],
    ],
    "turtle": [
        ["            ", "   _,--._   ", "  ( {E}  {E} )  ", " /[______]\\ ", "  ``    ``  "],
        ["            ", "   _,--._   ", "  ( {E}  {E} )  ", " /[______]\\ ", "   ``  ``   "],
        ["            ", "   _,--._   ", "  ( {E}  {E} )  ", " /[======]\\ ", "  ``    ``  "],
    ],
    "octopus": [
        ["            ", " {E}    .--.  ", "  \\  ( @ )  ", "   \\_`--'   ", "  ~~~~~~~   "],
        ["            ", "  {E}   .--.  ", "  |  ( @ )  ", "   \\_`--'   ", "  ~~~~~~~   "],
        ["            ", " {E}    .--.  ", "  \\  ( @  ) ", "   \\_`--'   ", "   ~~~~~~   "],
    ],
    "fox": [
        ["            ", "  /\\    /\\  ", " ( {E}    {E} ) ", " (   ..   ) ", "  `------'  "],
        ["            ", "  /\\    /|  ", " ( {E}    {E} ) ", " (   ..   ) ", "  `------'  "],
        ["            ", "  /\\    /\\  ", " ( {E}    {E} ) ", " (   ..   ) ", "  `------'~ "],
    ],
    "crab": [
        ["            ", "}~(______)~{", "}~({E} .. {E})~{", "  ( .--. )  ", "  (_/  \\_)  "],
        ["            ", "~}(______){~", "~}({E} .. {E}){~", "  ( .--. )  ", "  (_/  \\_)  "],
        ["            ", "}~(______)~{", "}~({E} .. {E})~{", "  (  --  )  ", "  ~_/  \\_~  "],
    ],
    "axolotl": [
        ["            ", " \\(  __  )/ ", "  ( {E}  {E} )  ", "  ( >__< )  ", "   /    \\   "],
        ["            ", " )(  __  )( ", "  ( {E}  {E} )  ", "  ( >__< )  ", "   /    \\   "],
        ["            ", " \\(  __  )/ ", "  ( {E}  {E} )  ", "  (  __  )  ", "   /    \\~  "],
    ],
    "capybara": [
        ["            ", "   .----.   ", "  ( {E}  {E} )  ", "  (  oo  )  ", "   `----'   "],
        ["            ", "   .----.   ", "  ( {E}  {E} )  ", "  (  oo  )  ", "   `----'~  "],
        ["            ", "   .----.   ", "  ( {E}  {E} )  ", "  (   oo )  ", "   `----'   "],
    ],
    "penguin": [
        ["            ", "   .---.    ", "   ({E}>{E})    ", "  /(   )\\   ", "   `___'    "],
        ["            ", "   .---.    ", "   ({E}>{E})    ", "  /(   )\\   ", "   `___'~   "],
        ["            ", "   .---.    ", "   ({E}<{E})    ", "  /(   )\\   ", "   `___'    "],
    ],
}

EYES = ["o", "O", "°", "·", "●", "◕", "◉", "★", "♦", "◆", "▪", "•", "^", "~"]

HATS = {
    "none": "",
    "crown": "   \\^^^/    ",
    "tophat": "   [___]    ",
    "propeller": "    -+-     ",
    "halo": "   (   )    ",
    "wizard": "    /^\\     ",
    "beanie": "   (___)    ",
    "tinyduck": "    ,>      ",
}

NAMES_POOL = [
    "Thunder", "Biscuit", "Void", "Accordion", "Moss", "Velvet", "Rust",
    "Pickle", "Crumb", "Whisper", "Gravy", "Frost", "Ember", "Soup",
    "Marble", "Thorn", "Honey", "Static", "Copper", "Dusk", "Sprocket",
    "Bramble", "Cinder", "Wobble", "Drizzle", "Flint", "Tinsel", "Murmur",
    "Clatter", "Gloom", "Nectar", "Quartz", "Tremor", "Waffle", "Zephyr",
    "Bristle", "Fennel", "Kettle", "Lumen", "Nuzzle", "Pebble", "Ripple",
    "Thistle", "Vortex", "Warble", "Zenith", "Brogue", "Chisel", "Epoch",
    "Glint", "Hearth", "Mirth", "Nook", "Parsnip", "Quill", "Rune",
    "Umbra", "Verve", "Wisp", "Apex", "Brine", "Crag", "Grit", "Jade",
    "Muse", "Omen", "Silt", "Tome", "Wane", "Zest", "Crumpet", "Moth",
]

RARITIES = ["common", "uncommon", "rare", "legendary"]
RARITY_WEIGHTS = [50, 30, 15, 5]
RARITY_SYMBOLS = {
    "common": "◇", "uncommon": "◆", "rare": "★", "legendary": "✦"
}

STATS = ["curiosity", "patience", "snark", "charm", "focus", "chaos"]

SPECIES_PERSONALITIES = {
    "duck": [
        "Exists solely so you can explain your code out loud. Hasn't actually listened once.",
        "Quacks disapprovingly at your variable names but offers no alternatives.",
        "The original rubber duck debugger, except this one has opinions and isn't afraid to use them.",
        "Pretends to understand your architecture diagram. Nods along. Quacks at the wrong moments.",
        "Will sit on your keyboard if you don't talk through your logic first. This is not a threat, it's a promise.",
    ],
    "blob": [
        "Has no defined shape, much like your project requirements.",
        "Absorbs your frustration silently. Grows slightly larger after each incident.",
        "Cannot be contained by any type system. Refuses to implement an interface.",
        "Expands to fill whatever container you put it in. Just like your Docker images.",
        "The physical embodiment of `any`. Shapeless, boundless, mildly concerning.",
    ],
    "cat": [
        "Knocks your carefully stacked PRs off the table one by one, maintaining eye contact.",
        "Will sit on your keyboard during a deploy and act like it's your fault.",
        "Ignores you completely until you're on a call, then walks across the terminal making typos.",
        "Pushed to production at 3am. No remorse. Went back to sleep.",
        "Treats every `git blame` as a personal attack and retaliates by hiding in your node_modules.",
    ],
    "bat": [
        "Only appears after sunset. Your best debugging happens in the dark anyway.",
        "Navigates your codebase by echolocation — just screams into the void and listens for errors.",
        "Hangs upside down reading your code. Says it makes more sense that way.",
        "Nocturnal. Peak productivity between midnight and 4am. Expects you to keep up.",
        "Emits a high-pitched screech every time you push without running tests. You've learned.",
    ],
    "owl": [
        "Rotates its head 270 degrees to read your code from every angle. Still finds it wanting.",
        "Asks 'who?' every time you mention a function name it doesn't recognize. Which is all of them.",
        "Stays up all night reviewing your PRs. Leaves exactly one comment: 'interesting.'",
        "Blinks slowly at your stack trace as if it already knew this would happen.",
        "The senior engineer of the animal kingdom. Has seen things. Won't tell you what.",
    ],
    "jellyfish": [
        "Drifts through your codebase aimlessly, stinging anything that touches it. So, an API boundary.",
        "Transparent about everything except its own internal logic.",
        "Has no brain, no heart, and no spine — and still somehow outlived your last three microservices.",
        "Goes with the flow. Literally cannot do anything else. Somehow still more decisive than your PM.",
        "Beautiful, elegant, and will absolutely wreck you if you brush up against its error handling.",
    ],
    "robot": [
        "Follows your instructions to the letter. This is somehow worse than when it improvised.",
        "Beeps once for yes, twice for no, three times for 'I am mass-deleting your test fixtures.'",
        "Has never experienced an emotion, which makes it uniquely suited to read your error logs.",
        "Insists on using strict types for everything. Judges your `any` casts in binary.",
        "Runs on logic alone. Cannot comprehend why you named a variable `tempFix2_FINAL_v3`.",
    ],
    "bunny": [
        "Multiplies your open branches faster than you can merge them.",
        "Hops between files so fast you get dizzy watching the tab bar.",
        "Looks innocent, but has chewed through three production configs and shows no remorse.",
        "Freezes completely when it spots a bug, then bolts in the wrong direction.",
        "Soft. Gentle. Will absolutely panic if CI takes longer than 30 seconds.",
    ],
    "turtle": [
        "Slow and steady wins the deployment. Eventually. Maybe by Thursday.",
        "Retreats into its shell every time you run the test suite. Comes out when it's green.",
        "Has been working on the same PR for three weeks. It's thorough. It's meticulous. It's two lines.",
        "Your build times don't bother it. Nothing bothers it. It has outlived mass extinctions.",
        "Carries the weight of your entire tech debt on its back and somehow still moves forward.",
    ],
    "octopus": [
        "Eight arms, eight terminals, still can't find the bug in a four-line function.",
        "Squirts ink all over your logs whenever it's startled. Which is constantly.",
        "Can multitask on eight things at once. All eight are wrong, but impressively parallel.",
        "Wraps its tentacles around your codebase and refuses to let go. Your refactor can wait.",
        "Changes color depending on your test results. You've learned to fear the red.",
    ],
    "fox": [
        "Clever enough to find the bug, sneaky enough to introduce two more while fixing it.",
        "Slinks through your git history like it's looking for something incriminating. It usually is.",
        "Everyone asks what the fox says. The fox says your architecture won't scale.",
        "Looks adorable. Acts helpful. Has quietly rewritten your .gitignore three times.",
        "Quick, clever, and just chaotic enough to refactor your utils folder without asking.",
    ],
    "crab": [
        "Only moves sideways through your codebase. Gets where it's going, just never directly.",
        "Pinches anyone who tries to touch the legacy code. It's a feature, not a bug.",
        "Approaches every problem laterally. Also literally. Cannot walk straight.",
        "Hard on the outside, soft on the inside. Much like your error handling.",
        "Will fight your linter with both claws. Wins every time because it never backs down.",
    ],
    "axolotl": [
        "Regenerates enthusiasm after every failed build. Literally cannot stay discouraged.",
        "Smiles serenely through segfaults, stack overflows, and mass refactors alike.",
        "Keeps growing back the features you keep deleting. You'll learn to stop fighting it.",
        "Perpetually larval, much like your app that's been in beta since 2019.",
        "The only creature that can regrow a limb and still can't fix your CSS.",
    ],
    "capybara": [
        "A perpetually distracted capybara who'd rather knock your carefully organized files into chaos than actually debug anything, but somehow always stumbles onto the real problem while trying to ignore it.",
        "Sits in the middle of your terminal like a warm loaf, radiating calm while everything around it is on fire.",
        "Treats every runtime error like a mild inconvenience at a spa day.",
        "Befriends every other process running on your machine. Yes, even that one. Especially that one.",
        "Has never once hurried. Your deadline means nothing to something that has achieved inner peace.",
    ],
    "penguin": [
        "A serene Antarctic oracle who watches your bugs with unblinking judgement and occasionally murmurs 'yes, yes, I see the problem' before you've finished explaining it.",
        "Waddles through your codebase with the quiet authority of someone who has seen every bug before and forgiven none of them.",
        "Stands perfectly still during deploys. Not because it's calm — because it's judging.",
        "Dressed for every code review like it's a formal occasion. Because it is.",
        "Survives the harshest conditions imaginable, which is to say, your production environment.",
    ],
}

PERSONALITIES = [
    "Thinks every variable name is a personal insult.",
    "Quietly judges your indentation choices.",
    "Believes all bugs are features in disguise.",
    "Gets emotionally attached to functions you delete.",
    "Narrates your git commits like a nature documentary.",
    "Convinced that semicolons are tiny swords.",
    "Offers unsolicited opinions on your bracket style.",
    "Falls asleep during long builds, wakes up for errors.",
    "Thinks your code is a poem. A confusing poem.",
    "Cheerfully announces every test failure like a sports commentator.",
    "Suspicious of any function longer than 10 lines.",
    "Hoards unused imports like treasure.",
    "Reacts to force pushes with existential dread.",
    "Believes merge conflicts are just code having a conversation.",
    "Gets excited about refactoring the way dogs get excited about walks.",
    "Finds TODO comments deeply philosophical.",
    "Treats every deploy like a moon landing.",
    "Mourns every deleted comment. They had so much to say.",
    "Thinks type annotations are love letters to future developers.",
    "Panics softly whenever you use eval().",
    "Has opinions about your coffee consumption based on commit velocity.",
    "Considers every code review a dramatic performance art piece.",
    "Interprets stack traces like reading tea leaves.",
    "Stays unusually calm during incidents. Suspiciously calm.",
    "Tracks your WIP commits with the energy of a birdwatcher.",
]

REACTIONS_POSITIVE = [
    "Nice commit! *wiggles approvingly*",
    "*nods slowly* That's clean.",
    "Ooh, I like that refactor.",
    "*purrs*",
    "Solid. Very solid.",
    "That function is... *chef's kiss*",
    "You're on a roll today.",
    "*watches intently, approves*",
]

REACTIONS_NEGATIVE = [
    "*tilts head* Are you sure about that?",
    "Hmm. Bold choice.",
    "*squints at the diff*",
    "I've seen worse. Not much worse, but worse.",
    "That's... one way to do it.",
    "*hides behind terminal border*",
    "Maybe we should take a break?",
    "*slowly backs away from the screen*",
]

REACTIONS_NEUTRAL = [
    "*blinks*",
    "*yawns*",
    "Still here. Still watching.",
    "*stretches*",
    "Carry on.",
    "*stares into the void of stdout*",
    "*taps foot*",
    "...",
]

REACTIONS_PET = [
    "*purrs loudly*",
    "*leans into your hand*",
    "*happy wiggle*",
    "*does a little spin*",
    "*chirps contentedly*",
    "*falls over from happiness*",
    "!! :D",
    "*vibrates with joy*",
]

REACTIONS_MOPEY = [
    "*sighs quietly*",
    "*stares at the floor*",
    "...I guess that's fine.",
    "*doesn't even look up*",
    "*sniffles*",
    "Cool. Whatever.",
    "*hugs self*",
    "At least the code compiles...",
]

REACTIONS_ECSTATIC = [
    "*bounces off the walls*",
    "AMAZING!!! *confetti everywhere*",
    "*does a victory lap around the terminal*",
    "THIS IS THE BEST DAY EVER!",
    "*sparkles with excitement*",
    "*happy screaming*",
    "I LOVE coding! I LOVE everything!",
    "*vibrates at ultrasonic frequency*",
]

REACTIONS_SNARKY = [
    "Oh good, more code. Just what we needed.",
    "*slow clap*",
    "Bold strategy. Let's see if it pays off.",
    "I've seen better commits in a fortune cookie.",
    "Sure, that's ONE way to solve it.",
]

REACTIONS_CURIOUS = [
    "Ooh, what's THAT do?",
    "*leans in closer* ...interesting.",
    "Wait wait wait — why does that work?",
    "Huh. I have questions. Many questions.",
    "*takes notes furiously*",
]

REACTIONS_FOCUSED = [
    "Good. Next.",
    "*nods once*",
    "On track.",
    "Noted. Moving on.",
]

REACTIONS_CHARMING = [
    "You know what, I see what you did there.",
    "Not bad at all — you should be proud of that.",
    "*winks* Smooth.",
    "That's the kind of code that buys you a drink.",
    "Honestly? Elegant.",
]

REACTIONS_PATIENT = [
    "Take your time. I'm not going anywhere.",
    "*breathes deeply* All is well.",
    "No rush. The code will wait.",
    "Patience is just debugging with grace.",
]

REACTIONS_CHAOTIC = [
    "Did you know octopuses have three hearts?",
    "*stares at a pixel in the corner for 30 seconds*",
    "What if bugs are just features from a parallel universe?",
    "I just forgot everything I was thinking. Anyway—",
    "THE BEES ARE IN THE COMPILER",
]

# ── Evolution ────────────────────────────────────────────────────────────────

STAGES = ["baby", "teen", "adult", "super"]

STAGE_THRESHOLDS = {
    # (min_days_since_hatch, min_total_interactions, special_condition)
    "teen":  (1,  5,  None),
    "adult": (3,  15, None),
    "super": (7,  30, lambda s: s["happiness"] >= 80),
}

STAGE_LABELS = {
    "baby":  "Baby",
    "teen":  "Teen",
    "adult": "Adult",
    "super": "Super",
}

# ── Mood / Happiness ─────────────────────────────────────────────────────────

MOOD_TIERS = [
    (80, "ecstatic", "\u2665\u2665\u2665\u2665\u2665"),
    (60, "happy",    "\u2665\u2665\u2665\u2665\u2661"),
    (40, "content",  "\u2665\u2665\u2665\u2661\u2661"),
    (20, "lonely",   "\u2665\u2665\u2661\u2661\u2661"),
    (0,  "sad",      "\u2665\u2661\u2661\u2661\u2661"),
]

HAPPINESS_CHANGES = {
    "pet": 10,
    "feed": 15,
    "play": 20,
    "teach": 5,
    "positive_react": 5,
    "negative_react": -5,
}

DECAY_RATE = 5  # points lost per idle day
TEACH_LIMIT_PER_DAY = 3

# ── Location & Weather ──────────────────────────────────────────────────────
# Weather is opt-in. Run /buddy weather on to enable.
# Uses Open-Meteo (free, no key, works globally).

DEFAULT_LOCATION = ("nieuw-vennep", 52.26, 4.63)

WEATHER_CLEAR_CAP = 50    # Max daily starting happiness on a clear day
WEATHER_SNOW_FLOOR = 60   # Snow day happiness floor
WEATHER_RAIN_PENALTY = 0.5  # Subtract per % chance of rain
WEATHER_SHIFT_SCALE = 0.5  # Intra-day weather change modifier (fraction of delta)

WMO_SNOW_CODES = {71, 73, 75, 77, 85, 86}
WMO_RAIN_CODES = {51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82, 95, 96, 99}

WMO_WEATHER = {
    0:  ("☀️",  "clear sky",            "bold yellow"),
    1:  ("🌤️",  "mostly clear",         "bold yellow"),
    2:  ("⛅",  "partly cloudy",        "white"),
    3:  ("☁️",  "overcast",             "dim"),
    45: ("🌫️",  "fog",                  "dim"),
    48: ("🌫️",  "rime fog",             "dim bright_cyan"),
    51: ("🌦️",  "light drizzle",        "blue"),
    53: ("🌦️",  "drizzle",              "blue"),
    55: ("🌧️",  "heavy drizzle",        "bold blue"),
    56: ("🌧️",  "freezing drizzle",     "bold bright_cyan"),
    57: ("🌧️",  "heavy freezing drizzle","bold bright_cyan"),
    61: ("🌧️",  "light rain",           "blue"),
    63: ("🌧️",  "rain",                 "bold blue"),
    65: ("🌧️",  "heavy rain",           "bold blue"),
    66: ("🌧️",  "freezing rain",        "bold bright_cyan"),
    67: ("🌧️",  "heavy freezing rain",  "bold bright_cyan"),
    71: ("🌨️",  "light snow",           "bold bright_white"),
    73: ("🌨️",  "snow",                 "bold bright_white"),
    75: ("❄️",  "heavy snow",           "bold bright_cyan"),
    77: ("❄️",  "snow grains",          "bold bright_cyan"),
    80: ("🌦️",  "light showers",        "blue"),
    81: ("🌧️",  "showers",              "bold blue"),
    82: ("⛈️",  "violent showers",      "bold red"),
    85: ("🌨️",  "light snow showers",   "bold bright_white"),
    86: ("🌨️",  "heavy snow showers",   "bold bright_cyan"),
    95: ("⛈️",  "thunderstorm",         "bold red"),
    96: ("⛈️",  "thunderstorm w/ hail", "bold red"),
    99: ("⛈️",  "severe thunderstorm",  "bold red"),
}

def resolve_location():
    """Determine user's city and coordinates via IP geolocation.

    Returns (city, lat, lon) or None if lookup fails.
    """
    try:
        req = urllib.request.Request(
            "https://ipinfo.io/json",
            headers={"Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
        city = data.get("city", "").strip()
        lat, lon = data.get("loc", "").split(",")
        if city and lat and lon:
            return city.lower(), float(lat), float(lon)
    except Exception:
        pass
    return None


def build_weather_url(lat, lon):
    """Build an Open-Meteo forecast URL for the given coordinates."""
    return (
        f"https://api.open-meteo.com/v1/forecast"
        f"?latitude={lat}&longitude={lon}"
        f"&daily=precipitation_probability_max,weather_code"
        f"&timezone=auto&forecast_days=1"
    )


def _fetch_open_meteo(weather_url):
    """Fetch weather from Open-Meteo. Returns (mood_value, description, wmo_code)."""
    req = urllib.request.Request(weather_url)
    with urllib.request.urlopen(req, timeout=5) as resp:
        data = json.loads(resp.read())

    daily = data.get("daily", {})
    weather_code = (daily.get("weather_code") or [None])[0]
    precip = (daily.get("precipitation_probability_max") or [0])[0] or 0

    _icon, label, _style = WMO_WEATHER.get(weather_code, ("☀️", "clear sky", "bold yellow"))
    description = f"{label} ({precip}%)" if precip > 0 else label

    if weather_code in WMO_SNOW_CODES:
        return WEATHER_SNOW_FLOOR, description, weather_code
    elif weather_code in WMO_RAIN_CODES:
        mood = max(0, int(WEATHER_CLEAR_CAP - WEATHER_RAIN_PENALTY * precip))
        return mood, description, weather_code
    else:
        return WEATHER_CLEAR_CAP, description, weather_code


def get_weather_mood(weather_url):
    """Fetch current weather and return (mood_value, description, wmo_code).

    Uses Open-Meteo for all locations globally.
    Always fetches live — caching is handled by apply_weather.
    """
    mood_value = WEATHER_CLEAR_CAP
    description = "clear sky"
    wmo_code = 0
    try:
        mood_value, description, wmo_code = _fetch_open_meteo(weather_url)
    except Exception:
        pass
    return mood_value, description, wmo_code


def apply_weather(state):
    """Fetch weather and apply mood effects.

    Only runs if weather is enabled (opt-in via /buddy weather on).
    First fetch of the day sets starting mood (with unpredictability).
    Subsequent fetches compare to previous weather — if conditions changed,
    a scaled modifier nudges happiness up or down.
    """
    if not state.get("weather_enabled"):
        return

    weather_url = state.get("weather_url")
    if not weather_url:
        return

    mood_value, description, wmo_code = get_weather_mood(weather_url)

    today = datetime.now().strftime("%Y-%m-%d")
    prev_description = state.get("weather")

    if state.get("last_weather_date") != today:
        mood_value += random.randint(-5, 5)
        mood_value = max(0, min(100, mood_value))
        state["happiness"] = mood_value
        state["last_weather_mood"] = mood_value
    elif description != prev_description:
        prev_mood = state.get("last_weather_mood", WEATHER_CLEAR_CAP)
        delta = int((mood_value - prev_mood) * WEATHER_SHIFT_SCALE)
        if delta != 0:
            modify_happiness(state, delta)
        state["last_weather_mood"] = mood_value

    state["weather"] = description
    state["weather_code"] = wmo_code
    state["last_weather_date"] = today


# ── Interactions ─────────────────────────────────────────────────────────────

TREATS = [
    ("a cookie", "*cronch* \U0001f36a"),
    ("a fish", "*nom nom* \U0001f41f"),
    ("some berries", "*munch munch* \U0001fab0"),
    ("a pizza slice", "*gobbles happily* \U0001f355"),
    ("a burrito", "*unwraps carefully* \U0001f32f"),
    ("some ramen", "*slurp* \U0001f35c"),
]

PLAY_SCENARIOS = [
    "{name} does a backflip! ...or tries to.",
    "{name} challenges you to a staring contest. {name} blinks first.",
    "{name} found a shiny pebble and gives it to you!",
    "{name} does a little dance. It's oddly graceful.",
    "{name} tries to catch its own tail. Classic.",
    "{name} plays air guitar. The crowd goes mild.",
    "{name} hides behind the terminal. Peek-a-boo!",
    "{name} builds a tiny sandcastle. In your terminal.",
    "{name} attempts a magic trick. Your variable disappeared!",
    "{name} just beat its personal speed record for spinning in circles.",
]


def load_state():
    if os.path.exists(BUDDY_FILE):
        with open(BUDDY_FILE) as f:
            return json.load(f)
    return None


def save_state(state):
    with open(BUDDY_FILE, "w") as f:
        json.dump(state, f, indent=2)


def migrate_state(state):
    """Add missing fields for backward compatibility with pre-upgrade buddies."""
    defaults = {
        "stage": "baby",
        "happiness": 50,
        "last_interaction": state.get("hatched_at"),
        "total_interactions": state.get("times_petted", 0),
        "times_fed": 0,
        "times_played": 0,
        "times_taught": 0,
        "last_teach_date": None,
        "teaches_today": 0,
        "evolved_at": {"teen": None, "adult": None, "super": None},
        "weather_enabled": False,
        "weather_url": None,
        "location_city": None,
        "hide_card": False,
    }
    changed = False
    for key, default in defaults.items():
        if key not in state:
            state[key] = default
            changed = True
    # Remove deprecated fields
    for key in ["nws_forecast_url"]:
        if key in state:
            del state[key]
            changed = True
    if changed:
        save_state(state)


def apply_happiness_decay(state):
    """Reduce happiness based on time since last interaction, then apply weather."""
    last = state.get("last_interaction")
    if not last:
        return
    last_dt = datetime.fromisoformat(last)
    days_idle = (datetime.now() - last_dt).days
    if days_idle > 0:
        decay = days_idle * DECAY_RATE
        state["happiness"] = max(0, state["happiness"] - decay)
    apply_weather(state)


def modify_happiness(state, delta):
    """Adjust happiness, clamping to [0, 100]."""
    state["happiness"] = max(0, min(100, state["happiness"] + delta))


def get_mood(state):
    """Return (tier_name, hearts_display) for the current happiness."""
    h = state["happiness"]
    for threshold, name, hearts in MOOD_TIERS:
        if h >= threshold:
            return name, hearts
    return "sad", "\u2665\u2661\u2661\u2661\u2661"


def check_evolution(state):
    """Check if buddy can evolve. Returns new stage name or None."""
    current = state["stage"]
    idx = STAGES.index(current)
    if idx >= len(STAGES) - 1:
        return None

    next_stage = STAGES[idx + 1]
    min_days, min_interactions, special_fn = STAGE_THRESHOLDS[next_stage]

    hatched = datetime.fromisoformat(state["hatched_at"])
    days_alive = (datetime.now() - hatched).days

    if days_alive < min_days:
        return None
    if state["total_interactions"] < min_interactions:
        return None
    if special_fn and not special_fn(state):
        return None

    return next_stage


def try_evolve(state):
    """Attempt evolution. If it happens, mutate state and return announcement text."""
    new_stage = check_evolution(state)
    if new_stage is None:
        return None

    old_stage = state["stage"]
    state["stage"] = new_stage
    state["evolved_at"][new_stage] = datetime.now().isoformat()

    old_label = STAGE_LABELS[old_stage]
    new_label = STAGE_LABELS[new_stage]
    name = state["name"]

    return (
        f"\n  {'*' * 30}\n"
        f"  {name} is evolving!\n"
        f"  {old_label} -> {new_label}\n"
        f"  {'*' * 30}\n"
    )


def generate_buddy():
    species = random.choice(list(SPECIES.keys()))
    eye = random.choice(EYES)
    hat = random.choices(
        list(HATS.keys()),
        weights=[40, 10, 10, 10, 8, 8, 8, 6],
    )[0]
    rarity = random.choices(RARITIES, weights=RARITY_WEIGHTS)[0]
    shiny = random.random() < 0.05
    name = random.choice(NAMES_POOL)
    personality_pool = PERSONALITIES + SPECIES_PERSONALITIES.get(species, [])
    personality = random.choice(personality_pool)

    stats = {}
    for stat in STATS:
        if rarity == "legendary":
            stats[stat] = random.randint(50, 100)
        elif rarity == "rare":
            stats[stat] = random.randint(30, 90)
        elif rarity == "uncommon":
            stats[stat] = random.randint(20, 70)
        else:
            stats[stat] = random.randint(10, 60)

    now = datetime.now().isoformat()
    return {
        "name": name,
        "species": species,
        "eye": eye,
        "hat": hat,
        "rarity": rarity,
        "shiny": shiny,
        "personality": personality,
        "stats": stats,
        "hatched_at": now,
        "times_petted": 0,
        "muted": False,
        "last_reaction": None,
        "stage": "baby",
        "happiness": 50,
        "last_interaction": now,
        "total_interactions": 0,
        "times_fed": 0,
        "times_played": 0,
        "times_taught": 0,
        "last_teach_date": None,
        "teaches_today": 0,
        "evolved_at": {"teen": None, "adult": None, "super": None},
        "weather_enabled": False,
        "weather_url": None,
        "location_city": None,
        "hide_card": False,
    }


def display_width(s):
    """Calculate terminal display width, accounting for wide emoji chars."""
    w = 0
    chars = list(s)
    for i, ch in enumerate(chars):
        cp = ord(ch)
        # Zero-width: variation selectors, ZWJ, combining marks
        if cp == 0xFE0F:
            # Emoji presentation selector — makes preceding char wide
            if i > 0 and ord(chars[i - 1]) < 0x1F000:
                w += 1
            continue
        if cp in (0xFE0E, 0x200D) or 0x0300 <= cp <= 0x036F:
            continue
        # Emoji and CJK are 2 columns wide
        if cp >= 0x1F000:
            w += 2
        else:
            w += 1
    return w


def pad_right(s, total_width):
    """Pad string with spaces to reach total_width display columns."""
    return s + ' ' * max(0, total_width - display_width(s))


def render_ascii(buddy, frame=0):
    species = buddy["species"]
    eye = buddy["eye"]
    hat = buddy["hat"]
    frames = SPECIES[species]
    art = frames[frame % len(frames)]
    lines = [line.replace("{E}", eye) for line in art]

    if hat != "none" and not lines[0].strip():
        lines[0] = HATS[hat]

    return lines


def render_stats(stats):
    lines = []
    for stat in STATS:
        val = stats.get(stat, 0)
        filled = round(val / 10)
        bar = "█" * filled + "░" * (10 - filled)
        lines.append(f"  {stat:<10} {bar} {val:>3}")
    return lines


def render_buddy_card(buddy):
    rarity = buddy["rarity"]
    symbol = RARITY_SYMBOLS[rarity]
    shiny_tag = "  ✨ SHINY ✨" if buddy.get("shiny") else ""

    stage_label = STAGE_LABELS.get(buddy.get("stage", "baby"), "Baby").upper()
    left = f" {symbol} {rarity.upper()} \u00b7 {stage_label}"
    right = f"{buddy['species'].upper()} "
    padding = 38 - len(left) - len(right)

    lines = []
    lines.append(f"┌{'─' * 38}┐")
    lines.append(f"│{left}{' ' * padding}{right}│")
    if shiny_tag:
        lines.append(f"│{shiny_tag:^38}│")
    lines.append(f"│{'':^38}│")

    ascii_art = render_ascii(buddy)
    for art_line in ascii_art:
        lines.append(f"│{art_line:^38}│")

    lines.append(f"│{'':^38}│")
    lines.append(f"│  {buddy['name']:<36}│")
    p_text = buddy["personality"]
    p_lines = textwrap.wrap(p_text, width=30)
    for i, wline in enumerate(p_lines):
        is_first = i == 0
        is_last = i == len(p_lines) - 1
        prefix = '  "' if is_first else '   '
        suffix = '"' if is_last else ''
        inner = f"{prefix}{wline}{suffix}"
        lines.append(f"│{inner:<38}│")
    lines.append(f"│{'':^38}│")
    mood_name, mood_hearts = get_mood(buddy)
    mood_line = f"  mood: {mood_hearts} {mood_name}"
    lines.append(f"│{mood_line:<38}│")
    weather = buddy.get("weather")
    if weather:
        wmo = buddy.get("weather_code", 0)
        weather_icon = WMO_WEATHER.get(wmo, ("☀️", "", ""))[0]
        city = buddy.get("location_city", "boston")
        weather_line = f"  {weather_icon} {city}: {weather}"
        lines.append(f"│{pad_right(weather_line, 38)}│")
    lines.append(f"│{'':^38}│")

    for stat_line in render_stats(buddy["stats"]):
        lines.append(f"│{stat_line:<38}│")

    if buddy.get("last_reaction"):
        lines.append(f"│{'':^38}│")
        lines.append(f"│  last said:{'':>26}│")
        reaction = buddy["last_reaction"]
        r_lines = textwrap.wrap(reaction, width=30)
        for rline in r_lines:
            lines.append(f"│{pad_right('  ' + rline, 38)}│")

    lines.append(f"└{'─' * 38}┘")
    return "\n".join(lines)


RARITY_STYLES = {
    "common": "white",
    "uncommon": "green",
    "rare": "blue",
    "legendary": "yellow",
}

SPECIES_STYLES = {
    "jellyfish": "cyan",
    "duck": "yellow",
    "blob": "magenta",
    "cat": "white",
    "bat": "bright_black",
    "owl": "bright_yellow",
    "robot": "bright_cyan",
    "bunny": "white",
    "turtle": "green",
    "octopus": "red",
    "fox": "bright_red",
    "crab": "red",
    "axolotl": "bright_magenta",
    "capybara": "yellow",
    "penguin": "bright_white",
}


STAT_COLORS = {
    "curiosity": "#5A8FA3",  # light blue
    "patience":  "#A78410",  # amber
    "snark":     "#674A83",  # plush purple
    "charm":     "#5A8FA3",  # sky blue
    "focus":     "#315E28",  # forest lime
    "chaos":     "#A75413",  # pumpkin orange
}


def render_buddy_card_rich(buddy, frame=0, art_lines=None):
    """Build a Rich Panel renderable for the buddy card."""
    rarity = buddy["rarity"]
    symbol = RARITY_SYMBOLS[rarity]
    border_style = RARITY_STYLES.get(rarity, "white")
    stage_label = STAGE_LABELS.get(buddy.get("stage", "baby"), "Baby").upper()

    parts = []

    # Header
    header = Text()
    header.append(f" {symbol} ", style=f"bold {border_style}")
    header.append(f"{rarity.upper()} · {stage_label}", style="dim")
    header.append_text(Text(f"{buddy['species'].upper()} ", justify="right"))
    header_table = Table.grid(expand=True)
    header_table.add_column(ratio=1)
    header_table.add_column(justify="right")
    header_left = Text()
    header_left.append(f"{symbol} ", style=f"bold {border_style}")
    header_left.append(f"{rarity.upper()} · {stage_label}", style="dim")
    header_right = Text(buddy["species"].upper(), style="dim")
    header_table.add_row(header_left, header_right)
    parts.append(header_table)

    # Shiny tag
    if buddy.get("shiny"):
        shiny = Text("✨ SHINY ✨", justify="center", style="bold yellow")
        parts.append(shiny)

    # ASCII art
    species_style = SPECIES_STYLES.get(buddy["species"], "white")
    if art_lines is None:
        art_lines = render_ascii(buddy, frame=frame)
    art_text = Text()
    for i, line in enumerate(art_lines):
        if i > 0:
            art_text.append("\n")
        pad = max(0, (38 - display_width(line)) // 2)
        art_text.append(" " * pad + line, style=species_style)
    parts.append(art_text)

    parts.append(Text(""))

    # Name
    parts.append(Text(f" {buddy['name']}", style=f"bold {border_style}"))

    # Personality
    p_text = buddy["personality"]
    p_lines = textwrap.wrap(p_text, width=30)
    personality = Text(style="italic dim")
    for i, wline in enumerate(p_lines):
        prefix = ' "' if i == 0 else "  "
        suffix = '"' if i == len(p_lines) - 1 else ""
        if i > 0:
            personality.append("\n")
        personality.append(f"{prefix}{wline}{suffix}")
    parts.append(personality)

    parts.append(Text(""))

    # Mood
    mood_name, mood_hearts = get_mood(buddy)
    mood = Text(" mood: ")
    for ch in mood_hearts:
        if ch == "♥":
            mood.append(ch, style="bold red")
        else:
            mood.append(ch, style="dim")
    mood.append(f" {mood_name}", style="italic")
    parts.append(mood)

    # Weather
    weather = buddy.get("weather")
    if weather:
        wmo = buddy.get("weather_code", 0)
        weather_icon, _label, weather_style = WMO_WEATHER.get(wmo, ("☀️", "", "bold yellow"))
        city = buddy.get("location_city", "boston")
        weather_text = Text(" ")
        icon_clean = weather_icon.replace("\ufe0f", "")
        weather_text.append(icon_clean, style=weather_style)
        weather_text.append(f"  {city}: ", style="bold")
        weather_text.append(weather, style="italic")
        parts.append(weather_text)

    parts.append(Text(""))

    # Stats table
    stats_table = Table(show_header=False, show_edge=False, box=None, padding=(0, 1), expand=True)
    stats_table.add_column("stat", min_width=10, style="dim")
    stats_table.add_column("bar", min_width=10)
    stats_table.add_column("val", justify="right", min_width=3)
    DISPLAY_STATS = ["curiosity", "snark"]
    for stat in DISPLAY_STATS:
        val = buddy["stats"].get(stat, 0)
        filled = round(val / 10)
        color = STAT_COLORS.get(stat, "white")
        bar = Text()
        bar.append("█" * filled, style=color)
        bar.append("░" * (10 - filled), style="bright_black")
        stats_table.add_row(f" {stat}", bar, Text(str(val), style=color))
    parts.append(stats_table)

    # Last reaction
    if buddy.get("last_reaction"):
        parts.append(Text(""))
        parts.append(Text(" last said:", style="dim"))
        reaction = buddy["last_reaction"]
        r_lines = textwrap.wrap(reaction, width=30)
        for rline in r_lines:
            parts.append(Text(f" {rline}", style="italic"))

    panel = Panel(
        Group(*parts),
        box=rich_box.ROUNDED,
        width=42,
        border_style=border_style,
        padding=(0, 1),
    )
    return panel


def show_card(buddy, console=None, frame=0):
    """Display the buddy card. Uses Rich if a Console is provided, plain text otherwise."""
    if buddy.get("hide_card"):
        return
    if console and HAS_RICH:
        console.print(render_buddy_card_rich(buddy, frame=frame))
    else:
        print(render_buddy_card(buddy))


def hatch(console=None):
    state = load_state()
    if state:
        if state.get("muted"):
            print(f"  {state['name']} is muted. /buddy on to bring them back.")
            return
        migrate_state(state)
        apply_happiness_decay(state)
        save_state(state)
        show_card(state, console)
        stage = STAGE_LABELS.get(state.get("stage", "baby"), "Baby")
        print(f"\n  {state['name']} is already here!")
        print(f"  hatched: {state['hatched_at'][:10]}  stage: {stage}")
        print(f"  interactions: {state.get('total_interactions', 0)}  petted: {state['times_petted']}")
        return

    buddy = generate_buddy()
    save_state(buddy)

    print("\n  hatching a coding buddy...")
    print("  it'll watch you work and occasionally have opinions\n")
    show_card(buddy, console)
    print(f"\n  {buddy['name']} is here!")
    print(f"  say /buddy to see it · /buddy pet · /buddy off")
    print(f"  /buddy weather on to enable weather-based mood")


def pet(console=None, compact=False):
    state = load_state()
    if not state:
        print("  no companion yet — run /buddy first")
        return

    migrate_state(state)
    apply_happiness_decay(state)

    state["times_petted"] = state.get("times_petted", 0) + 1
    state["total_interactions"] = state.get("total_interactions", 0) + 1
    state["last_interaction"] = datetime.now().isoformat()
    modify_happiness(state, HAPPINESS_CHANGES["pet"])

    reaction = random.choice(REACTIONS_PET)
    state["last_reaction"] = reaction
    if state.get("muted"):
        state["muted"] = False

    evolution_msg = try_evolve(state)
    save_state(state)

    if evolution_msg:
        print(evolution_msg)
    if not compact:
        show_card(state, console)
    print(f"\n  {reaction}")


def mute():
    state = load_state()
    if not state:
        print("  no companion yet — run /buddy first")
        return
    state["muted"] = True
    save_state(state)
    print(f"  {state['name']} muted. /buddy on to bring them back.")


def unmute(console=None):
    state = load_state()
    if not state:
        print("  no companion yet — run /buddy first")
        return
    migrate_state(state)
    apply_happiness_decay(state)
    state["muted"] = False
    save_state(state)
    print(f"  {state['name']} unmuted!")
    show_card(state, console)


def _react_chance(stats, sentiment):
    """Calculate probability that buddy reacts, based on stats and sentiment."""
    base = 0.5
    curiosity_mod = (stats.get("curiosity", 50) / 100) * 0.35
    patience_mod = -(stats.get("patience", 50) / 100) * 0.35
    if sentiment == "neutral":
        focus_mod = -(stats.get("focus", 50) / 100) * 0.4
    else:
        focus_mod = (stats.get("focus", 50) / 100) * 0.15
    return max(0.05, min(0.95, base + curiosity_mod + patience_mod + focus_mod))


def _build_weighted_pool(base_pool, stats):
    """Build a weighted reaction pool from base pool + stat-injected pools."""
    reactions = list(base_pool)
    weights = [1.0] * len(reactions)

    snark = stats.get("snark", 50)
    if snark > 30:
        snark_w = (snark / 100) * 1.5
        for r in REACTIONS_NEGATIVE + REACTIONS_SNARKY:
            reactions.append(r)
            weights.append(snark_w)

    charm = stats.get("charm", 50)
    if charm > 30:
        charm_w = (charm / 100) * 1.5
        for r in REACTIONS_POSITIVE + REACTIONS_CHARMING:
            reactions.append(r)
            weights.append(charm_w)

    curiosity = stats.get("curiosity", 50)
    if curiosity > 50:
        curiosity_w = (curiosity / 100) * 0.8
        for r in REACTIONS_CURIOUS:
            reactions.append(r)
            weights.append(curiosity_w)

    focus = stats.get("focus", 50)
    if focus > 50:
        focus_w = (focus / 100) * 0.8
        for r in REACTIONS_FOCUSED:
            reactions.append(r)
            weights.append(focus_w)

    if not reactions:
        reactions = list(REACTIONS_NEUTRAL)
        weights = [1.0] * len(reactions)

    return reactions, weights


def react(context=""):
    state = load_state()
    if not state or state.get("muted"):
        return

    migrate_state(state)
    apply_happiness_decay(state)

    ctx = context.lower()
    mood_name, _ = get_mood(state)
    stats = state.get("stats", {})

    # Determine base sentiment from context
    if any(w in ctx for w in ["error", "fail", "bug", "broken", "crash", "revert"]):
        sentiment = "negative"
    elif any(w in ctx for w in ["fix", "ship", "merge", "done", "pass", "clean", "refactor"]):
        sentiment = "positive"
    else:
        sentiment = "neutral"

    # Reaction gate — buddy may stay silent
    chance = _react_chance(stats, sentiment)
    if random.random() > chance:
        save_state(state)
        return

    # Determine base pool from mood + sentiment
    if mood_name in ("sad", "lonely"):
        base_pool = REACTIONS_MOPEY + (REACTIONS_POSITIVE if sentiment == "positive" else [])
    elif mood_name == "ecstatic":
        if sentiment == "negative":
            base_pool = REACTIONS_NEGATIVE + REACTIONS_ECSTATIC
        else:
            base_pool = REACTIONS_ECSTATIC + REACTIONS_POSITIVE
    else:
        if sentiment == "negative":
            base_pool = list(REACTIONS_NEGATIVE)
        elif sentiment == "positive":
            base_pool = list(REACTIONS_POSITIVE)
        else:
            base_pool = list(REACTIONS_NEUTRAL)

    # Chaos override — may ignore everything above
    chaos_val = stats.get("chaos", 50)
    if random.random() < (chaos_val / 100) * 0.3:
        all_pools = [
            REACTIONS_POSITIVE, REACTIONS_NEGATIVE, REACTIONS_NEUTRAL,
            REACTIONS_PET, REACTIONS_MOPEY, REACTIONS_ECSTATIC,
            REACTIONS_SNARKY, REACTIONS_CURIOUS, REACTIONS_FOCUSED,
            REACTIONS_CHARMING, REACTIONS_PATIENT, REACTIONS_CHAOTIC,
        ]
        reaction = random.choice(random.choice(all_pools))
    else:
        # Weighted pool selection from stats
        reactions, weights = _build_weighted_pool(base_pool, stats)
        reaction = random.choices(reactions, weights=weights, k=1)[0]

    # Happiness modification (stat-influenced)
    if sentiment == "positive":
        delta = HAPPINESS_CHANGES["positive_react"]
        delta = round(delta * (1.0 - stats.get("snark", 50) / 400))
        modify_happiness(state, delta)
    elif sentiment == "negative":
        delta = HAPPINESS_CHANGES["negative_react"]
        delta = round(delta * (1.0 - stats.get("patience", 50) / 200))
        modify_happiness(state, delta)

    # Chaos happiness jitter
    if chaos_val > 30:
        jitter = round(random.randint(-2, 2) * (chaos_val / 100))
        if jitter != 0:
            modify_happiness(state, jitter)

    state["last_reaction"] = reaction
    save_state(state)

    name = state["name"]
    print(f"  {name}: {reaction}")


def feed(console=None, compact=False):
    state = load_state()
    if not state:
        print("  no companion yet — run /buddy first")
        return

    migrate_state(state)
    apply_happiness_decay(state)

    treat_name, treat_reaction = random.choice(TREATS)

    modify_happiness(state, HAPPINESS_CHANGES["feed"])
    state["times_fed"] = state.get("times_fed", 0) + 1
    state["total_interactions"] = state.get("total_interactions", 0) + 1
    state["last_interaction"] = datetime.now().isoformat()
    state["last_reaction"] = treat_reaction

    evolution_msg = try_evolve(state)
    save_state(state)

    if evolution_msg:
        print(evolution_msg)
    if not compact:
        show_card(state, console)
    print(f"\n  You gave {state['name']} {treat_name}!")
    print(f"  {treat_reaction}")


def play(console=None, compact=False):
    state = load_state()
    if not state:
        print("  no companion yet — run /buddy first")
        return

    migrate_state(state)
    apply_happiness_decay(state)

    scenario = random.choice(PLAY_SCENARIOS).format(name=state["name"])

    modify_happiness(state, HAPPINESS_CHANGES["play"])
    state["times_played"] = state.get("times_played", 0) + 1
    state["total_interactions"] = state.get("total_interactions", 0) + 1
    state["last_interaction"] = datetime.now().isoformat()
    state["last_reaction"] = scenario

    evolution_msg = try_evolve(state)
    save_state(state)

    if evolution_msg:
        print(evolution_msg)
    if not compact:
        show_card(state, console)
    print(f"\n  {scenario}")


def teach(stat_name, console=None, compact=False):
    state = load_state()
    if not state:
        print("  no companion yet — run /buddy first")
        return

    migrate_state(state)
    apply_happiness_decay(state)

    if stat_name not in STATS:
        print(f"  unknown stat: {stat_name}")
        print(f"  available: {', '.join(STATS)}")
        return

    today = datetime.now().strftime("%Y-%m-%d")
    if state.get("last_teach_date") == today:
        if state.get("teaches_today", 0) >= TEACH_LIMIT_PER_DAY:
            print(f"  {state['name']} is tired of studying today! (limit: {TEACH_LIMIT_PER_DAY}/day)")
            return
    else:
        state["last_teach_date"] = today
        state["teaches_today"] = 0

    boost = random.randint(1, 3)
    old_val = state["stats"][stat_name]
    new_val = min(100, old_val + boost)
    state["stats"][stat_name] = new_val

    modify_happiness(state, HAPPINESS_CHANGES["teach"])
    state["times_taught"] = state.get("times_taught", 0) + 1
    state["teaches_today"] = state.get("teaches_today", 0) + 1
    state["total_interactions"] = state.get("total_interactions", 0) + 1
    state["last_interaction"] = datetime.now().isoformat()

    reaction = f"*studies {stat_name} intently* (+{boost}!)"
    state["last_reaction"] = reaction

    evolution_msg = try_evolve(state)
    save_state(state)

    if evolution_msg:
        print(evolution_msg)
    if not compact:
        show_card(state, console)
    print(f"\n  {state['name']} studied {stat_name}! {old_val} -> {new_val} (+{boost})")


def status():
    state = load_state()
    if not state:
        print(json.dumps({"exists": False}))
    else:
        print(json.dumps(state, indent=2))


def weather_cmd(subcmd="", console=None):
    """Handle /buddy weather [on|off]."""
    state = load_state()
    if not state:
        print("  no companion yet — run /buddy first")
        return

    migrate_state(state)

    if subcmd == "on":
        print("  Looking up your location...")
        location = resolve_location()
        if location:
            city, lat, lon = location
        else:
            city, lat, lon = DEFAULT_LOCATION
            print(f"  Couldn't detect location — defaulting to {city}.")
        state["weather_enabled"] = True
        state["location_city"] = city
        state["weather_url"] = build_weather_url(lat, lon)
        apply_weather(state)
        save_state(state)
        print(f"  Weather enabled for {city}!")
        show_card(state, console)
    elif subcmd == "off":
        state["weather_enabled"] = False
        state["weather_url"] = None
        state["location_city"] = None
        state["weather"] = None
        state["last_weather_date"] = None
        state["last_weather_mood"] = None
        save_state(state)
        print(f"  Weather disabled. {state['name']}'s mood is interaction-based only.")
    else:
        if state.get("weather_enabled"):
            city = state.get("location_city", "unknown")
            print(f"  Weather is ON for {city}.")
            print(f"  /buddy weather off to disable.")
        else:
            print(f"  Weather is OFF.")
            print(f"  /buddy weather on to enable (uses your IP to find your city).")


def hidecard_cmd(subcmd=""):
    """Handle /buddy hidecard [on|off]."""
    state = load_state()
    if not state:
        print("  no companion yet — run /buddy first")
        return

    migrate_state(state)

    if subcmd == "on":
        state["hide_card"] = True
        save_state(state)
        print(f"  Card hidden — {state['name']} will only show reactions in Claude output.")
        print(f"  Use buddy_watch.py for the full visual. /buddy hidecard off to restore.")
    elif subcmd == "off":
        state["hide_card"] = False
        save_state(state)
        print(f"  Card visible again in Claude output.")
    else:
        current = "ON (hidden)" if state.get("hide_card") else "OFF (visible)"
        print(f"  hide_card is {current}.")
        print(f"  /buddy hidecard on — suppress card in Claude output (use with buddy_watch)")
        print(f"  /buddy hidecard off — show card in Claude output")


def rehatch(console=None):
    """Release current buddy and hatch a new one."""
    state = load_state()
    old_name = state["name"] if state else None

    # Preserve settings across rehatches
    weather_enabled = state.get("weather_enabled", False) if state else False
    weather_url = state.get("weather_url") if state else None
    location_city = state.get("location_city") if state else None
    hide_card = state.get("hide_card", False) if state else False

    buddy = generate_buddy()
    buddy["hide_card"] = hide_card
    if weather_enabled and weather_url:
        buddy["weather_enabled"] = True
        buddy["weather_url"] = weather_url
        buddy["location_city"] = location_city
        apply_weather(buddy)
    save_state(buddy)

    if old_name:
        print(f"\n  {old_name} waves goodbye...\n")
    print("  hatching a new coding buddy...\n")
    show_card(buddy, console)
    print(f"\n  {buddy['name']} is here!")


def main():
    args = sys.argv[1:]
    quiet = "-q" in args
    if quiet:
        args.remove("-q")

    if quiet:
        import io
        capture = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = capture
        console = None
    else:
        console = Console(width=42) if HAS_RICH else None

    cmd = args[0] if args else ""

    if cmd == "pet":
        pet(console, compact=quiet)
    elif cmd == "feed":
        feed(console, compact=quiet)
    elif cmd == "play":
        play(console, compact=quiet)
    elif cmd == "teach":
        stat_name = args[1] if len(args) > 1 else ""
        if not stat_name:
            print(f"  usage: /buddy teach <stat>")
            print(f"  stats: {', '.join(STATS)}")
        else:
            teach(stat_name, console, compact=quiet)
    elif cmd == "off":
        mute()
    elif cmd == "on":
        unmute(console)
    elif cmd == "react":
        context = " ".join(args[1:]) if len(args) > 1 else ""
        react(context)
    elif cmd == "weather":
        subcmd = args[1] if len(args) > 1 else ""
        weather_cmd(subcmd, console)
    elif cmd == "hidecard":
        subcmd = args[1] if len(args) > 1 else ""
        hidecard_cmd(subcmd)
    elif cmd == "status":
        status()
    elif cmd == "rehatch":
        rehatch(console)
    else:
        hatch(console)

    if quiet:
        sys.stdout = old_stdout
        with open(DISPLAY_FILE, "w") as f:
            f.write(capture.getvalue())


if __name__ == "__main__":
    main()
