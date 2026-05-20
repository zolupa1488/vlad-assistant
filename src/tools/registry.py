"""Tool registry — JSON schemas + dispatcher + file-collection."""

from __future__ import annotations

import json
from contextvars import ContextVar
from typing import Any, Awaitable, Callable

from loguru import logger

from src.tools.aura_kb_tool import aura_kb
from src.tools.chatgpt_memory import recall_chain, recall_decision, recall_history
from src.tools.business_tools import (
    business_brief,
    competitive_brief,
    draft_outreach,
    prep_meeting,
    research_company,
    summarize_call,
)
from src.tools.instagram_tools import (
    caption_for_artwork,
    content_calendar,
    hook_bank,
    insta_audit,
    instagram_post_pack,
    reels_script,
)
from src.tools.instagram_stats_tool import instagram_stats
from src.tools.figma_tool import (
    figma_export_image,
    figma_get_comments,
    figma_get_file,
)
from src.tools.google_sheets_tool import (
    create_google_sheet,
    find_google_sheet,
    list_google_sheet_tabs,
    read_google_sheet,
    write_google_sheet,
)
from src.tools.image_gen import generate_image
from src.tools.mac_bridge_tool import mac_bridge_run
from src.tools.memory_tools import (
    clear_focus,
    forget,
    recall,
    remember,
    set_active_sheet,
    set_active_spreadsheet,
    set_focus,
)
from src.tools.model_tools import escalate_to_sonnet, whoami_model
from src.tools.skills_tools import (
    generate_chart,
    generate_docx,
    generate_pdf,
    generate_pptx,
)
from src.tools.web_fetch import web_fetch

# --- File side-channel ---------------------------------------------------
_files_for_turn: ContextVar[list[dict[str, Any]] | None] = ContextVar(
    "files_for_turn", default=None
)


def reset_file_collector() -> list[dict[str, Any]]:
    files: list[dict[str, Any]] = []
    _files_for_turn.set(files)
    return files


def collect_files() -> list[dict[str, Any]]:
    files = _files_for_turn.get()
    return files if files is not None else []


# -------------------------------------------------------------------------

TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "web_fetch",
            "description": "Fetch the readable text content of a public URL.",
            "parameters": {
                "type": "object",
                "properties": {"url": {"type": "string"}},
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_google_sheet",
            "description": (
                "Search Vladimir's Google Drive for spreadsheets whose name contains `query`. "
                "Returns up to 8 matches. Pass empty string to list recent sheets."
            ),
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_google_sheet_tabs",
            "description": (
                "List all sheets/tabs inside a spreadsheet (titles, indexes, sizes). "
                "ALWAYS call this right after set_active_spreadsheet before read_google_sheet, "
                "so you know which tab to read instead of guessing."
            ),
            "parameters": {
                "type": "object",
                "properties": {"spreadsheet_id": {"type": "string"}},
                "required": ["spreadsheet_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_google_sheet",
            "description": (
                "Read a range from a spreadsheet (TSV, capped at 100 rows). "
                "If the spreadsheet has multiple sheets, ALWAYS prefix the range with "
                "the sheet name in single quotes: \"'Заказы 2026'!A1:Z200\". "
                "Without the sheet prefix, Google reads the first tab — which may not "
                "be the one you need."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "spreadsheet_id": {"type": "string"},
                    "range": {
                        "type": "string",
                        "description": (
                            "A1 with sheet prefix, e.g. \"'Заказы 2026'!A1:Z200\". "
                            "Default: 'A1:Z200' on the first tab."
                        ),
                    },
                },
                "required": ["spreadsheet_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_google_sheet",
            "description": "Write a 2D block of values into a spreadsheet range.",
            "parameters": {
                "type": "object",
                "properties": {
                    "spreadsheet_id": {"type": "string"},
                    "range": {"type": "string"},
                    "values_csv": {"type": "string"},
                },
                "required": ["spreadsheet_id", "range", "values_csv"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_google_sheet",
            "description": "Create a new spreadsheet in Vladimir's Drive.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "headers_csv": {"type": "string"},
                },
                "required": ["title"],
            },
        },
    },
    # ── Session state / memory ──────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "set_active_spreadsheet",
            "description": (
                "Pin a spreadsheet as the current focus. Call this right after "
                "find_google_sheet when you've identified the right table — then "
                "you don't have to keep asking which one."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "spreadsheet_id": {"type": "string"},
                    "title": {"type": "string"},
                },
                "required": ["spreadsheet_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_active_sheet",
            "description": "Pin which sheet/tab inside the active spreadsheet is in focus.",
            "parameters": {
                "type": "object",
                "properties": {"sheet_name": {"type": "string"}},
                "required": ["sheet_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_focus",
            "description": "Pin free-form note about the current focus of the conversation.",
            "parameters": {
                "type": "object",
                "properties": {"topic": {"type": "string"}},
                "required": ["topic"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "clear_focus",
            "description": "Drop all session focus pins (active spreadsheet/sheet/topic).",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "remember",
            "description": (
                "Pin a fact in long-term memory. Call when the user shares something "
                "durable — names of partners, recurring rules, project meanings. "
                "Don't pin transient stuff like 'today I'm tired'."
            ),
            "parameters": {
                "type": "object",
                "properties": {"fact": {"type": "string"}},
                "required": ["fact"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "recall",
            "description": (
                "Search Vladimir's pinned facts. Pass a keyword/substring or "
                "omit `query` to get 10 most recent."
            ),
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "forget",
            "description": "Delete pinned facts that match the query.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        },
    },
    # ── Generators ─────────────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "generate_pptx",
            "description": (
                "Build a clean .pptx presentation. Output goes to the user as a Telegram file. "
                "`slides_json`: JSON array of {title, bullets[]} or {title, body}."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "subtitle": {"type": "string"},
                    "slides_json": {"type": "string"},
                },
                "required": ["title", "slides_json"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_docx",
            "description": (
                "Build a clean .docx file. `sections_json`: JSON array of "
                "{heading, paragraphs[], bullets[]}."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "sections_json": {"type": "string"},
                },
                "required": ["title", "sections_json"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_pdf",
            "description": "Build a clean PDF (sections like generate_docx + optional `table`).",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "sections_json": {"type": "string"},
                },
                "required": ["title", "sections_json"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "mac_bridge_run",
            "description": (
                "Delegate a task to Vladimir's Mac, which runs Claude Code with MCP "
                "servers (Figma, Canva, file-system, etc). Use for: working with "
                "Figma designs, Canva mockups, building static websites, anything that "
                "needs Vladimir's local environment. The task should be a clear, "
                "self-contained instruction in plain Russian or English. The Mac must "
                "be awake — if asleep or tunnel down, returns an error."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "task": {
                        "type": "string",
                        "description": "Self-contained instruction for Claude Code on the Mac.",
                    },
                },
                "required": ["task"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_chart",
            "description": "Render a single PNG chart (bar/line/pie).",
            "parameters": {
                "type": "object",
                "properties": {
                    "chart_type": {"type": "string", "enum": ["bar", "line", "pie"]},
                    "title": {"type": "string"},
                    "labels_csv": {"type": "string"},
                    "values_csv": {"type": "string"},
                    "y_label": {"type": "string"},
                },
                "required": ["chart_type", "title", "labels_csv", "values_csv"],
            },
        },
    },
    # ── Image generation (nano-banana via OpenRouter) ──────────────
    {
        "type": "function",
        "function": {
            "name": "generate_image",
            "description": (
                "Generate a PNG image from a text prompt using Gemini 2.5 Flash "
                "Image (nano-banana) via OpenRouter. Prompt in English works best. "
                "The image is shipped to Telegram as a photo automatically."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "prompt": {
                        "type": "string",
                        "description": "What to generate, ideally in English.",
                    }
                },
                "required": ["prompt"],
            },
        },
    },
    # ── Figma read + render via REST API ──────────────────────────
    {
        "type": "function",
        "function": {
            "name": "figma_get_file",
            "description": (
                "Read top-level structure of a Figma file: pages and their "
                "frames with node_ids. Pass a full Figma URL or just the file_key. "
                "Use the node_ids from this output with figma_export_image."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "url_or_key": {
                        "type": "string",
                        "description": "Figma URL or bare file_key",
                    }
                },
                "required": ["url_or_key"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "figma_export_image",
            "description": (
                "Export a Figma node (frame/component/group) as image and ship "
                "it to Telegram. Get the node_id from figma_get_file first."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "url_or_key": {"type": "string"},
                    "node_id": {"type": "string"},
                    "format": {
                        "type": "string",
                        "enum": ["png", "jpg", "svg", "pdf"],
                    },
                    "scale": {
                        "type": "number",
                        "description": "Render scale, default 2.0 for retina-quality PNG.",
                    },
                },
                "required": ["url_or_key", "node_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "figma_get_comments",
            "description": "Read comments left on a Figma file.",
            "parameters": {
                "type": "object",
                "properties": {"url_or_key": {"type": "string"}},
                "required": ["url_or_key"],
            },
        },
    },
    # ── AURA knowledge base ───────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "aura_kb",
            "description": (
                "Прочитать секцию из базы знаний бизнеса Владимира (студия AURA.BEYOND "
                "/ AURA.objcts — картины, панно, барельефы для интерьеров). Содержит: "
                "позиционирование, аудитории, продуктовые линии, ценовые якоря (EUR/RUB), "
                "формулу залёта (visual_success_formula), правила подачи, что-залетает / "
                "что-фейлится, sales-данные серий (Георгий, цветы и тд), структуру "
                "себестоимости, финансы воронок (leads/cold calls), эвристики аналитики, "
                "маркетинг RF/EU, правила сообщений, prompting-стек NanoBanana, "
                "операционку, цели расширения, глоссарий. "
                "ВЫЗЫВАЙ когда Владимир спрашивает что-то о бизнесе, продуктах, ценах, "
                "клиентах, картинах, серии, методологии или просит сгенерировать что-то "
                "под этот контекст (oфферы, тексты, описания). Не выдумывай сам — "
                "доставай из базы. Section: list/all или конкретное имя секции."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "section": {
                        "type": "string",
                        "description": (
                            "Секция: brand, audiences, products, visual_success_formula, "
                            "presentation_rules, what_hits, series_sales, pricing, "
                            "cost_structure, financials, analytics_heuristics, marketing, "
                            "messaging_rules, prompting_stack, ops, expansion, glossary. "
                            "Или 'all' (полная база) или 'list' (показать список секций)."
                        ),
                    }
                },
            },
        },
    },
    # ── Instagram / SMM operator pack ─────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "instagram_post_pack",
            "description": (
                "Полный пакет под публикацию в Instagram: 3 hook-варианта, основной "
                "текст, CTA, набор хэштегов, идеи под сторис. Уже знает бренд AURA, "
                "tone, formula залёта — не выдумывает. ВЫЗЫВАЙ когда «напиши пост», "
                "«сделай пост про X», «нужен пост для серии», «помоги с публикацией»."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "topic": {
                        "type": "string",
                        "description": "Тема поста (новая работа, процесс, мысль, факт)",
                    },
                    "series": {
                        "type": "string",
                        "description": "Серия если есть: Георгий / Матрёшки / Москва / Богатыри / цветы / барельеф. Опционально.",
                    },
                    "format": {
                        "type": "string",
                        "description": "carousel / single / reels-cover. Default carousel.",
                    },
                },
                "required": ["topic"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "reels_script",
            "description": (
                "Сценарий Reels с pacing по секундам — таблица «секунда / визуал / "
                "звук / текст на экране» + hook-механика + CTA + caption. ВЫЗЫВАЙ "
                "когда «сценарий Reels», «помоги снять видео», «нужен рилс про X»."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "idea": {
                        "type": "string",
                        "description": "Идея видео (что показываем)",
                    },
                    "duration_sec": {
                        "type": "integer",
                        "description": "Длительность: 7, 15, 30 или 60. Default 15.",
                    },
                },
                "required": ["idea"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "hook_bank",
            "description": (
                "Банк зацепов под тему — 3-10 разных hook-паттернов (вопрос-ловушка, "
                "контр-интуитивный, статус-сигнал, конкретный факт, инсайд и тд). "
                "ВЫЗЫВАЙ когда «придумай заходы», «нужны hook'и», «варианты "
                "открывающих строк», «как зацепить внимание про X»."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "topic": {
                        "type": "string",
                        "description": "Тема для которой нужны hook'и",
                    },
                    "n": {
                        "type": "integer",
                        "description": "Сколько hook'ов (3-10). Default 10.",
                    },
                },
                "required": ["topic"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "caption_for_artwork",
            "description": (
                "Caption под фото конкретной работы AURA — короткий (3-6 строк), "
                "в нашем tone, без поэзии про вдохновение. ВЫЗЫВАЙ когда «напиши "
                "подпись к этой картине / работе», «caption для нового барельефа»."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "artwork_description": {
                        "type": "string",
                        "description": "Описание работы: символ, размер, материал, особенности",
                    },
                    "mood": {
                        "type": "string",
                        "description": "neutral / storytelling / direct-sale / process. Default neutral.",
                    },
                    "series": {
                        "type": "string",
                        "description": "Серия если ясна. Опционально.",
                    },
                },
                "required": ["artwork_description"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "content_calendar",
            "description": (
                "Контент-план на месяц для Instagram: распределяет посты по типам "
                "(PROMO/PROCESS/STATEMENT/CASE/SERIES_SPOTLIGHT/COMMUNITY), даёт "
                "тему и hook-набросок для каждого, советует что замерять. ВЫЗЫВАЙ "
                "когда «составь план на месяц», «контент-план», «что постить в X»."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "month": {
                        "type": "string",
                        "description": "Заголовок периода: «май 2026», «next 30 days»",
                    },
                    "n_posts": {
                        "type": "integer",
                        "description": "Количество постов в месяце (8-30). Default 20.",
                    },
                    "focus": {
                        "type": "string",
                        "description": "Особый акцент (продвижение серии X, старт продаж в Y). Опционально.",
                    },
                },
                "required": ["month"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "insta_audit",
            "description": (
                "Разбор метрик Instagram по эвристикам AURA (core/floor/виралы/"
                "money_density). На входе текст с цифрами (вставленный из Insights, "
                "описанный руками, выдержка из скриншота). Выдаёт: что вижу — что "
                "значит — что зашло — где течёт — что чинить — эксперименты на "
                "неделю. ВЫЗЫВАЙ когда «проанализируй Instagram», «вот цифры за "
                "месяц», «разбери метрики», «почему просел охват»."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "metrics_or_text": {
                        "type": "string",
                        "description": "Метрики / выдержка / описание цифр",
                    },
                    "context": {
                        "type": "string",
                        "description": "Период, цели, что недавно меняли. Опционально.",
                    },
                },
                "required": ["metrics_or_text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "instagram_stats",
            "description": (
                "Живая статистика Instagram-аккаунта AURA (@aura.objcts) — РЕАЛЬНЫЕ "
                "цифры напрямую из Instagram через Composio: подписчики, охват, "
                "просмотры, вовлечённость за период. ВЫЗЫВАЙ когда Владимир "
                "спрашивает «какой охват», «статистика инсты», «сколько подписчиков», "
                "«цифры по инстаграму за неделю/месяц», «как дела в инсте». "
                "НЕ путать с insta_audit — тот разбирает цифры которые дал "
                "пользователь, а этот сам достаёт свежие данные из API. "
                "period: today / week / month."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "period": {
                        "type": "string",
                        "description": "Период выборки: today, week или month. Default week.",
                    },
                },
            },
        },
    },
    # ── Business advisor toolkit ──────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "draft_outreach",
            "description": (
                "Сгенерить outreach-сообщение (cold или follow-up) под канал. "
                "Использовать когда пользователь говорит «напиши письмо/сообщение» "
                "X-у по поводу Y. Возвращает готовый текст сообщения без подписи. "
                "Channel: email/linkedin/whatsapp/telegram/sms. Tone: warm/direct/"
                "playful/formal. Для follow-up передавай `history` с предыдущей "
                "перепиской."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "channel": {
                        "type": "string",
                        "description": "Канал: email, linkedin, whatsapp, telegram, sms",
                    },
                    "recipient": {
                        "type": "string",
                        "description": "Кто адресат + контекст (роль, компания, недавние действия)",
                    },
                    "goal": {
                        "type": "string",
                        "description": "Чего хотим от адресата (ответ, согласие на звонок, посмотреть кейсы)",
                    },
                    "tone": {
                        "type": "string",
                        "description": "Тон сообщения: warm, direct, playful, formal. Default warm.",
                    },
                    "history": {
                        "type": "string",
                        "description": "Предыдущая переписка (если follow-up). Опционально.",
                    },
                },
                "required": ["channel", "recipient", "goal"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "research_company",
            "description": (
                "Собрать структурированный бизнес-бриф на компанию (продукт, клиенты, "
                "деньги, команда, сигналы, хуки для нас). Двухфазный: если не передан "
                "`web_excerpts` — возвращает план каких URL нужно дёрнуть через web_fetch. "
                "Когда соберёшь выдержки — вызови повторно с web_excerpts, получишь "
                "финальный бриф. Если поверхностного ответа достаточно, можешь не "
                "ходить за выдержками."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name_or_url": {
                        "type": "string",
                        "description": "Название компании или URL сайта",
                    },
                    "focus": {
                        "type": "string",
                        "description": "Особый угол: 'looking for partnership', 'evaluating as competitor', etc.",
                    },
                    "web_excerpts": {
                        "type": "string",
                        "description": "Сырой текст с веба (объединённые web_fetch результаты). Если пусто — вернётся план.",
                    },
                },
                "required": ["name_or_url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "prep_meeting",
            "description": (
                "Подготовить Владимира к встрече/звонку. Выдаёт цель встречи, "
                "что важно про участников, план разговора (5-7 пунктов), 3 главных "
                "вопроса, аргументы и контраргументы, что отдать после, красные флаги. "
                "Используй когда «подготовь меня к», «как зайти в разговор с», "
                "«что спросить у»."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "context": {
                        "type": "string",
                        "description": "О чём встреча, история отношений",
                    },
                    "attendees": {
                        "type": "string",
                        "description": "Кто придёт, их роли, что известно про каждого",
                    },
                    "goal": {
                        "type": "string",
                        "description": "Что Владимиру нужно от этой встречи",
                    },
                    "timing": {
                        "type": "string",
                        "description": "Когда и сколько по времени. Опционально.",
                    },
                },
                "required": ["context", "attendees", "goal"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "summarize_call",
            "description": (
                "Обработать заметки/транскрипт звонка/встречи в структурированный "
                "конспект: о чём говорили, что решили, action items с владельцами и "
                "дедлайнами, открытые вопросы, сигналы, draft follow-up письма. "
                "Используй когда «вот заметки со звонка», «подытожь встречу», "
                "«сделай follow-up по разговору»."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "notes_or_transcript": {
                        "type": "string",
                        "description": "Заметки или транскрипт звонка",
                    },
                    "context": {
                        "type": "string",
                        "description": "С кем и о чём был звонок. Опционально.",
                    },
                },
                "required": ["notes_or_transcript"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "competitive_brief",
            "description": (
                "Сравнительный бриф мы vs конкурент: что у них хорошо, где слабее "
                "нас, спорные места, готовые формулировки для клиента когда сравнивают, "
                "стратегические выводы. Используй когда «сравни нас с X», «как "
                "отвечать клиенту что мы дороже чем Y», «battlecard на конкурента Z»."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "us": {
                        "type": "string",
                        "description": "Кратко мы: что предлагаем, позиционирование",
                    },
                    "them": {
                        "type": "string",
                        "description": "Кратко конкурент + что про них известно",
                    },
                    "focus": {
                        "type": "string",
                        "description": "Особый угол: pricing battle, enterprise vs SMB, specific RFP",
                    },
                },
                "required": ["us", "them"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "business_brief",
            "description": (
                "Стратегический документ по бизнес-вопросу. Форматы: decision_memo "
                "(рекомендация + аргументы + риски), options_compare (таблица вариантов), "
                "one_pager (обзор темы), swot, pricing (анализ цены), unit_economics "
                "(юнит-экономика), diagnose (диагностика проблемы). Используй когда "
                "«помоги выбрать», «какую модель монетизации», «что взять А или Б», "
                "«проанализируй мою юнит-экономику», «диагностируй почему просел Х»."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "topic": {
                        "type": "string",
                        "description": "Что за вопрос / решение",
                    },
                    "format": {
                        "type": "string",
                        "description": "auto | decision_memo | options_compare | one_pager | swot | pricing | unit_economics | diagnose",
                    },
                    "context": {
                        "type": "string",
                        "description": "Данные, ограничения, что уже думали. Опционально.",
                    },
                },
                "required": ["topic"],
            },
        },
    },
    # ── Model-tier controls ───────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "escalate_to_sonnet",
            "description": (
                "ESCALATE TO SONNET 4. Call this when you (running as Haiku 4.5) "
                "feel the task is too complex — long reasoning, nuanced creative "
                "writing, multi-step analysis. The next hop will run on Sonnet 4 "
                "with the same context. Don't overuse — only when you actually "
                "feel stuck or about to produce mediocre output. Pass a brief "
                "reason."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "reason": {
                        "type": "string",
                        "description": "Brief reason in Russian — why this needs Sonnet.",
                    }
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "whoami_model",
            "description": (
                "Return the LLM tier currently powering this turn. Call when the "
                "user asks 'какая модель' / 'на чём ты сейчас отвечаешь'."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
    # ── ChatGPT-архив (второй мозг Vladimir) ────────────────────────
    {
        "type": "function",
        "function": {
            "name": "recall_history",
            "description": (
                "Семантический поиск по архиву ChatGPT-диалогов Vladimir "
                "(509 диалогов с 2023). Возвращает top-N релевантных эпизодов "
                "с заголовком, датой, категорией (decision/project/principle/...) "
                "и темой. ОБЯЗАТЕЛЬНО зови когда вопрос звучит как: "
                "«помнишь мы обсуждали...», «к чему я пришёл насчёт...», "
                "«что я думал про...», «искал ли я инфу про...»."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "n": {
                        "type": "integer",
                        "description": "Сколько результатов вернуть (1-20). По умолчанию 5.",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "recall_chain",
            "description": (
                "Логическая цепочка по теме из ChatGPT-архива — связанные эпизоды "
                "в ХРОНОЛОГИЧЕСКОМ порядке (старые → новые), чтобы видеть как "
                "Vladimir пришёл к выводу/решению. Зови когда вопрос: «как я "
                "пришёл к...», «эволюция моего взгляда на...», «история работы с...»."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "topic": {"type": "string"},
                    "n": {"type": "integer", "description": "Сколько эпизодов (1-30). Default 8."},
                },
                "required": ["topic"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "recall_decision",
            "description": (
                "Точечный поиск решений Vladimir в архиве — отфильтровано по "
                "category=decision. Зови для вопросов «что я решил по...», "
                "«какой выбор сделал насчёт...»."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "topic": {"type": "string"},
                    "n": {"type": "integer", "description": "Сколько решений (1-15). Default 5."},
                },
                "required": ["topic"],
            },
        },
    },
]


_DISPATCH: dict[str, Callable[..., Awaitable[str]]] = {
    "web_fetch": web_fetch,
    "find_google_sheet": find_google_sheet,
    "list_google_sheet_tabs": list_google_sheet_tabs,
    "read_google_sheet": read_google_sheet,
    "write_google_sheet": write_google_sheet,
    "create_google_sheet": create_google_sheet,
    "set_active_spreadsheet": set_active_spreadsheet,
    "set_active_sheet": set_active_sheet,
    "set_focus": set_focus,
    "clear_focus": clear_focus,
    "remember": remember,
    "recall": recall,
    "forget": forget,
    "generate_pptx": generate_pptx,
    "generate_docx": generate_docx,
    "generate_pdf": generate_pdf,
    "generate_chart": generate_chart,
    "generate_image": generate_image,
    "figma_get_file": figma_get_file,
    "figma_export_image": figma_export_image,
    "figma_get_comments": figma_get_comments,
    "mac_bridge_run": mac_bridge_run,
    "aura_kb": aura_kb,
    "instagram_post_pack": instagram_post_pack,
    "reels_script": reels_script,
    "hook_bank": hook_bank,
    "caption_for_artwork": caption_for_artwork,
    "content_calendar": content_calendar,
    "insta_audit": insta_audit,
    "instagram_stats": instagram_stats,
    "draft_outreach": draft_outreach,
    "research_company": research_company,
    "prep_meeting": prep_meeting,
    "summarize_call": summarize_call,
    "competitive_brief": competitive_brief,
    "business_brief": business_brief,
    "escalate_to_sonnet": escalate_to_sonnet,
    "whoami_model": whoami_model,
    "recall_history": recall_history,
    "recall_chain": recall_chain,
    "recall_decision": recall_decision,
}


_FILE_PRODUCING_TOOLS = {
    "generate_pptx",
    "generate_docx",
    "generate_pdf",
    "generate_chart",
    "generate_image",
    "figma_export_image",
}


async def execute_tool(name: str, args_json: str) -> str:
    fn = _DISPATCH.get(name)
    if fn is None:
        return f"unknown tool: {name}"
    try:
        args = json.loads(args_json) if args_json else {}
    except Exception as e:
        return f"invalid arguments JSON: {e}"
    try:
        result = await fn(**args)
    except Exception as e:
        logger.exception("tool {} failed", name)
        return f"error executing {name}: {type(e).__name__}: {e}"

    if name in _FILE_PRODUCING_TOOLS:
        try:
            payload = json.loads(result)
            if isinstance(payload, dict) and payload.get("ok") and payload.get("file_path"):
                collected = _files_for_turn.get()
                if collected is not None:
                    collected.append(
                        {
                            "path": payload["file_path"],
                            "name": payload.get("file_name"),
                            "kind": payload.get("kind"),
                        }
                    )
        except Exception:
            pass

    return result
