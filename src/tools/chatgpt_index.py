"""Облачная индексация ChatGPT-архива в Chroma — работает прямо на Railway.

Архив conversations-*.json (упакованный в tar.gz) лежит в GitHub Release.
Бот:
  1. Качает архив один раз → /app/data/chatgpt_export/
  2. Парсит 509 диалогов
  3. Фильтрует мусор + LLM-extraction через OpenRouter gpt-4o-mini
  4. Embed через sentence-transformers (multilingual-e5-base, локально на Railway)
  5. Сохраняет в Chroma → /app/data/chroma_vlad/ (collection vlad_chatgpt)

Запускается админ-командой /index_chatgpt в Telegram (только владелец).
Прогресс пишет в Telegram.

Хранилище — chromadb напрямую (без mem0): та же collection "vlad_chatgpt"
и тот же embedder, что использует chatgpt_memory.py для чтения.
"""

from __future__ import annotations

import glob
import json
import os
import re
import tarfile
import time
import urllib.request
from pathlib import Path
from typing import Any, Callable

from loguru import logger
from openai import OpenAI

DATA_DIR = Path("/app/data")
EXPORT_DIR = DATA_DIR / "chatgpt_export"
CHROMA_DIR = DATA_DIR / "chroma_vlad"
COLLECTION_NAME = "vlad_chatgpt"
EMBED_MODEL = "intfloat/multilingual-e5-base"
ARCHIVE_URL_ENV = "CHATGPT_EXPORT_ARCHIVE_URL"
DEFAULT_ARCHIVE_URL = (
    "https://github.com/zolupa1488/vlad-assistant/releases/download/"
    "chatgpt-export-v1/chatgpt_conversations.tar.gz"
)


# ---------- Фильтрация мусора ----------
JUNK_TITLE_PATTERNS = [r"^new chat$", r"^untitled", r"^test", r"^привет$", r"^hi$"]
JUNK_HINTS = ["poem", "joke", "sing me", "rhyme", "перевести фразу", "что значит слово"]


def _is_junk_title(t: str) -> bool:
    tl = (t or "").strip().lower()
    return not tl or any(re.search(p, tl) for p in JUNK_TITLE_PATTERNS)


def _low_signal(title: str, user_msgs: list[str]) -> bool:
    if _is_junk_title(title):
        return True
    if len(user_msgs) < 2:
        return True
    if sum(len(m) for m in user_msgs) < 100:
        return True
    tl = title.lower() if title else ""
    return any(h in tl for h in JUNK_HINTS)


def _extract_linear(conv: dict) -> list[dict]:
    mapping = conv.get("mapping") or {}
    current = conv.get("current_node")
    chain = []
    if current and current in mapping:
        node_id = current
        while node_id:
            node = mapping.get(node_id) or {}
            msg = node.get("message") or {}
            if msg:
                author = (msg.get("author") or {}).get("role")
                parts = (msg.get("content") or {}).get("parts") or []
                text = "\n".join(p for p in parts if isinstance(p, str)).strip()
                ts = msg.get("create_time") or 0
                if author and text and author in ("user", "assistant"):
                    chain.append({"role": author, "content": text, "ts": ts})
            node_id = node.get("parent")
        chain.reverse()
    return chain


EXTRACT_PROMPT = """Ты помогаешь Владимиру построить «второй мозг» — память обо всём, что для него важно. Это не бизнес-база, а карта его жизни, мыслей, отношений и людей.

Тебе дают краткое содержание одного диалога с ChatGPT. Реши, стоит ли его сохранять, и если да — извлеки суть.

СОХРАНЯЙ ШИРОКО (не только бизнес):
- решения, выводы, принципы, ценности Владимира
- проекты и бизнес (AURA.BEYOND, «Золотая миля» и др.)
- людей и отношения с ними — романтические, дружеские, рабочие, семейные
- эмоциональное состояние, саморефлексию, внутренние конфликты, личный рост
- мировоззрение (трансерфинг и пр.), то как он принимает решения и мыслит
- здоровье, семью, личные истории и эпизоды

НЕ сохраняй: разовые переводы, generic Q&A без личного следа, технические дебаг-сессии без долгосрочной важности, разовые стихи/шутки.

ВАЖНО: не суди о людях через деловую линзу. Если человек — романтический интерес, друг, родственник, сотрудник — так и помечай. НЕ называй человека «клиентом», если из контекста это не очевидно. В поле people указывай имя И кто это для Владимира.

Summary пиши в ПРАВИЛЬНОЙ рамке: личное — как личное, рабочее — как рабочее, семейное — как семейное. Не превращай личную историю в бизнес-кейс.

Ответь STRICT JSON без markdown:
{"keep": true|false, "reason": "1 предложение",
 "category": "decision|project|person|relationship|principle|self_reflection|emotion|family|technical|junk",
 "summary": "2-4 предложения квинтэссенция в правильной рамке",
 "facts": ["факт1", ...],
 "people": ["Имя — кто это для Владимира (роль)", ...],
 "topics": ["topic", ...]}"""


def _call_extractor(client: OpenAI, title: str, user_msgs: list[str], ts: float) -> dict:
    snippet = "\n---\n".join(m[:500] for m in user_msgs[:15])
    dt = time.strftime("%Y-%m-%d", time.localtime(ts))
    payload = f"Заголовок: {title}\nДата: {dt}\n\nПервые сообщения Владимира:\n{snippet}"
    resp = client.chat.completions.create(
        model="openai/gpt-4o-mini",
        messages=[{"role": "system", "content": EXTRACT_PROMPT}, {"role": "user", "content": payload}],
        temperature=0.2,
        response_format={"type": "json_object"},
    )
    return json.loads(resp.choices[0].message.content)


# ---------- Скачивание архива ----------


def _download_archive(progress: Callable[[str], None] | None = None) -> None:
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    url = os.environ.get(ARCHIVE_URL_ENV, DEFAULT_ARCHIVE_URL)
    if list(EXPORT_DIR.glob("conversations-*.json")):
        if progress:
            progress(f"Архив уже распакован в {EXPORT_DIR}")
        return
    if progress:
        progress(f"Качаю архив с {url} …")
    archive = DATA_DIR / "chatgpt_archive.tar.gz"
    urllib.request.urlretrieve(url, archive)
    size_mb = archive.stat().st_size / 1024 / 1024
    if progress:
        progress(f"Скачано {size_mb:.0f} MB, распаковываю …")
    with tarfile.open(archive, "r:gz") as tar:
        tar.extractall(EXPORT_DIR)
    archive.unlink(missing_ok=True)
    if progress:
        files = sorted(EXPORT_DIR.glob("conversations-*.json"))
        progress(f"Готово, JSON-файлов: {len(files)}")


# ---------- Chroma напрямую (без mem0) ----------


def _make_collection():
    """Chroma persistent collection с sentence-transformers embedder.

    Та же collection и embedder, что читает chatgpt_memory.py — поэтому
    запись и чтение полностью совместимы.
    """
    import chromadb
    from chromadb.utils import embedding_functions

    CHROMA_DIR.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    embedder = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name=EMBED_MODEL
    )
    return client.get_or_create_collection(
        name=COLLECTION_NAME,
        embedding_function=embedder,
    )


def _clean_meta(meta: dict) -> dict:
    """Chroma-метаданные принимают только str/int/float/bool. None → ''."""
    out: dict[str, Any] = {}
    for k, v in meta.items():
        if v is None:
            out[k] = ""
        elif isinstance(v, bool) or isinstance(v, (str, int, float)):
            out[k] = v
        else:
            out[k] = str(v)
    return out


# ---------- Main pipeline ----------


async def index_chatgpt(progress: Callable[[str], None] | None = None) -> str:
    """Полный pipeline индексации. Возвращает финальную сводку.
    progress(msg) — callback для апдейтов в Telegram (опционально).
    """
    _download_archive(progress)

    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        return "ERROR: OPENROUTER_API_KEY не задан"
    client = OpenAI(api_key=api_key, base_url="https://openrouter.ai/api/v1")

    files = sorted(EXPORT_DIR.glob("conversations-*.json"))
    if not files:
        return "ERROR: нет conversations-*.json после распаковки"

    all_convs: list[dict] = []
    for f in files:
        with open(f) as fp:
            all_convs.extend(json.load(fp))
    all_convs.sort(key=lambda c: c.get("create_time") or 0, reverse=True)
    if progress:
        progress(f"Всего диалогов в архиве: {len(all_convs)}")

    if progress:
        progress("Поднимаю Chroma + загружаю embedding-модель (может занять минуту)…")
    collection = _make_collection()

    stats = {"total": 0, "filtered_heuristics": 0, "filtered_llm": 0, "kept": 0, "errors": 0}
    by_cat: dict[str, int] = {}

    update_every = max(20, len(all_convs) // 25)
    for i, conv in enumerate(all_convs):
        stats["total"] += 1
        msgs = _extract_linear(conv)
        user_msgs = [m["content"] for m in msgs if m["role"] == "user"]
        title = conv.get("title") or "New chat"
        ts = conv.get("create_time") or 0
        cid = conv.get("id") or conv.get("conversation_id") or f"conv{i}"

        if _low_signal(title, user_msgs):
            stats["filtered_heuristics"] += 1
        else:
            try:
                ext = _call_extractor(client, title, user_msgs, ts)
            except Exception as e:
                stats["errors"] += 1
                logger.warning(f"extractor err on {title!r}: {e}")
                if progress and i % update_every == 0:
                    progress(f"[{i}/{len(all_convs)}] kept={stats['kept']} err={stats['errors']}")
                continue
            if not ext.get("keep"):
                stats["filtered_llm"] += 1
            else:
                stats["kept"] += 1
                cat = ext.get("category", "unknown")
                by_cat[cat] = by_cat.get(cat, 0) + 1
                meta = {
                    "source": "chatgpt_export",
                    "conv_id": cid,
                    "conv_url": f"https://chatgpt.com/c/{cid}",
                    "title": title,
                    "create_time": float(ts) if ts else 0.0,
                    "category": cat,
                    "topics": ",".join(ext.get("topics") or []),
                    "people": ",".join(ext.get("people") or []),
                }

                docs: list[str] = []
                metas: list[dict] = []
                ids: list[str] = []

                summary = (ext.get("summary") or "").strip()
                if summary:
                    docs.append(summary)
                    metas.append(_clean_meta(meta))
                    ids.append(f"{cid}-summary-{i}")

                for fi, fact in enumerate((ext.get("facts") or [])[:5]):
                    fact = (fact or "").strip()
                    if not fact:
                        continue
                    docs.append(fact)
                    metas.append(_clean_meta({**meta, "is_fact": True}))
                    ids.append(f"{cid}-fact-{i}-{fi}")

                if docs:
                    try:
                        # upsert — идемпотентно, повторный /index_chatgpt не падает
                        collection.upsert(documents=docs, metadatas=metas, ids=ids)
                    except Exception as e:
                        stats["errors"] += 1
                        logger.warning(f"chroma upsert err: {e}")

        if progress and i % update_every == 0 and i:
            progress(
                f"[{i}/{len(all_convs)}] kept={stats['kept']} "
                f"skip_heur={stats['filtered_heuristics']} skip_llm={stats['filtered_llm']}"
            )

    try:
        total_vectors = collection.count()
    except Exception:
        total_vectors = -1

    summary_lines = [f"Импорт завершён. Всего диалогов: {stats['total']}"]
    for k, v in stats.items():
        if k != "total":
            summary_lines.append(f"  {k}: {v}")
    summary_lines.append(f"Векторов в Chroma: {total_vectors}")
    summary_lines.append("По категориям:")
    for k, v in sorted(by_cat.items(), key=lambda x: -x[1]):
        summary_lines.append(f"  {k}: {v}")
    return "\n".join(summary_lines)
