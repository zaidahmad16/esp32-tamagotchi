# BoardPet pet logic. Pure Python: runs on MicroPython (the board) and
# desktop CPython (tests, mock server). No hardware imports here.

HOUR = 3600
DAY = 86400

# Seconds for a stat to drain from 100 to 0 while awake.
HUNGER_DRAIN = 8 * HOUR
HAPPY_DRAIN = 10 * HOUR
ENERGY_DRAIN = 14 * HOUR
CLEAN_DRAIN = 24 * HOUR
ENERGY_REFILL = 6 * HOUR        # asleep: 0 -> 100
SLEEP_FACTOR = 0.25             # asleep: other stats drain this much slower
POOP_EVERY = 3 * HOUR           # awake time between poops
POOP_DIRT = 20                  # cleanliness lost per poop
SICK_AFTER_ZERO = HOUR          # any stat at 0 this long -> sick
SICK_POOPS = 3
MAX_POOPS = 4
MAX_CATCHUP = 7 * DAY
STEP = 60                       # simulation chunk, seconds

STAGES = (("egg", 300), ("hatchling", DAY), ("young", 3 * DAY), ("adult", None))


def new_state(name="Patrick"):
    return {
        "v": 1, "name": name, "age_s": 0.0,
        "hunger": 80.0, "happy": 80.0, "energy": 100.0, "clean": 100.0,
        "poops": 0, "poop_acc": 0.0, "zero_s": 0.0,
        "sick": False, "asleep": False,
        "last_epoch": 0, "unsynced_s": 0.0,
        "event": "", "event_seq": 0,
    }


def upgrade(s, name="Patrick"):
    """Fill in any keys missing from an older or partial save."""
    base = new_state(s.get("name", name))
    for k in base:
        if k not in s:
            s[k] = base[k]
    return s


def stage(s):
    for name, until in STAGES:
        if until is None or s["age_s"] < until:
            return name
    return "adult"


def _clamp(x):
    return 0.0 if x < 0 else 100.0 if x > 100 else x


def _step(s, dt):
    s["age_s"] += dt
    if stage(s) == "egg":
        return
    slow = SLEEP_FACTOR if s["asleep"] else 1.0
    sick = 2.0 if s["sick"] else 1.0
    s["hunger"] = _clamp(s["hunger"] - 100.0 * dt / HUNGER_DRAIN * slow)
    s["happy"] = _clamp(s["happy"] - 100.0 * dt / HAPPY_DRAIN * slow * sick)
    s["clean"] = _clamp(s["clean"] - 100.0 * dt / CLEAN_DRAIN * slow)
    if s["asleep"]:
        s["energy"] = _clamp(s["energy"] + 100.0 * dt / ENERGY_REFILL)
        if s["energy"] >= 100:
            s["asleep"] = False
            _event(s, "woke")
    else:
        s["energy"] = _clamp(s["energy"] - 100.0 * dt / ENERGY_DRAIN * (1.5 if s["sick"] else 1.0))
        if s["energy"] <= 0:
            s["asleep"] = True
            _event(s, "passed_out")
    s["poop_acc"] += dt * slow
    while s["poop_acc"] >= POOP_EVERY:
        s["poop_acc"] -= POOP_EVERY
        if s["poops"] < MAX_POOPS:
            s["poops"] += 1
            s["clean"] = _clamp(s["clean"] - POOP_DIRT)
    if min(s["hunger"], s["happy"], s["energy"], s["clean"]) <= 0:
        s["zero_s"] += dt
    else:
        s["zero_s"] = 0.0
    if not s["sick"] and (s["zero_s"] >= SICK_AFTER_ZERO or s["poops"] >= SICK_POOPS):
        s["sick"] = True
        _event(s, "got_sick")


def apply_elapsed(s, seconds):
    """Advance the pet by `seconds` (offline catch-up is capped)."""
    if seconds <= 0:
        return
    if seconds > MAX_CATCHUP:
        seconds = MAX_CATCHUP
    while seconds > 0:
        dt = STEP if seconds > STEP else seconds
        _step(s, dt)
        seconds -= dt


def _event(s, name):
    s["event"] = name
    s["event_seq"] = s.get("event_seq", 0) + 1


def act(s, action, arg=0):
    """Perform a care action. Returns (ok, message)."""
    n = s["name"]
    if stage(s) == "egg":
        if action == "pat":
            _event(s, "wobble")
            return True, "The egg wobbles."
        return False, "It's still an egg. Give it a few minutes."
    if s["asleep"] and action not in ("wake", "clean", "medicine", "sleep"):
        return False, n + " is asleep."
    if action == "feed":
        if s["hunger"] >= 95:
            return False, n + " is full."
        s["hunger"] = _clamp(s["hunger"] + 35)
        s["energy"] = _clamp(s["energy"] + 5)
        s["poop_acc"] += POOP_EVERY / 6
        _event(s, "eat")
        return True, n + " ate a meal."
    if action == "snack":
        if s["hunger"] >= 98:
            return False, n + " is too full for a snack."
        s["hunger"] = _clamp(s["hunger"] + 10)
        s["happy"] = _clamp(s["happy"] + 15)
        s["poop_acc"] += POOP_EVERY / 12
        _event(s, "snack")
        return True, n + " loved the snack."
    if action == "play":
        if s["energy"] < 10:
            return False, n + " is too tired to play."
        won = int(arg) if 0 <= int(arg) <= 5 else 0
        s["happy"] = _clamp(s["happy"] + 5 + 6 * won)
        s["energy"] = _clamp(s["energy"] - 8)
        s["hunger"] = _clamp(s["hunger"] - 5)
        _event(s, "play")
        return True, n + " had fun (" + str(won) + "/5)."
    if action == "pat":
        s["happy"] = _clamp(s["happy"] + 5)
        _event(s, "pat")
        return True, n + " liked that."
    if action == "sleep":
        if s["asleep"]:
            return False, n + " is already asleep."
        s["asleep"] = True
        _event(s, "sleep")
        return True, "Lights out."
    if action == "wake":
        if not s["asleep"]:
            return False, n + " is already awake."
        s["asleep"] = False
        if s["energy"] < 30:
            s["happy"] = _clamp(s["happy"] - 5)
        _event(s, "woke")
        return True, n + " is up."
    if action == "clean":
        if s["poops"] == 0 and s["clean"] >= 95:
            return False, "Already clean."
        s["poops"] = 0
        s["clean"] = 100.0
        _event(s, "clean")
        return True, "All clean."
    if action == "medicine":
        if not s["sick"]:
            return False, n + " isn't sick."
        s["sick"] = False
        s["zero_s"] = 0.0
        s["happy"] = _clamp(s["happy"] - 5)
        _event(s, "medicine")
        return True, n + " feels better."
    return False, "Unknown action."


def mood(s):
    if stage(s) == "egg":
        return "egg"
    if s["sick"]:
        return "sick"
    if s["asleep"]:
        return "sleep"
    if min(s["hunger"], s["happy"]) < 25 or s["poops"] >= 2:
        return "sad"
    if s["happy"] >= 70:
        return "happy"
    return "ok"


def needs(s):
    out = []
    if stage(s) == "egg":
        return out
    if s["sick"]:
        out.append("medicine")
    if s["hunger"] < 30:
        out.append("food")
    if s["happy"] < 30:
        out.append("play")
    if s["poops"] > 0 or s["clean"] < 30:
        out.append("clean")
    if s["energy"] < 20 and not s["asleep"]:
        out.append("sleep")
    return out


def public(s):
    """State as sent to the page."""
    d = {}
    for k in ("name", "age_s", "poops", "sick", "asleep", "event", "event_seq"):
        d[k] = s[k]
    for k in ("hunger", "happy", "energy", "clean"):
        d[k] = int(s[k] + 0.5)
    d["stage"] = stage(s)
    d["mood"] = mood(s)
    d["needs"] = needs(s)
    if d["stage"] == "egg":
        d["hatch_in"] = int(STAGES[0][1] - s["age_s"])
    return d
