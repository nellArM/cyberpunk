"""The save file (savegame.json): one JSON object whose keys several systems share.

Every writer merges its own keys into what is on disk (read, update, atomic replace), so the
map's discovered places, the player's progress and the world state never overwrite each other.
The path is passed in on every call (citymap.SAVE_PATH), so test scripts can redirect it.
"""
import json
import os
import shutil

VERSION = 2


def load(path):
    """The saved object, or {} when there is none / it is unreadable."""
    try:
        with open(path, encoding="utf8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def merge(path, **fields):
    """Write fields into the save, keeping every other key. Returns False if it could not be written."""
    data = load(path)
    data.update(fields)
    data["version"] = VERSION
    tmp = path + ".tmp"
    try:
        with open(tmp, "w", encoding="utf8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
        os.replace(tmp, path)
        return True
    except OSError:
        return False


def exists(path):
    return bool(load(path))


def backup_path(path):
    root, ext = os.path.splitext(path)
    return root + ".bak" + ext


def reset(path):
    """Start over: keep the old save as savegame.bak.json (only the latest one), then remove it."""
    try:
        if os.path.exists(path):
            shutil.copyfile(path, backup_path(path))
            os.remove(path)
        return True
    except OSError:
        return False
