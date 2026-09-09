import os
from environs import Env

env = Env()
env.read_env(".env", recurse=False)

BOT_TOKEN = os.getenv("BOT_TOKEN", env.str("BOT_TOKEN", ""))
API_ID = int(os.getenv("API_ID", env.int("API_ID", 2040)))
API_HASH = os.getenv("API_HASH", env.str("API_HASH", "b18441a1ff607e10a989891a5462e627"))

# AI Settings - совместимо с OpenRouter
AI_BASE_URL = os.getenv("AI_BASE_URL", env.str("AI_BASE_URL", "https://openrouter.ai/api/v1"))
AI_KEY = os.getenv("AI_KEY", env.str("AI_KEY", ""))
AI_MODEL = os.getenv("AI_MODEL", env.str("AI_MODEL", "google/gemini-2.0-flash-001"))

# Owner
OWNER_ID = int(os.getenv("OWNER_ID", env.int("OWNER_ID", 0)))
OWNER_NAME = os.getenv("OWNER_NAME", env.str("OWNER_NAME", "Владелец"))

# Database
DB_PATH = os.getenv("DB_PATH", env.str("DB_PATH", "bot.db"))

# Behavior
MAX_PROMPT_LEN = 4000
MAX_TOKENS = 2048
