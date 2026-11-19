"""Desktop tests for pet.py. Run: python3 tests/test_pet.py"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import pet  # noqa: E402

H, D = pet.HOUR, pet.DAY


def hatched():
    s = pet.new_state()
    pet.apply_elapsed(s, 300)
    assert pet.stage(s) == "hatchling"
    return s


def test_egg_is_frozen_then_hatches():
    s = pet.new_state()
    pet.apply_elapsed(s, 299)
    assert pet.stage(s) == "egg" and s["hunger"] == 80
    ok, _ = pet.act(s, "feed")
    assert not ok
    pet.apply_elapsed(s, 1)
    assert pet.stage(s) == "hatchling"


def test_hunger_drains_in_about_8h():
    s = hatched()
    s["hunger"] = 100
    pet.apply_elapsed(s, 4 * H)
    assert 45 <= s["hunger"] <= 55, s["hunger"]


def test_sleep_slows_drain_and_refills_energy():
    s = hatched()
    s.update(hunger=100, energy=10)
    pet.act(s, "sleep")
    pet.apply_elapsed(s, 4 * H)
    assert s["hunger"] > 85, s["hunger"]
    assert s["energy"] > 70, s["energy"]


def test_wakes_itself_when_rested():
    s = hatched()
    s["energy"] = 50
    pet.act(s, "sleep")
    pet.apply_elapsed(s, 4 * H)
    assert not s["asleep"]


def test_day_offline_means_hungry_and_dirty():
    s = hatched()
    pet.apply_elapsed(s, D)
    assert s["hunger"] < 30
    assert s["poops"] >= 2
    assert "food" in pet.needs(s) and "clean" in pet.needs(s)


def test_three_poops_make_it_sick_and_medicine_cures():
    s = hatched()
    s["poops"] = 2
    s["poop_acc"] = pet.POOP_EVERY - 60
    pet.apply_elapsed(s, 120)
    assert s["poops"] == 3 and s["sick"]
    assert pet.mood(s) == "sick"
    ok, _ = pet.act(s, "medicine")
    assert ok and not s["sick"]
    ok, _ = pet.act(s, "medicine")
    assert not ok


def test_zero_stat_for_an_hour_makes_sick():
    s = hatched()
    s.update(hunger=0, poops=0)
    s["poop_acc"] = -10 * H  # keep poops out of it
    pet.apply_elapsed(s, 59 * 60)
    assert not s["sick"]
    pet.apply_elapsed(s, 2 * 60)
    assert s["sick"]


def test_never_dies_after_a_week_of_neglect():
    s = hatched()
    pet.apply_elapsed(s, 30 * D)  # capped at 7 days
    assert s["age_s"] <= 300 + pet.MAX_CATCHUP + 1
    assert s["sick"]
    for k in ("hunger", "happy", "energy", "clean"):
        assert 0 <= s[k] <= 100
    # still fully playable afterwards
    pet.act(s, "medicine")
    pet.act(s, "clean")
    if s["asleep"]:
        pet.act(s, "wake")
    ok, _ = pet.act(s, "feed")
    assert ok and not s["sick"] and s["poops"] == 0


def test_growth_stages():
    s = pet.new_state()
    seen = []
    for _ in range(6):
        pet.apply_elapsed(s, D)
        s.update(hunger=100, happy=100, energy=100, clean=100, poops=0, sick=False)
        seen.append(pet.stage(s))
    assert seen[0] == "young" and seen[-1] == "adult", seen
    assert "hatchling" == pet.stage(dict(pet.new_state(), age_s=D - 1))


def test_actions_and_refusals():
    s = hatched()
    s["hunger"] = 96
    assert not pet.act(s, "feed")[0]
    s["hunger"] = 40
    assert pet.act(s, "feed")[0] and s["hunger"] == 75
    s["energy"] = 5
    assert not pet.act(s, "play", 3)[0]
    s["energy"] = 50
    h = s["happy"]
    assert pet.act(s, "play", 5)[0] and s["happy"] == min(100, h + 35)
    pet.act(s, "sleep")
    assert not pet.act(s, "feed")[0]
    assert pet.act(s, "wake")[0]
    assert not pet.act(s, "bogus")[0]


def test_public_and_upgrade():
    s = pet.upgrade({"name": "Rex", "hunger": 50})
    d = pet.public(s)
    assert d["name"] == "Rex" and d["stage"] == "egg" and "hatch_in" in d
    assert isinstance(d["hunger"], int)


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print("ok", t.__name__)
    print(len(tests), "passed")
