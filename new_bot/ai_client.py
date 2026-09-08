import logging
import aiohttp
from typing import Optional

log = logging.getLogger(__name__)

_session: Optional[aiohttp.ClientSession] = None

async def get_session() -> aiohttp.ClientSession:
    global _session
    if _session is None or _session.closed:
        _session = aiohttp.ClientSession()
    return _session

async def close_session():
    global _session
    if _session and not _session.closed:
        await _session.close()

async def chat_completion(prompt: str, system: str, model: str, base_url: str, api_key: str, max_tokens: int = 2048) -> str:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": max_tokens,
    }
    session = await get_session()
    url = base_url.rstrip("/") + "/chat/completions"
    
    async with session.post(url, headers=headers, json=payload, timeout=aiohttp.ClientTimeout(total=120)) as resp:
        try:
            data = await resp.json(content_type=None)
        except Exception:
            text = await resp.text()
            raise RuntimeError(f"Не-JSON ответ от API (HTTP {resp.status}): {text[:300]}")

        if resp.status != 200:
            err_msg = f"HTTP {resp.status}"
            if isinstance(data, dict):
                err_msg = data.get("error", {}).get("message", err_msg) if isinstance(data.get("error"), dict) else data.get("error", err_msg)
            raise RuntimeError(err_msg)

        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as e:
            raise RuntimeError(f"Некорректный формат ответа: {data}") from e

async def test_connection(base_url: str, api_key: str, model: str) -> str:
    return await chat_completion("ping", "Отвечай одним словом: pong", model, base_url, api_key, max_tokens=10)
