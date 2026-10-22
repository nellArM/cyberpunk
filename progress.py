"""Credits, cyberware upgrades (bought at CHROME clinics), collected data shards and mission records.

`stats()` turns the upgrade levels into the numbers the player controller uses; level 0 is
the game as it was before upgrades existed.
"""
import savegame
from i18n import tr

PRICES = (300, 800, 2000)                       # Lv1, Lv2, Lv3
# key: (name, what it does, per-level values of each stat)
UPGRADES = {
    "wingsuit": ("翼裝", "最高速、滑翔距離、最低展開高度",
                 {"glide_max": (65.0, 73.0, 81.0, 90.0), "glide_sink": (4.0, 3.5, 3.0, 2.5),
                  "glide_min_h": (6.0, 5.0, 4.0, 3.0)}),
    "grapple": ("鉤索", "射程、收線速度",
                {"grapple_range": (150.0, 190.0, 230.0, 280.0), "grapple_speed": (45.0, 55.0, 65.0, 75.0)}),
    "run": ("跑速", "奔跑速度",
            {"run_speed": (11.0, 12.5, 14.0, 16.0)}),
    "boots": ("火箭靴", "噴射次數、冷卻、衝刺與二段跳力道",
              {"boost_charges": (1, 2, 2, 3), "boost_cooldown": (4.0, 3.2, 2.4, 1.6),
               "dash_speed": (22.0, 25.0, 28.0, 32.0), "jump2_speed": (9.0, 10.0, 11.0, 12.0)}),
}
ORDER = ("wingsuit", "grapple", "run", "boots")
MAX_LEVEL = 3
STAT_LABELS = {"glide_max": ("最高速", "m/s"), "glide_sink": ("下沉", "m/s"), "glide_min_h": ("展開高度", "m"),
               "grapple_range": ("射程", "m"), "grapple_speed": ("收線", "m/s"), "run_speed": ("奔跑", "m/s"),
               "boost_charges": ("噴射", "次"), "boost_cooldown": ("冷卻", "s"), "dash_speed": ("衝刺", "m/s"),
               "jump2_speed": ("二段跳", "m/s")}


def describe(key, lv):
    """e.g. "射程 150→190 m · 收線 45→55 m/s" (current -> next level), or the current values at max."""
    parts = []
    for stat, values in UPGRADES[key][2].items():
        label, unit = STAT_LABELS[stat]
        label, unit = tr(label), tr(unit)
        unit = f" {unit}" if unit else ""
        now = values[lv]
        if lv < MAX_LEVEL:
            parts.append(f"{label} {now:g}→{values[lv + 1]:g}{unit}")
        else:
            parts.append(f"{label} {now:g}{unit}")
    return " · ".join(parts)


def base_stats():
    return stats_for({k: 0 for k in UPGRADES})


def stats_for(levels):
    out = {}
    for key, (_, _, table) in UPGRADES.items():
        lv = max(0, min(MAX_LEVEL, int(levels.get(key, 0))))
        for stat, values in table.items():
            out[stat] = values[lv]
    return out


class Progress:
    def __init__(self, path):
        """path: callable returning the save file path (read at save time)."""
        self.path = path
        self.reset()

    def reset(self):
        self.credits = 0
        self.levels = {k: 0 for k in UPGRADES}
        self.shards = set()
        self.missions = {}                      # id: {"done": n, "best": seconds or None}

    def load(self, data):
        try:
            self.credits = max(0, int(data.get("credits", 0)))
        except (TypeError, ValueError):
            self.credits = 0
        up = data.get("upgrades", {})
        if isinstance(up, dict):
            for k in UPGRADES:
                try:
                    self.levels[k] = max(0, min(MAX_LEVEL, int(up.get(k, 0))))
                except (TypeError, ValueError):
                    pass
        sh = data.get("shards", [])
        self.shards = {int(i) for i in sh if isinstance(i, int)} if isinstance(sh, list) else set()
        ms = data.get("missions", {})
        self.missions = {k: v for k, v in ms.items() if isinstance(v, dict)} if isinstance(ms, dict) else {}

    def fields(self):
        return {"credits": self.credits, "upgrades": dict(self.levels), "shards": sorted(self.shards),
                "missions": self.missions}

    def save(self):
        savegame.merge(self.path(), **self.fields())

    def stats(self):
        return stats_for(self.levels)

    # ---------------------------------------------------------------- spending / earning
    def price(self, key):
        lv = self.levels[key]
        return PRICES[lv] if lv < MAX_LEVEL else None

    def buy(self, key):
        """(ok, message)"""
        name = UPGRADES[key][0]
        price = self.price(key)
        if price is None:
            return False, tr("{name} 已經升到最高級", name=name)
        if self.credits < price:
            return False, tr("信用點不足：{name} Lv{lv} 要 ${price:,}（目前 ${credits:,}）", name=name,
                             lv=self.levels[key] + 1, price=price, credits=self.credits)
        self.credits -= price
        self.levels[key] += 1
        self.save()
        return True, tr("{name} 升級到 Lv{lv}！（-${price:,}）", name=name, lv=self.levels[key], price=price)

    def earn(self, amount):
        self.credits += int(amount)

    def record(self, mission_id, seconds):
        """Note a completed mission; returns whether it is a new best time."""
        rec = self.missions.setdefault(mission_id, {"done": 0, "best": None})
        rec["done"] = int(rec.get("done", 0)) + 1
        best = rec.get("best")
        new = seconds is not None and (best is None or seconds < best)
        if new:
            rec["best"] = round(float(seconds), 2)
        return new

    def best(self, mission_id):
        return self.missions.get(mission_id, {}).get("best")

    def done(self, mission_id):
        return int(self.missions.get(mission_id, {}).get("done", 0))
