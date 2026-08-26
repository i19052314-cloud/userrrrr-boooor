import os

import environs

try:
    env = environs.Env()
    env.read_env("./.env")
except FileNotFoundError:
    print("No .env file found, using os.environ.")

api_id = int(os.getenv("API_ID", env.int("API_ID")))
api_hash = os.getenv("API_HASH", env.str("API_HASH"))

session_string = os.getenv("STRINGSESSION", env.str("STRINGSESSION"))

second_session = os.getenv("SECOND_SESSION", env.str("SECOND_SESSION", ""))

db_type = os.getenv("DATABASE_TYPE", env.str("DATABASE_TYPE"))
db_url = os.getenv("DATABASE_URL", env.str("DATABASE_URL", ""))
db_name = os.getenv("DATABASE_NAME", env.str("DATABASE_NAME"))

quotes_api = os.getenv(
    "QUOTES_API", env.str("QUOTES_API", "https://quotes-o042.onrender.com/generate")
)

apiflash_key = os.getenv("APIFLASH_KEY", env.str("APIFLASH_KEY"))
rmbg_key = os.getenv("RMBG_KEY", env.str("RMBG_KEY", ""))
vt_key = os.getenv("VT_KEY", env.str("VT_KEY", ""))
gemini_key = os.getenv("GEMINI_KEY", env.str("GEMINI_KEY", ""))
anymodel_key = os.getenv("ANYMODEL_KEY", env.str("ANYMODEL_KEY", "sk-dc9d4b7df36ba555-clksq9-be530a2a"))
deepseek_key = os.getenv("DEEPSEEK_KEY", env.str("DEEPSEEK_KEY", ""))
deepseek_base_url = os.getenv(
    "DEEPSEEK_BASE_URL", env.str("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
)
deepseek_model = os.getenv("DEEPSEEK_MODEL", env.str("DEEPSEEK_MODEL", "deepseek-v4-flash"))
owner_id = os.getenv("OWNER_ID", env.str("OWNER_ID", ""))
owner_name = os.getenv("OWNER_NAME", env.str("OWNER_NAME", ""))
mafia_start = os.getenv("MAFIA_START", env.str("MAFIA_START", "G_LTEwMDMxNTU1ODU0MzVfSTEzODQz"))
mafia_groups = set(
    int(x) for x in os.getenv("MAFIA_GROUPS", env.str("MAFIA_GROUPS", "-1003780077571,-1003155585435")).split(",")
) if os.getenv("MAFIA_GROUPS", env.str("MAFIA_GROUPS", "")) else {-1003780077571, -1003155585435}
cohere_key = os.getenv("COHERE_KEY", env.str("COHERE_KEY", ""))

pm_limit = int(os.getenv("PM_LIMIT", env.int("PM_LIMIT", 4)))

test_server = bool(os.getenv("TEST_SERVER", env.bool("TEST_SERVER", False)))
modules_repo_branch = os.getenv(
    "MODULES_REPO_BRANCH", env.str("MODULES_REPO_BRANCH", "main")
)

port = int(os.getenv("PORT", env.int("PORT", 8000)))
