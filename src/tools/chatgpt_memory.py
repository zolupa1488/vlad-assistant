"""Семантический поиск по ChatGPT-архиву Vladimir (второй мозг).

Под капотом — Chroma SQLite collection, наполненная скриптом
second-brain/import_chatgpt.py. Хранит embeddings + metadata (conv_id,
title, ts, category, topics, people, facts).

Embeddings — sentence-transformers/multilingual-e5-base (локально, бесплатно).
"""

from __future__ import annotations

import json
import os
import tarfile
import urllib.request
from pathlib import Path
from typing import Any

from loguru import logger

# Путь к Chroma DB. На Railway — persistent volume /app/data/.
_CHROMA_DIR = Path("/app/data/chroma_vlad")
_FALLBACKS = [
    Path(__file__).parent.parent.parent / "data" / "chroma_vlad",
    Path.home() / "vlad-assistant" / "data" / "chroma_vlad",
]

# URL архива с Chroma DB (GitHub Release). Загружается один раз при cold-start.
# Меняй после каждой переиндексации.
_CHROMA_ARCHIVE_URL = os.environ.get(
    "CHATGPT_MEMORY_ARCHIVE_URL",
    "https://github.com/zolupa1488/vlad-assistant/releases/download/second-brain-v1/chroma_vlad.tar.gz",
)


def _resolve_chroma_path() -> Path:
    """Найти готовую Chroma на диске, если есть."""
    for p in [_CHROMA_DIR, *_FALLBACKS]:
        if p.exists() and any(p.iterdir()):
            return p
    return _CHROMA_DIR  # дефолт куда будем скачивать


def _ensure_chroma_db() -> Path:
    """Возвращает путь к локальной Chroma. База создаётся скриптом chatgpt_index.py
    (admin-команда /index_chatgpt в Telegram). Если базы нет — даёт ясную ошибку."""
    path = _resolve_chroma_path()
    if path.exists() and any(path.iterdir()):
        return path
    raise RuntimeError(
        "Chroma база ChatGPT-архива пока не построена. "
        "Попроси Vladimir-владельца запустить admin-команду /index_chatgpt в Telegram — "
        "бот скачает архив с GitHub Release и проиндексирует."
    )


_collection = None


def _get_collection():
    global _collection
    if _collection is not None:
        return _collection

    chroma_path = _ensure_chroma_db()

    import chromadb
    from chromadb.utils import embedding_functions

    client = chromadb.PersistentClient(path=str(chroma_path))
    embedder = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name="intfloat/multilingual-e5-base"
    )
    _collection = client.get_or_create_collection(
        name="vlad_chatgpt",
        embedding_function=embedder,
    )
    return _collection


def _format_hit(idx: int, doc: str, meta: dict[str, Any] | None, distance: float | None) -> dict:
    meta = meta or {}
    out = {
        "rank": idx + 1,
        "text": doc,
        "category": meta.get("category", "unknown"),
    }
    if meta.get("title"):
        out["title"] = meta["title"]
    if meta.get("create_time"):
        import time
        out["date"] = time.strftime("%Y-%m-%d", time.localtime(float(meta["create_time"])))
    if meta.get("conv_url"):
        out["url"] = meta["conv_url"]
    if meta.get("topics"):
        out["topics"] = meta["topics"]
    if meta.get("people"):
        out["people"] = meta["people"]
    if distance is not None:
        out["score"] = round(1.0 - distance, 3)
    return out


async def recall_history(query: str, n: int = 5) -> str:
    """Семантический поиск по архиву ChatGPT-диалогов Vladimir.

    Возвращает top-N самых релевантных фрагментов с заголовком, датой, категорией,
    темами и ссылкой на исходный диалог. Подходит когда вопрос звучит как «помнишь
    мы обсуждали...», «к чему я пришёл насчёт...», «что я думал про...».
    """
    try:
        coll = _get_collection()
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)

    res = coll.query(
        query_texts=[query],
        n_results=min(max(n, 1), 20),
    )
    docs = (res.get("documents") or [[]])[0]
    metas = (res.get("metadatas") or [[]])[0]
    dists = (res.get("distances") or [[None] * len(docs)])[0]

    hits = [_format_hit(i, d, m, ds) for i, (d, m, ds) in enumerate(zip(docs, metas, dists))]
    return json.dumps({"query": query, "n_hits": len(hits), "hits": hits}, ensure_ascii=False)


async def recall_chain(topic: str, n: int = 8) -> str:
    """Логическая цепочка по теме: вытаскивает связанные эпизоды из истории
    в хронологическом порядке (сначала старые → как Vladimir пришёл к выводу).

    Используй когда вопрос звучит как «как я пришёл к...», «эволюция моего
    взгляда на...», «история работы с...».
    """
    try:
        coll = _get_collection()
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)

    res = coll.query(
        query_texts=[topic],
        n_results=min(max(n, 1), 30),
    )
    docs = (res.get("documents") or [[]])[0]
    metas = (res.get("metadatas") or [[]])[0]
    dists = (res.get("distances") or [[None] * len(docs)])[0]

    hits = [_format_hit(i, d, m, ds) for i, (d, m, ds) in enumerate(zip(docs, metas, dists))]
    # Сортируем по дате (создание диалога), не по релевантности
    hits.sort(key=lambda h: h.get("date", "0"))
    return json.dumps({"topic": topic, "n_episodes": len(hits), "chain": hits}, ensure_ascii=False)


async def recall_decision(topic: str, n: int = 5) -> str:
    """Точечный поиск решений Vladimir по теме (фильтр category=decision).
    Используй для вопросов «что я решил по...», «какой выбор я сделал насчёт...».
    """
    try:
        coll = _get_collection()
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)

    res = coll.query(
        query_texts=[topic],
        n_results=min(max(n, 1) * 3, 30),  # over-fetch, потом фильтр
        where={"category": "decision"},
    )
    docs = (res.get("documents") or [[]])[0]
    metas = (res.get("metadatas") or [[]])[0]
    dists = (res.get("distances") or [[None] * len(docs)])[0]

    hits = [_format_hit(i, d, m, ds) for i, (d, m, ds) in enumerate(zip(docs, metas, dists))][:n]
    return json.dumps({"topic": topic, "decisions": hits}, ensure_ascii=False)


# ---------- Живая память — бот растит мозг с каждого разговора ----------


def remember_turn_sync(user_text: str, reply: str) -> None:
    """Сохранить содержательный разговор в долгую память (Chroma).

    Вызывается fire-and-forget из handlers после каждого ответа.
    Синхронная (chromadb sync) — оборачивай в asyncio.to_thread.
    Короткую болтовню («привет», «ок») не сохраняем.
    """
    import hashlib
    import time

    text = (user_text or "").strip()
    if len(text) < 200:
        return  # мелочь — не засоряем мозг

    try:
        coll = _get_collection()
    except Exception:
        return  # база ещё не построена — тихо пропускаем

    ts = time.time()
    cid = "tg-" + hashlib.md5(f"{ts}{text[:80]}".encode()).hexdigest()[:14]
    doc = f"[Разговор в Telegram, {time.strftime('%Y-%m-%d', time.localtime(ts))}]\n"
    doc += f"Владимир: {text[:1800]}"
    if reply:
        doc += f"\nОтвет: {reply[:600]}"
    meta = {
        "source": "telegram_live",
        "category": "conversation",
        "create_time": ts,
        "title": text[:60].replace("\n", " "),
    }
    try:
        coll.upsert(documents=[doc], metadatas=[meta], ids=[cid])
        logger.info("live memory: saved turn ({} chars)", len(text))
    except Exception as e:
        logger.warning("remember_turn failed: {}", e)
