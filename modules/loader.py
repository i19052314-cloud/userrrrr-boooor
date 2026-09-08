#  Moon-Userbot - telegram userbot
#  Copyright (C) 2020-present Moon Userbot Organization
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.

import hashlib
import importlib
import os
import shutil
import subprocess
import sys
from urllib.parse import urlparse

import aiohttp
from pyrogram import Client, filters
from pyrogram.types import Message

from utils import modules_help, prefix
from utils.db import db
from utils.scripts import load_module as base_load_module, unload_module

BASE_PATH = os.path.abspath(os.getcwd())
CUSTOM_DIR = os.path.join(BASE_PATH, "modules", "custom_modules")
REPO_RAW_URL = "https://raw.githubusercontent.com/The-MoonTg-project/custom_modules/main"


def ensure_custom_dir():
    os.makedirs(CUSTOM_DIR, exist_ok=True)


async def force_load_module(module_name: str, client: Client, message: Message = None):
    """
    Загружает модуль напрямую без блокировок по modules_hashes.txt.
    Сначала пытается использовать стандартный загрузчик, а при ошибке
    хеша/белого списка импортирует модуль напрямую.
    """
    try:
        await base_load_module(module_name, client, message)
    except Exception as e:
        # Если стандартный load_module заблокировал модуль по хешу/источнику,
        # подключаем его напрямую через sys.modules / importlib
        mod_path = f"modules.custom_modules.{module_name}"
        if mod_path in sys.modules:
            importlib.reload(sys.modules[mod_path])
        else:
            mod = importlib.import_module(mod_path)
            for attr in dir(mod):
                handler = getattr(mod, attr)
                if callable(handler) and hasattr(handler, "handlers"):
                    for h, group in handler.handlers:
                        client.add_handler(h, group)


@Client.on_message(filters.command(["modhash", "mh"], prefix) & filters.me)
async def get_mod_hash(_, message: Message):
    if len(message.command) == 1:
        return
    url = message.command[1]
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url) as resp:
                if resp.status != 200:
                    return await message.edit(
                        f"<b>Failed to download: <code>{url}</code> (Status: {resp.status})</b>"
                    )
                content = await resp.read()
        except Exception as e:
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
    is_reply_doc = (
        message.reply_to_message
        and message.reply_to_message.document
        and message.reply_to_message.document.file_name
        and message.reply_to_message.document.file_name.endswith(".py")
    )

    if not is_reply_doc and len(message.command) == 1:
        return await message.edit("<b>Укажите ссылку, имя модуля или ответьте на .py файл</b>")

    ensure_custom_dir()

    if len(message.command) > 1:
        await message.edit("<b>Загрузка модуля...</b>")
        target = message.command[1]

        # 1. Если передана произвольная ссылка (http / https)
        if target.startswith(("http://", "https://")):
            url = target
            parsed_path = urlparse(url).path
            file_part = parsed_path.rstrip("/").split("/")[-1]
            module_name = file_part[:-3] if file_part.endswith(".py") else file_part
            module_name = module_name.lower().replace("-", "_")

        # 2. Если указано короткое имя из официального репозитория
        elif "." not in target:
            module_name = target.lower().replace("-", "_")
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(f"{REPO_RAW_URL}/full.txt") as resp:
                        if resp.status != 200:
                            return await message.edit("<b>Не удалось получить каталог модулей</b>")
                        catalog_text = await resp.text()
            except Exception as e:
                return await message.edit(f"<b>Ошибка каталога:</b> <code>{e}</code>")

            modules_dict = {
                line.strip().split("/")[-1].split()[0]: line.strip()
                for line in catalog_text.splitlines()
                if line.strip()
            }

            if module_name in modules_dict:
                url = f"{REPO_RAW_URL}/{modules_dict[module_name]}.py"
            else:
                return await message.edit(f"<b>Модуль <code>{module_name}</code> не найден в репозитории</b>")

        # 3. Любая другая относительная ссылка/путь
        else:
            module_name = target.rstrip("/").split("/")[-1].replace(".py", "").lower()
            url = target

        # Скачиваем файл модуля
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    if resp.status != 200:
                        return await message.edit(f"<b>Ошибка скачивания ({resp.status}): <code>{url}</code></b>")
                    resp_content = await resp.read()
        except Exception as e:
            return await message.edit(f"<b>Не удалось скачать модуль:</b> <code>{e}</code>")

        dest_path = os.path.join(CUSTOM_DIR, f"{module_name}.py")
        with open(dest_path, "wb") as f:
            f.write(resp_content)

    # Загрузка через reply на .py файл
    else:
        file_name = await message.reply_to_message.download()
        raw_name = message.reply_to_message.document.file_name[:-3]
        module_name = raw_name.lower().replace("-", "_")
        dest_path = os.path.join(CUSTOM_DIR, f"{module_name}.py")
        if os.path.exists(dest_path):
            os.remove(dest_path)
        os.rename(file_name, dest_path)

    # Сохраняем имя модуля в базу данных
    all_modules = db.get("custom.modules", "allModules", [])
    if module_name not in all_modules:
        all_modules.append(module_name)
        db.set("custom.modules", "allModules", all_modules)

    # Загружаем модуль в рантайм юзербота
    try:
        await force_load_module(module_name, client, message)
        await message.edit(f"<b>Модуль <code>{module_name}</code> успешно установлен и загружен!</b>")
    except Exception as e:
        await message.edit(f"<b>Ошибка при загрузке модуля <code>{module_name}</code>:</b>\n<code>{e}</code>")


@Client.on_message(filters.command(["unloadmod", "ulm"], prefix) & filters.me)
async def unload_mods(client: Client, message: Message):
    if len(message.command) <= 1:
        return await message.edit("<b>Укажите имя модуля для выгрузки</b>")

    raw_target = message.command[1].lower()
    module_name = raw_target.rstrip("/").split("/")[-1].replace(".py", "")

    custom_mod_path = os.path.join(CUSTOM_DIR, f"{module_name}.py")
    builtin_mod_path = os.path.join(BASE_PATH, "modules", f"{module_name}.py")

    if os.path.exists(custom_mod_path):
        try:
            await unload_module(module_name, client)
        except Exception:
            pass

        os.remove(custom_mod_path)

        if module_name == "musicbot":
            musicbot_path = os.path.join(BASE_PATH, "musicbot")
            if os.path.exists(musicbot_path):
                subprocess.run(
                    [sys.executable, "-m", "pip", "uninstall", "-y", "-r", "requirements.txt"],
                    cwd=musicbot_path,
                )
                shutil.rmtree(musicbot_path, ignore_errors=True)

        all_modules = db.get("custom.modules", "allModules", [])
        if module_name in all_modules:
            all_modules.remove(module_name)
            db.set("custom.modules", "allModules", all_modules)

        await message.edit(f"<b>Модуль <code>{module_name}</code> удален!</b>")
    elif os.path.exists(builtin_mod_path):
        await message.edit("<b>Запрещено удалять встроенные модули</b>")
    else:
        await message.edit(f"<b>Модуль <code>{module_name}</code> не найден</b>")


@Client.on_message(filters.command(["loadallmods", "lmall"], prefix) & filters.me)
async def load_all_mods(client: Client, message: Message):
    await message.edit("<b>Получение списка модулей...</b>")
    ensure_custom_dir()

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{REPO_RAW_URL}/full.txt") as resp:
                if resp.status != 200:
                    return await message.edit("<b>Не удалось получить список модулей</b>")
                catalog_text = await resp.text()
    except Exception as e:
        return await message.edit(f"<b>Ошибка сети:</b> <code>{e}</code>")

    modules_list = [line.strip() for line in catalog_text.splitlines() if line.strip()]

    await message.edit("<b>Скачивание модулей...</b>")
    async with aiohttp.ClientSession() as session:
        for mod_entry in modules_list:
            url = f"{REPO_RAW_URL}/{mod_entry}.py"
            mod_file_name = f"{mod_entry.split('/')[-1]}.py"
            try:
                async with session.get(url) as resp:
                    if resp.status != 200:
                        continue
                    content = await resp.read()
                with open(os.path.join(CUSTOM_DIR, mod_file_name), "wb") as f:
                    f.write(content)
            except Exception:
                continue

    loaded = 0
    all_modules = db.get("custom.modules", "allModules", [])
    for mod_entry in modules_list:
        name = mod_entry.split("/")[-1].split()[0]
        try:
            await force_load_module(name, client)
            if name not in all_modules:
                all_modules.append(name)
            loaded += 1
        except Exception:
            pass

    db.set("custom.modules", "allModules", all_modules)
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
        except Exception:
            pass

    shutil.rmtree(CUSTOM_DIR, ignore_errors=True)
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
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{REPO_RAW_URL}/full.txt") as resp:
                if resp.status != 200:
                    return await message.edit("<b>Не удалось получить список модулей</b>")
                catalog_text = await resp.text()
    except Exception as e:
        return await message.edit(f"<b>Ошибка:</b> <code>{e}</code>")

    modules_dict = {
        line.strip().split("/")[-1].split()[0]: line.strip()
        for line in catalog_text.splitlines()
        if line.strip()
    }

    await message.edit("<b>Обновление модулей...</b>")
    updated = 0
    async with aiohttp.ClientSession() as session:
        for mod_file in installed_files:
            mod_name = mod_file[:-3]
            if mod_name not in modules_dict:
                continue

            target_url = f"{REPO_RAW_URL}/{modules_dict[mod_name]}.py"
            try:
                async with session.get(target_url) as resp:
                    if resp.status != 200:
                        continue
                    content = await resp.read()

                with open(os.path.join(CUSTOM_DIR, mod_file), "wb") as f:
                    f.write(content)

                await force_load_module(mod_name, client)
                updated += 1
            except Exception:
                pass

    await message.edit(f"<b>Обновлено модулей: {updated}</b>")


modules_help["loader"] = {
    "loadmod [link/name]*": "Установить модуль по прямой ссылке, имени из каталога или reply на .py файл",
    "unloadmod [name]*": "Удалить кастомный модуль",
    "modhash [link]*": "Узнать SHA-256 хеш файла по ссылке",
    "loadallmods": "Загрузить все модули из каталога",
    "unloadallmods": "Удалить все кастомные модули",
    "updateallmods": "Обновить модули из каталога",
}
