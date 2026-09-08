#  Moon-Userbot - telegram userbot
#  Copyright (C) 2020-present Moon Userbot Organization
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.

#  Загрузчик модулей БЕЗ ограничений.
#  Поддерживается всё, что может быть исходником модуля:
#    * любая прямая ссылка (raw / github blob / gist / pastebin / любой хост)
#    * ссылка на сообщение Telegram (t.me/...) — файл или код в тексте
#    * локальный путь на сервере (файл или целая папка)
#    * архивы (.zip / .tar / .tar.gz / ...) — выгружаются все .py файлы
#    * reply на документ с любым именем и расширением
#    * reply на текстовое сообщение с кодом
#    * короткое имя из каталога, имя уже установленного модуля
#    * несколько целей за один вызов
#  Никаких белых списков, проверок хешей и ограничений по расширениям.

import hashlib
import importlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path
from urllib.parse import urlparse

import aiohttp
from pyrogram import Client, filters
from pyrogram.types import Message

from utils import modules_help, prefix
from utils.config import modules_repo_branch
from utils.db import db
from utils.scripts import load_module as base_load_module, unload_module

BASE_PATH = os.path.abspath(os.getcwd())
MODULES_DIR = os.path.join(BASE_PATH, "modules")
CUSTOM_DIR = os.path.join(MODULES_DIR, "custom_modules")
REPO_RAW_URL = (
    "https://raw.githubusercontent.com/The-MoonTg-project/custom_modules/"
    f"{modules_repo_branch}"
)

ARCHIVE_EXTS = (
    ".zip",
    ".tar",
    ".tar.gz",
    ".tgz",
    ".tar.bz2",
    ".tbz2",
    ".tar.xz",
    ".txz",
)

TG_LINK_RE = re.compile(
    r"(?:https?://)?(?:www\.)?(?:t|telegram)\.(?:me|dog)/+"
    r"(?:c/(\d+)|([A-Za-z0-9_]{3,}))/(\d+)"
)


def ensure_custom_dir() -> None:
    os.makedirs(CUSTOM_DIR, exist_ok=True)


def normalize_name(name: str) -> str:
    """Приводит любое имя файла к валидному имени python-модуля."""
    name = os.path.basename(str(name)).strip()
    name = re.sub(r"\.py$", "", name, flags=re.IGNORECASE)
    name = re.sub(r"[^0-9A-Za-z_]", "_", name).strip("_").lower()
    if not name:
        name = "module"
    if name[0].isdigit():
        name = f"mod_{name}"
    return name


def is_archive_name(name: str) -> bool:
    lowered = str(name).lower()
    return any(lowered.endswith(ext) for ext in ARCHIVE_EXTS)


def strip_code_fences(text: str) -> str:
    text = (text or "").strip()
    match = re.match(r"^```[a-zA-Z0-9_+-]*\n(.*?)\n?```$", text, re.DOTALL)
    if match:
        return match.group(1)
    return text


# --------------------------------------------------------------------------- #
#  Получение исходников модуля
# --------------------------------------------------------------------------- #
def extract_archive(content: bytes) -> list[tuple[str, bytes]]:
    """Достаёт все .py файлы из zip/tar архива."""
    files: list[tuple[str, bytes]] = []
    data = io.BytesIO(content)

    if zipfile.is_zipfile(data):
        data.seek(0)
        with zipfile.ZipFile(data) as archive:
            for info in archive.infolist():
                if info.is_dir() or "__MACOSX" in info.filename:
                    continue
                file_name = os.path.basename(info.filename)
                if not file_name.endswith(".py") or file_name.startswith("_"):
                    continue
                files.append((file_name, archive.read(info)))
        return files

    data.seek(0)
    try:
        archive = tarfile.open(fileobj=data)
    except tarfile.TarError:
        return files

    with archive:
        for member in archive.getmembers():
            if not member.isfile() or "__MACOSX" in member.name:
                continue
            file_name = os.path.basename(member.name)
            if not file_name.endswith(".py") or file_name.startswith("_"):
                continue
            extracted = archive.extractfile(member)
            if extracted is not None:
                files.append((file_name, extracted.read()))
    return files


def to_raw_url(url: str) -> str:
    """Превращает «человеческие» ссылки в ссылки на сырой файл/API."""
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    path = parsed.path.strip("/")
    parts = path.split("/") if path else []

    if host == "github.com" and len(parts) >= 5 and parts[2] in ("blob", "raw"):
        owner, repo, _, branch, *rest = parts
        return f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{'/'.join(rest)}"

    if host == "github.com" and len(parts) >= 5 and parts[2] == "tree":
        owner, repo, _, branch, *rest = parts
        return (
            f"https://api.github.com/repos/{owner}/{repo}/contents/"
            f"{'/'.join(rest)}?ref={branch}"
        )

    if host == "gist.github.com" and len(parts) >= 2:
        return f"https://api.github.com/gists/{parts[1]}"

    if host == "pastebin.com" and parts and parts[0] != "raw":
        return f"https://pastebin.com/raw/{parts[0]}"

    if "api.github.com" in host:
        return url

    return url


async def fetch_bytes(session: aiohttp.ClientSession, url: str) -> bytes:
    async with session.get(url, allow_redirects=True) as resp:
        if resp.status != 200:
            raise RuntimeError(f"HTTP {resp.status} для {url}")
        return await resp.read()


async def collect_from_url(
    session: aiohttp.ClientSession, url: str
) -> list[tuple[str, bytes]]:
    """Скачивает один файл, gist или целую папку GitHub."""
    url = to_raw_url(url)

    if "api.github.com/gists/" in url:
        data = json.loads(await fetch_bytes(session, url))
        files = list(data.get("files") or {})
        if not files:
            raise RuntimeError("в gist нет файлов")
        picked = [name for name in files if name.endswith(".py")] or files[:1]
        result = []
        for name in picked:
            raw_url = data["files"][name].get("raw_url")
            if raw_url:
                result.append((name, await fetch_bytes(session, raw_url)))
            else:
                result.append((name, data["files"][name].get("content", "").encode()))
        return result

    if "api.github.com/repos/" in url:
        data = json.loads(await fetch_bytes(session, url))
        if not isinstance(data, list):
            raise RuntimeError("не удалось прочитать папку репозитория")
        result = []
        for item in data:
            if item.get("type") != "file" or not item.get("name", "").endswith(".py"):
                continue
            if item["name"].startswith("_"):
                continue
            result.append(
                (item["name"], await fetch_bytes(session, item["download_url"]))
            )
        if not result:
            raise RuntimeError("в папке нет .py файлов")
        return result

    content = await fetch_bytes(session, url)
    file_name = os.path.basename(urlparse(url).path) or "module.py"
    if is_archive_name(file_name):
        archive_files = extract_archive(content)
        if archive_files:
            return archive_files
    return [(file_name, content)]


def parse_tg_link(url: str):
    """Достаёт (chat_id, message_id) из ссылки на сообщение Telegram."""
    match = TG_LINK_RE.search(url)
    if not match:
        return None
    channel, username, message_id = match.groups()
    chat_id = int(f"-100{channel}") if channel else username
    return chat_id, int(message_id)


async def collect_from_tg(client: Client, url: str) -> list[tuple[str, bytes]]:
    parsed = parse_tg_link(url)
    if not parsed:
        raise RuntimeError("некорректная ссылка на сообщение Telegram")
    chat_id, message_id = parsed

    message = await client.get_messages(chat_id, message_id)
    if message is None or getattr(message, "empty", False):
        raise RuntimeError("сообщение не найдено")
    return await collect_from_message(client, message)


async def collect_from_message(client: Client, message: Message):
    """Берёт модуль из документа (любого) или из текста сообщения."""
    document = getattr(message, "document", None)
    if document is not None:
        file_name = getattr(document, "file_name", None) or f"module_{message.id}.py"
        downloaded = await message.download(in_memory=True)
        if hasattr(downloaded, "getvalue"):
            content = downloaded.getvalue()
        else:
            with open(downloaded, "rb") as f:
                content = f.read()
            if os.path.exists(downloaded):
                os.remove(downloaded)
        if is_archive_name(file_name):
            archive_files = extract_archive(content)
            if archive_files:
                return archive_files
        if not file_name.endswith(".py"):
            file_name = f"{normalize_name(file_name)}.py"
        return [(file_name, content)]

    text = strip_code_fences(getattr(message, "text", None) or "")
    if not text:
        raise RuntimeError("в сообщении нет ни файла, ни кода")
    return [(f"module_{message.id}.py", text.encode())]


async def collect_from_catalog(
    session: aiohttp.ClientSession, target: str
) -> list[tuple[str, bytes]]:
    module_name = normalize_name(target)

    local_path = os.path.join(CUSTOM_DIR, f"{module_name}.py")
    if os.path.exists(local_path):
        with open(local_path, "rb") as f:
            return [(os.path.basename(local_path), f.read())]

    try:
        catalog_text = (await fetch_bytes(session, f"{REPO_RAW_URL}/full.txt")).decode()
    except Exception as e:  # noqa: BLE001
        raise RuntimeError(f"каталог недоступен: {e}") from e

    modules_dict = {
        line.strip().split("/")[-1].split()[0]: line.strip()
        for line in catalog_text.splitlines()
        if line.strip()
    }
    if module_name not in modules_dict:
        raise RuntimeError(
            f"«{module_name}» не найден — укажите прямую ссылку или файл"
        )
    return await collect_from_url(session, f"{REPO_RAW_URL}/{modules_dict[module_name]}.py")


async def collect_from_path(target: str) -> list[tuple[str, bytes]] | None:
    """Локальный файл или папка на сервере."""
    candidates = [target, os.path.join(BASE_PATH, target)]
    if not target.startswith("/"):
        candidates.append(os.path.join(CUSTOM_DIR, target))
        candidates.append(os.path.join(MODULES_DIR, target))

    for candidate in candidates:
        if os.path.isfile(candidate):
            with open(candidate, "rb") as f:
                content = f.read()
            if is_archive_name(candidate):
                archive_files = extract_archive(content)
                if archive_files:
                    return archive_files
            return [(os.path.basename(candidate), content)]

        if os.path.isdir(candidate):
            files = []
            for path in sorted(Path(candidate).rglob("*.py")):
                if path.name.startswith("_") or "__pycache__" in path.parts:
                    continue
                with open(path, "rb") as f:
                    files.append((path.name, f.read()))
            if files:
                return files
    return None


async def collect_from_target(
    client: Client, session: aiohttp.ClientSession, target: str
) -> list[tuple[str, bytes]]:
    target = target.strip()
    if not target:
        return []

    if re.match(r"^(https?://)?(www\.)?(t|telegram)\.(me|dog)/", target, re.IGNORECASE):
        url = target if target.startswith(("http://", "https://")) else f"https://{target}"
        if parse_tg_link(url):
            return await collect_from_tg(client, url)
        return await collect_from_url(session, url)

    if target.startswith(("http://", "https://")):
        return await collect_from_url(session, target)

    from_path = await collect_from_path(target)
    if from_path is not None:
        return from_path

    return await collect_from_catalog(session, target)


# --------------------------------------------------------------------------- #
#  Установка и загрузка
# --------------------------------------------------------------------------- #
async def force_load_module(module_name: str, client: Client, message: Message = None):
    """
    Загружает модуль в рантайм. Сначала используется штатный загрузчик,
    а если он по какой-то причине не справился — модуль подключается напрямую.
    """
    try:
        return await base_load_module(module_name, client, message)
    except Exception:
        mod_path = f"modules.custom_modules.{module_name}"
        if mod_path in sys.modules:
            module = importlib.reload(sys.modules[mod_path])
        else:
            module = importlib.import_module(mod_path)

        for _name, obj in vars(module).items():
            handlers = getattr(obj, "handlers", None)
            if not isinstance(handlers, list):
                continue
            for handler, group in handlers:
                client.add_handler(handler, group)
        return module


def save_files(files: list[tuple[str, bytes]]) -> tuple[list[str], list[str]]:
    """Кладёт исходники в modules/custom_modules. Возвращает (имена, ошибки)."""
    ensure_custom_dir()
    saved: list[str] = []
    errors: list[str] = []

    for file_name, content in files:
        try:
            if is_archive_name(file_name):
                archive_files = extract_archive(content)
                if not archive_files:
                    errors.append(f"{file_name}: архив без .py файлов")
                    continue
                names, inner_errors = save_files(archive_files)
                saved.extend(names)
                errors.extend(inner_errors)
                continue

            module_name = normalize_name(file_name)
            with open(os.path.join(CUSTOM_DIR, f"{module_name}.py"), "wb") as f:
                f.write(content)
            saved.append(module_name)
        except Exception as e:  # noqa: BLE001
            errors.append(f"{file_name}: {e}")

    return saved, errors


def register_module(module_name: str) -> None:
    all_modules = db.get("custom.modules", "allModules", [])
    if module_name not in all_modules:
        all_modules.append(module_name)
        db.set("custom.modules", "allModules", all_modules)


def unregister_module(module_name: str) -> None:
    all_modules = db.get("custom.modules", "allModules", [])
    if module_name in all_modules:
        all_modules.remove(module_name)
        db.set("custom.modules", "allModules", all_modules)


async def fetch_catalog() -> str:
    async with aiohttp.ClientSession() as session:
        return (await fetch_bytes(session, f"{REPO_RAW_URL}/full.txt")).decode()


def parse_catalog(catalog_text: str) -> dict:
    return {
        line.strip().split("/")[-1].split()[0]: line.strip()
        for line in catalog_text.splitlines()
        if line.strip()
    }


# --------------------------------------------------------------------------- #
#  Команды
# --------------------------------------------------------------------------- #
@Client.on_message(filters.command(["modhash", "mh"], prefix) & filters.me)
async def get_mod_hash(_, message: Message):
    if len(message.command) == 1:
        return
    url = message.command[1]
    async with aiohttp.ClientSession() as session:
        try:
            content = await fetch_bytes(session, to_raw_url(url))
        except Exception as e:  # noqa: BLE001
            return await message.edit(f"<b>Error:</b> <code>{e}</code>")

    file_name = url.rstrip("/").split("/")[-1]
    sha256_hash = hashlib.sha256(content).hexdigest()
    await message.edit(
        f"<b>Module hash:</b> <code>{sha256_hash}</code>\n"
        f"<b>Link:</b> <code>{url}</code>\n"
        f"<b>File:</b> <code>{file_name}</code>"
    )


@Client.on_message(filters.command(["loadmod", "lm"], prefix) & filters.me)
async def loadmod(client: Client, message: Message):
    args = list(message.command[1:])

    name_override = None
    if "-n" in args:
        idx = args.index("-n")
        if idx + 1 < len(args):
            name_override = normalize_name(args[idx + 1])
            del args[idx : idx + 2]
    for arg in list(args):
        if arg.startswith("--name="):
            name_override = normalize_name(arg.split("=", 1)[1])
            args.remove(arg)

    targets = [arg for arg in args if not arg.startswith("-")]
    reply = message.reply_to_message

    if reply is None and not targets:
        return await message.edit(
            "<b>Укажите ссылку, имя модуля, путь к файлу "
            "или ответьте на файл/код</b>"
        )

    await message.edit("<b>Загрузка модуля...</b>")

    files: list[tuple[str, bytes]] = []
    errors: list[str] = []

    if reply is not None:
        try:
            files = await collect_from_message(client, reply)
        except Exception as e:  # noqa: BLE001
            return await message.edit(
                f"<b>Не удалось получить модуль:</b> <code>{e}</code>"
            )
    else:
        async with aiohttp.ClientSession() as session:
            for target in targets:
                try:
                    files.extend(await collect_from_target(client, session, target))
                except Exception as e:  # noqa: BLE001
                    errors.append(f"{target}: {e}")

    if name_override and len(files) == 1:
        files = [(f"{name_override}.py", files[0][1])]

    if not files:
        text = "<b>Ничего не удалось загрузить</b>"
        if errors:
            text += "\n<code>" + "\n".join(errors[:10]) + "</code>"
        return await message.edit(text)

    saved, save_errors = save_files(files)
    errors.extend(save_errors)

    if not saved:
        text = "<b>Не удалось сохранить модули</b>"
        if errors:
            text += "\n<code>" + "\n".join(errors[:10]) + "</code>"
        return await message.edit(text)

    loaded: list[str] = []
    for module_name in saved:
        try:
            await force_load_module(module_name, client, message)
        except Exception as e:  # noqa: BLE001
            errors.append(f"{module_name}: {e}")
            continue
        register_module(module_name)
        loaded.append(module_name)

    text = ""
    if loaded:
        text += (
            f"<b>Модуль(и) установлены и загружены:</b> "
            f"<code>{', '.join(loaded)}</code>"
        )
    if errors:
        text += "\n\n<b>Ошибки:</b>\n<code>" + "\n".join(errors[:10]) + "</code>"
    await message.edit(text or "<b>Нечего загружать</b>")


@Client.on_message(filters.command(["unloadmod", "ulm"], prefix) & filters.me)
async def unload_mods(client: Client, message: Message):
    if len(message.command) <= 1:
        return await message.edit("<b>Укажите имя модуля для выгрузки</b>")

    module_name = normalize_name(message.command[1])

    custom_mod_path = os.path.join(CUSTOM_DIR, f"{module_name}.py")
    builtin_mod_path = os.path.join(MODULES_DIR, f"{module_name}.py")

    try:
        await unload_module(module_name, client)
    except Exception:  # noqa: BLE001
        pass

    removed = False
    for path in (custom_mod_path, builtin_mod_path):
        if os.path.exists(path):
            os.remove(path)
            removed = True

    if module_name == "musicbot":
        musicbot_path = os.path.join(BASE_PATH, "musicbot")
        if os.path.exists(musicbot_path):
            subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pip",
                    "uninstall",
                    "-y",
                    "-r",
                    "requirements.txt",
                ],
                cwd=musicbot_path,
            )
            shutil.rmtree(musicbot_path, ignore_errors=True)

    if not removed:
        return await message.edit(
            f"<b>Файл модуля <code>{module_name}</code> не найден</b>"
        )

    unregister_module(module_name)
    await message.edit(f"<b>Модуль <code>{module_name}</code> удален!</b>")


@Client.on_message(filters.command(["loadallmods", "lmall"], prefix) & filters.me)
async def load_all_mods(client: Client, message: Message):
    await message.edit("<b>Получение списка модулей...</b>")
    ensure_custom_dir()

    try:
        catalog_text = await fetch_catalog()
    except Exception as e:  # noqa: BLE001
        return await message.edit(f"<b>Ошибка сети:</b> <code>{e}</code>")

    modules_dict = parse_catalog(catalog_text)

    await message.edit("<b>Скачивание модулей...</b>")
    async with aiohttp.ClientSession() as session:
        for name, entry in modules_dict.items():
            try:
                files = await collect_from_url(session, f"{REPO_RAW_URL}/{entry}.py")
            except Exception:  # noqa: BLE001
                continue
            save_files(files)

    await message.edit("<b>Загрузка модулей...</b>")
    loaded = 0
    for name in modules_dict:
        try:
            await force_load_module(name, client)
        except Exception:  # noqa: BLE001
            continue
        register_module(name)
        loaded += 1

    await message.edit(f"<b>Загружено модулей: {loaded}</b>")


@Client.on_message(filters.command(["unloadallmods", "ulmall"], prefix) & filters.me)
async def unload_all_mods(client: Client, message: Message):
    if not os.path.exists(CUSTOM_DIR):
        return await message.edit("<b>Нет установленных кастомных модулей</b>")

    custom_modules = [f[:-3] for f in os.listdir(CUSTOM_DIR) if f.endswith(".py")]
    if not custom_modules:
        return await message.edit("<b>Нет установленных кастомных модулей</b>")

    await message.edit("<b>Выгрузка всех модулей...</b>")
    for name in custom_modules:
        try:
            await unload_module(name, client)
        except Exception:  # noqa: BLE001
            pass

    shutil.rmtree(CUSTOM_DIR, ignore_errors=True)
    ensure_custom_dir()
    db.set("custom.modules", "allModules", [])
    await message.edit("<b>Все кастомные модули удалены!</b>")


@Client.on_message(filters.command(["updateallmods"], prefix) & filters.me)
async def updateallmods(client: Client, message: Message):
    if not os.path.exists(CUSTOM_DIR):
        return await message.edit("<b>Нет установленных модулей</b>")

    installed_files = [f for f in os.listdir(CUSTOM_DIR) if f.endswith(".py")]
    if not installed_files:
        return await message.edit("<b>Нет установленных модулей</b>")

    await message.edit("<b>Проверка обновлений репозитория...</b>")
    try:
        catalog_text = await fetch_catalog()
    except Exception as e:  # noqa: BLE001
        return await message.edit(f"<b>Ошибка:</b> <code>{e}</code>")

    modules_dict = parse_catalog(catalog_text)

    await message.edit("<b>Обновление модулей...</b>")
    updated = 0
    async with aiohttp.ClientSession() as session:
        for mod_file in installed_files:
            mod_name = mod_file[:-3]
            if mod_name not in modules_dict:
                continue
            try:
                files = await collect_from_url(
                    session, f"{REPO_RAW_URL}/{modules_dict[mod_name]}.py"
                )
            except Exception:  # noqa: BLE001
                continue
            save_files([(f"{mod_name}.py", files[0][1])])
            try:
                await force_load_module(mod_name, client)
                updated += 1
            except Exception:  # noqa: BLE001
                pass

    await message.edit(f"<b>Обновлено модулей: {updated}</b>")


modules_help["loader"] = {
    "loadmod [ссылка/имя/путь/архив] [-n имя]*": (
        "Установить модуль откуда угодно: ссылка, github/gist/pastebin, "
        "t.me-ссылка на сообщение, локальный путь, reply на файл или на код. "
        "Можно несколько целей сразу"
    ),
    "unloadmod [name]*": "Удалить модуль (кастомный или встроенный)",
    "modhash [link]*": "Узнать SHA-256 хеш файла по ссылке",
    "loadallmods": "Загрузить все модули из каталога",
    "unloadallmods": "Удалить все кастомные модули",
    "updateallmods": "Обновить модули из каталога",
}
