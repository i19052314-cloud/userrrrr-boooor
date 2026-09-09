import json
import sqlite3
import threading
from typing import Any, List

class Database:
    def __init__(self, path: str = "bot.db"):
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        self._init_tables()

    def _init_tables(self):
        with self._lock:
            cur = self._conn.cursor()
            cur.execute("""
                CREATE TABLE IF NOT EXISTS kv (
                    module TEXT NOT NULL,
                    var TEXT NOT NULL,
                    val TEXT NOT NULL,
                    type TEXT NOT NULL,
                    PRIMARY KEY (module, var)
                )
            """)
            self._conn.commit()

    def _execute(self, sql, params=()):
        with self._lock:
            cur = self._conn.cursor()
            cur.execute(sql, params)
            self._conn.commit()
            return cur

    def get(self, module: str, var: str, default: Any = None) -> Any:
        cur = self._execute("SELECT val, type FROM kv WHERE module=? AND var=?", (module, var))
        row = cur.fetchone()
        if not row:
            return default
        val, typ = row["val"], row["type"]
        if typ == "bool":
            return val == "1"
        if typ == "int":
            return int(val)
        if typ == "str":
            return val
        return json.loads(val)

    def set(self, module: str, var: str, value: Any):
        if isinstance(value, bool):
            val, typ = ("1" if value else "0", "bool")
        elif isinstance(value, str):
            val, typ = (value, "str")
        elif isinstance(value, int):
            val, typ = (str(value), "int")
        else:
            val, typ = (json.dumps(value, ensure_ascii=False), "json")

        self._execute("""
            INSERT INTO kv (module, var, val, type) VALUES (?, ?, ?, ?)
            ON CONFLICT(module, var) DO UPDATE SET val=excluded.val, type=excluded.type
        """, (module, var, val, typ))

    def remove(self, module: str, var: str):
        self._execute("DELETE FROM kv WHERE module=? AND var=?", (module, var))

# Глобальный инстанс
db = Database()

# Хелперы для моделей как в оригинале
DEFAULT_MODELS = [
    "google/gemini-2.0-flash-001",
    "google/gemini-1.5-flash-8b",
    "openai/gpt-4o-mini",
    "meta-llama/llama-4-scout",
    "mistralai/mistral-7b-instruct",
    "MiniMaxAI/MiniMax-M2.7",
    "MiniMaxAI/MiniMax-M3",
    "stealth/ox-alpha",
    "z-ai/glm-5.3-flash",
]

def get_models() -> List[str]:
    saved = db.get("custom.chatbot", "models", None)
    if saved is None:
        db.set("custom.chatbot", "models", DEFAULT_MODELS)
        return DEFAULT_MODELS.copy()
    return saved

def save_models(models: List[str]):
    db.set("custom.chatbot", "models", models)

def get_current_model() -> str:
    from .config import AI_MODEL
    model = db.get("custom.chatbot", "current_model", None)
    if model is None:
        db.set("custom.chatbot", "current_model", AI_MODEL)
        return AI_MODEL
    return model

def set_current_model(model: str) -> bool:
    if model in get_models():
        db.set("custom.chatbot", "current_model", model)
        return True
    return False
