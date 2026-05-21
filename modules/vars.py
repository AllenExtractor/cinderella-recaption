# Cinderella PVC Bot - vars.py
import os
from os import environ

API_ID   = int(environ.get("API_ID", "38498066"))
API_HASH = environ.get("API_HASH", "c9696114751feacdeb1b4487f5839a1a")
BOT_TOKEN = environ.get("BOT_TOKEN", "")

OWNER  = int(environ.get("OWNER", "8446475678"))
CREDIT = environ.get("CREDIT", "💥 @CinderellaContactBot")

TOTAL_USER  = os.environ.get('TOTAL_USERS', '8446475678').split(',')
TOTAL_USERS = [int(u) for u in TOTAL_USER if u.strip()]

AUTH_USER  = os.environ.get('AUTH_USERS', '8446475678').split(',')
AUTH_USERS = [int(u) for u in AUTH_USER if u.strip()]
if OWNER not in AUTH_USERS:
    AUTH_USERS.append(OWNER)
