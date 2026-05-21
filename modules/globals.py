# Cinderella PVC Bot - globals.py
import os
import json
from vars import CREDIT

# ── Credit string (loaded from settings or default) ─────────────────────────
CR = f"{CREDIT}"

# ── Global settings (persisted in settings_store.json) ───────────────────────
_SETTINGS_STORE = "settings_store.json"

def _load_settings() -> dict:
    if os.path.exists(_SETTINGS_STORE):
        try:
            with open(_SETTINGS_STORE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def _save_settings(data: dict):
    try:
        with open(_SETTINGS_STORE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[globals] settings save error: {e}")

def get_setting(key: str, default=None):
    return _load_settings().get(key, default)

def set_setting(key: str, value):
    data = _load_settings()
    data[key] = value
    _save_settings(data)

# ── Load persisted batch_name and credit_name on startup ─────────────────────
batch_name  = get_setting("batch_name",  "💥Contact: @CinderellaContactBot")
credit_name = get_setting("credit_name", CR)
