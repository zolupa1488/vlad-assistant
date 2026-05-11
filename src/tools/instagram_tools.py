"""Instagram / SMM operator toolkit for Vladimir's AURA studio.

Six tools that build production-grade SMM artefacts (posts, reels, hooks,
captions, calendars, audits) tuned to Vladimir's brand. Each tool spawns a
focused sub-LLM call (Sonnet by default) with an embedded AURA knowledge
base context — the sub-LLM sees brand positioning, audiences, products,
the visual-success formula, what-hits/what-fails, presentation rules, and
messaging rules directly inside its system prompt. So the output isn't
generic SMM — it's AURA-grade.

Tools:
  - instagram_post_pack — комплект под пост: hook x3, основной текст, CTA, хэштеги, сторис-идеи
  - reels_script — сценарий Reels с pacing по секундам
  - hook_bank — банк зацепов под тему
  - caption_for_artwork — caption под конкретную работу
  - content_calendar — план постов на месяц
  - insta_audit — разбор метрик Instagram
"""

from __future__ import annotations

import json
from typing import Any

from loguru import logger

from src.brain.claude_client import make_client
from src.tools.aura_kb_tool import _load_kb


# ─── helpers ────────────────────────────────────────────────────────────────


async def _run_subllm(
    system: str,
    user: str,
    tier: str = "sonnet",
    max_tokens: int = 2000,
) -> str:
    """Run one focused sub-LLM call. Returns the assistant content (stripped)."""
    client = make_client()
    try:
        resp = await client.chat_complete(
            tier=tier,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            max_tokens=max_tokens,
        )
    except Exception as e:
        logger.exception("instagram tool sub-llm failed")
        return f"(внутренняя ошибка тула: {type(e).__name__}: {e})"
    return (resp.choices[0].message.content or "").strip()


def _aura_context_for_smm() -> str:
    """Bundle the AURA brand context needed for all SMM tools into one block.

    Pulls: brand, audiences, products, visual_success_formula, what_hits,
    presentation_rules, messaging_rules. Returns formatted Russian-prose
    block ready to embed in a system prompt."""
    try:
        kb = _load_kb()
    except Exception:
        return "(AURA knowledge base недоступна — работаем по общим SMM-правилам)"

    parts: list[str] = []

    brand = kb.get("brand", {})
    if brand:
        positioning = brand.get("positioning", {}).get("core", "")
        geo = brand.get("geography", {}).get("implemented_projects", [])
        entities = [e.get("value", "") for e in brand.get("entities", [])]
        parts.append(
            "БРЕНД: "
            + ", ".join(entities)
            + ". "
            + positioning
            + (f" Проекты: {', '.join(geo)}." if geo else "")
        )

    audiences = kb.get("audiences", [])
    if audiences:
        segs = [a.get("segment", "") for a in audiences]
        parts.append("АУДИТОРИИ: " + ", ".join(segs) + ".")

    products = kb.get("products", {})
    if products:
        lines = products.get("lines", [])
        anchors = products.get("offer_anchors", [])
        anchor_strs = [
            f"{a.get('product','')} от €{a.get('price_from_eur')}"
            for a in anchors
            if a.get("price_from_eur")
        ]
        parts.append(
            "ПРОДУКТ: "
            + ", ".join(lines)
            + ". "
            + ("Якоря: " + "; ".join(anchor_strs) + "." if anchor_strs else "")
        )

    vsf = kb.get("visual_success_formula", {})
    if vsf:
        parts.append(
            "ФОРМУЛА ЗАЛЁТА: "
            + vsf.get("formula", "")
            + "\nABCD-фильтр: "
            + json.dumps(vsf.get("abcd_filter", {}), ensure_ascii=False)
            + "\nШТРАФЫ (избегать): "
            + ", ".join(vsf.get("penalties", []))
        )

    wh = kb.get("what_hits", {})
    if wh:
        succ = wh.get("successful_symbols", [])
        fails = wh.get("failures", [])
        parts.append(
            "ЧТО ЗАЛЕТАЕТ: " + ", ".join(succ) + ".\n"
            "ЧТО ФЕЙЛИТСЯ: " + ", ".join(fails) + "."
        )

    pr = kb.get("presentation_rules", {})
    if pr:
        base = pr.get("base", [])
        cat = pr.get("catalog_constraints", [])
        parts.append(
            "ПРАВИЛА ПОДАЧИ: " + ", ".join(base) + ".\n"
            "КАТАЛОГ: " + ", ".join(cat) + "."
        )

    mr = kb.get("messaging_rules", {})
    if mr:
        style = mr.get("style", [])
        strong = mr.get("strong_phrases", [])
        avoid = mr.get("avoid", [])
        parts.append(
            "TONE СООБЩЕНИЙ: " + ", ".join(style) + ".\n"
            "СИЛЬНЫЕ ФРАЗЫ: " + "; ".join(strong) + ".\n"
            "ИЗБЕГАТЬ: " + ", ".join(avoid) + "."
        )

    return "\n\n".join(parts)


_BASE_TONE = """ОБЩИЕ ПРИНЦИПЫ ВСЕГО SMM-КОНТЕНТА AURA:

- Никакой воды, никакого канцелярита, никаких «погружения в мир искусства».
- НЕ писать «вдохновение», «уникальный», «эксклюзивный», «истинное произведение».
- Конкретика > эпитет. «Барельеф 130×130 см» > «крупный барельеф».
- Тон спокойный, статусный, как разговор знающего с равным. Не продаём — приглашаем.
- AURA не делает «декор», AURA делает АРХИТЕКТУРУ пространства. Это про статус, не про красивость.
- Хэштеги — в конце поста, отдельным абзацем, через пробел.
- Эмодзи — только если уместно для сторис; в основных постах почти всегда без.
"""


# ─── instagram_post_pack ────────────────────────────────────────────────────


_POST_PACK_SYSTEM_TMPL = """Ты — SMM-стратег AURA.BEYOND. Делаешь пакет под публикацию в
Instagram: 3 hook-варианта, основной текст, CTA, хэштеги, идеи под сторис.

{aura}

{tone}

ФОРМАТ ОТВЕТА — строго разделители «—— Раздел ——», без markdown # заголовков:

—— Hook (3 варианта) ——
H1: [версия с эго-сигналом]
H2: [версия с провокацией / контр-интуитивная]
H3: [версия с конкретикой / фактом]

Каждый — одна строка до 80 символов, читается за 1.5 секунды.

—— Основной текст ——
3-5 коротких абзацев. По нашей формуле залёта: знак → архетип → желание владеть.
Без воды. Закончи естественно, без громких выводов.

—— CTA ——
Одна строка. Не «пишите в Direct» абстрактно — конкретная следующая просьба
(«пришли размеры комнаты — соберём визуализацию», «есть стена 2×3 — какой
барельеф подойдёт?», «нужен номер серии — отвечу с фото в наличии»).

—— Хэштеги ——
Один блок, через пробел. 10-15 штук:
- 3-4 крупных evergreen (#interiordesign #contemporaryart #wallart)
- 3-4 средних под нишу (#russianart #handmadepainting #bareliefart)
- 3-4 узких/локальных под наш сегмент (#luxuryinterior #moscowdesign #parisart)

Если тема про конкретную серию (Георгий, Матрёшки, Москва, Богатыри, цветы) —
добавь 1-2 специфичных под неё.

—— Идеи под сторис (3 кадра) ——
S1: [процессный кадр + текст]
S2: [деталь / макро + вопрос аудитории]
S3: [результат / финал + CTA в DM]

ЕСЛИ в input указана конкретная серия — опирайся на её сильные стороны из what_hits.
ЕСЛИ серия не указана — не выдумывай, делай универсальный пост."""


async def instagram_post_pack(
    topic: str,
    series: str = "",
    format: str = "carousel",
) -> str:
    """Generate a full Instagram post pack: 3 hooks, body, CTA, hashtags, story ideas.

    topic: тема поста (новая работа / процесс / мысль про бренд / факт)
    series: AURA series this is for (Георгий, Матрёшки, Москва, Богатыри, цветы, барельеф) — опционально
    format: carousel / single / reels-cover — по умолчанию carousel"""
    system = _POST_PACK_SYSTEM_TMPL.format(
        aura=_aura_context_for_smm(), tone=_BASE_TONE
    )
    user = (
        f"Тема поста: {topic}\n"
        f"Серия: {series or '(не указана — универсальный пост)'}\n"
        f"Формат: {format}\n"
    )
    return await _run_subllm(system, user, max_tokens=2500)


# ─── reels_script ───────────────────────────────────────────────────────────


_REELS_SYSTEM_TMPL = """Ты — режиссёр Reels для AURA. Делаешь сценарий с pacing
по секундам — для съёмки и монтажа.

{aura}

{tone}

ПРИНЦИПЫ REELS:
- Hook за 1.5 секунды (визуальный + словесный одновременно). Если зритель не понял в 1.5с — он листает.
- Retention loop: на 30%, 60%, 90% длительности — что-то меняется (новый ракурс / реплика / звук), чтобы держать.
- Без водных вступлений «привет», «сегодня я расскажу», «итак».
- Текст на экране — крупно, читается за 1с, не больше 8 слов в строке.
- CTA в самом конце последние 1-2 секунды, нативно вплетён.
- Aspect 9:16, music: deep house / cinematic instrumental / silence + voiceover.

ФОРМАТ ОТВЕТА — таблица по секундам:

—— Сценарий ({duration}с) ——

| Сек | Визуал | Звук/Реплика | Текст на экране |
|-----|--------|--------------|------------------|
| 0-1.5 | ... | ... | ... |
| 1.5-3 | ... | ... | ... |
...

—— Hook-механика ——
Одной строкой: какой паттерн hook'a, почему сработает на нашей аудитории.

—— CTA финал ——
Точно как звучит / выглядит на последних секундах.

—— Caption под Reels ——
4-6 строк. Не дублирует то что говорят в видео — расширяет.
"""


async def reels_script(idea: str, duration_sec: int = 15) -> str:
    """Generate a Reels script with second-by-second pacing.

    idea: что показываем (новая работа, процесс, бэкстейдж, мысль)
    duration_sec: длительность 7 / 15 / 30 / 60. По умолчанию 15."""
    system = _REELS_SYSTEM_TMPL.format(
        aura=_aura_context_for_smm(),
        tone=_BASE_TONE,
        duration=duration_sec,
    )
    user = f"Идея Reels: {idea}\nДлительность: {duration_sec}с\n"
    return await _run_subllm(system, user, max_tokens=2000)


# ─── hook_bank ──────────────────────────────────────────────────────────────


_HOOK_BANK_SYSTEM_TMPL = """Ты — копирайтер Reels/постов AURA. На входе тема, на
выходе банк зацепов (открывающих строк) разными паттернами.

{aura}

{tone}

ПАТТЕРНЫ HOOK (для каждого один вариант):

1. ВОПРОС-ЛОВУШКА — провокационный вопрос с парадоксом («Почему миллионеры
   вешают над диваном Георгия, а не Моне?»)
2. КОНТР-ИНТУИТИВНЫЙ — переворачивает ожидание («Картина за €5000 — это дёшево.
   И вот почему.»)
3. СТАТУС-СИГНАЛ — апеллирует к группе («Если ты не повесил это над диваном —
   ты ещё не в этой лиге.»)
4. КОНКРЕТНЫЙ ФАКТ — число / результат («31 проданная Георгий. Каждая в
   мужских кабинетах от Москвы до Парижа.»)
5. ИНСАЙД — раскрывает кухню («Вот что мы убираем перед тем как фото уходит
   в каталог.»)
6. ПЕРЕНОС — связывает с известным мемом / понятным образом («Айфон в кармане,
   Георгий на стене. Один язык.»)
7. ВЫЗОВ — приглашает к спору («Большинство интерьеров скучные. Знаете
   почему?»)
8. PoV — от лица покупателя («Ты заходишь в квартиру. Первое что видишь —
   эта картина. Что ты подумал?»)
9. ИСТОРИЯ (хук-крючок) — начало мини-нарратива («Этот клиент думал что
   купит картину. Не знал что меняет свою стену навсегда.»)
10. ПРЯМОЙ ОФФЕР — без лирики, в лоб («Барельеф 130×130 см. €4500. В
    наличии. Кому?»)

ПРАВИЛА:
- Каждый hook ≤ 80 символов.
- Должен читаться за 1.5 секунды.
- Не выдумывай факты — если число / имя / событие не задано в input или
  не из AURA-контекста, не вставляй.
- Помечай каждый паттерном (1-10 выше) — пользователю понятнее какой брать.

ФОРМАТ:
—— Hook bank (n={n}) ——
H1 [Паттерн X]: ...
H2 [Паттерн Y]: ...
..."""


async def hook_bank(topic: str, n: int = 10) -> str:
    """Generate a bank of hook lines for a topic, each using a different pattern.

    topic: тема для которой нужны hook'и
    n: сколько hook'ов выдать (3-10), по умолчанию 10"""
    n = max(3, min(n, 10))
    system = _HOOK_BANK_SYSTEM_TMPL.format(
        aura=_aura_context_for_smm(), tone=_BASE_TONE, n=n
    )
    user = f"Тема: {topic}\nКоличество hook'ов: {n}\n"
    return await _run_subllm(system, user, max_tokens=1500)


# ─── caption_for_artwork ────────────────────────────────────────────────────


_CAPTION_SYSTEM_TMPL = """Ты пишешь caption под фото конкретной работы AURA.
Caption должен звучать как голос Владимира — спокойно, статусно, без поэзии
про вдохновение и без школьных эпитетов.

{aura}

{tone}

ДЛИНА И СТРУКТУРА:
- 3-6 строк, максимум 7.
- Первая строка — самостоятельный hook, читается без контекста.
- Дальше: 1-2 строки про работу (символ / архетип / что в ней «бьёт»).
- Опционально: 1 строка про материал / технику (без хвастовства, как факт).
- Финал: мягкий CTA («есть стена под это», «отвечу с размерами»,
  «можем сделать в другом масштабе») — или закрытая мысль если CTA не
  уместен.

ФАЙЛЫ КОТОРЫЕ НЕЛЬЗЯ ПРОИЗВОДИТЬ:
- «истинное искусство», «истинный шедевр», «вдохновение из глубин»
- «эксклюзивная авторская работа», «уникальный артефакт»
- «погружение в мир искусства»
- «современное прочтение классики» (банальность)
- «откройте для себя» (продажная клише)

ФОРМАТ ОТВЕТА:
Только caption, без преамбулы, без объяснений. Готовый текст для копи-паста."""


async def caption_for_artwork(
    artwork_description: str,
    mood: str = "neutral",
    series: str = "",
) -> str:
    """Generate a caption for a specific AURA artwork photo.

    artwork_description: что на фото — символ, размер, материал, особенности
    mood: neutral / storytelling / direct-sale / process
    series: серия если ясна (Георгий, Матрёшки, цветы, барельеф итд)"""
    system = _CAPTION_SYSTEM_TMPL.format(
        aura=_aura_context_for_smm(), tone=_BASE_TONE
    )
    user = (
        f"Описание работы: {artwork_description}\n"
        f"Тональность: {mood}\n"
        f"Серия: {series or '(не указана)'}\n"
    )
    return await _run_subllm(system, user, max_tokens=600)


# ─── content_calendar ───────────────────────────────────────────────────────


_CALENDAR_SYSTEM_TMPL = """Ты строишь контент-план на месяц для AURA Instagram.
Распределяешь типы постов так, чтобы держать стабильный «floor» внимания и
оставлять окна под виралы.

{aura}

ТИПЫ ПОСТОВ (сбалансированный микс):
- PROMO (35%) — новая работа / серия / оффер с CTA. Прямая продажа.
- PROCESS (20%) — бэкстейдж, как делается, материалы, кухня студии.
- STATEMENT (15%) — мысль про искусство, интерьер, статус. Голос бренда.
- CASE (15%) — реализованный проект в интерьере клиента, до/после.
- SERIES_SPOTLIGHT (10%) — глубокое погружение в одну серию (Георгий,
  Матрёшки итд). Архетип, история, кому подойдёт.
- COMMUNITY (5%) — Q&A, репост клиента, обсуждение тренда. Не каждую неделю.

ПРАВИЛА РИТМА:
- Не более 2 PROMO подряд.
- Понедельник / пятница — лучший день для PROMO (повышенный охват).
- Среда — STATEMENT или SERIES_SPOTLIGHT (вдумчивая аудитория в середине недели).
- Воскресенье — CASE или COMMUNITY (атмосферные дни).
- Reels (формат) распределяй равномерно, ≥1 в неделю, ≤2.

ФОРМАТ ВЫВОДА — markdown таблица:

—— Контент-план на {month}, {n_posts} постов ——

| День | Дата | Тип | Тема | Серия / фокус | Формат | Hook-набросок |
|------|------|-----|------|----------------|--------|----------------|
| пн | 1 | PROMO | новая работа из серии X | Георгий | carousel | «31 продана. Кто 32-й?» |
...

—— Распределение по типам ——
PROMO: X / N (X%)
PROCESS: Y / N (Y%)
...

—— Hook-приоритеты ——
Какие 3-4 hook-паттерна стоит протестировать в этом месяце и почему.

—— Что замерять ——
Какие 2-3 метрики смотрим к концу месяца, чтобы понять что зашло."""


async def content_calendar(
    month: str,
    n_posts: int = 20,
    focus: str = "",
) -> str:
    """Build a month-long Instagram content calendar.

    month: «май 2026», «декабрь», «next 30 days» — что писать в заголовке
    n_posts: сколько постов в месяце (12-30), по умолчанию 20 (~5/неделю)
    focus: особый акцент (например 'продвижение серии Матрёшки' или
           'старт продаж в Дубае' или 'подготовка к Art Basel')"""
    n_posts = max(8, min(n_posts, 30))
    system = _CALENDAR_SYSTEM_TMPL.format(
        aura=_aura_context_for_smm(), month=month, n_posts=n_posts
    )
    user = (
        f"Месяц: {month}\n"
        f"Количество постов: {n_posts}\n"
        f"Особый фокус: {focus or '(нет, обычный микс)'}\n"
    )
    return await _run_subllm(system, user, max_tokens=4000)


# ─── insta_audit ────────────────────────────────────────────────────────────


_AUDIT_SYSTEM_TMPL = """Ты разбираешь метрики Instagram-аккаунта AURA как
аналитик который понимает контекст бизнеса. На входе — текст с цифрами
(вставленный из Insights, описанный руками, или вытащенный из скриншота).

{aura}

ТВОЯ ЛОГИКА АНАЛИЗА (по эвристикам AURA):

CORE — среднее число просмотров постом со стороны подписчиков. Это «ядро
внимания». Если core просел — проблема не в одном посте, а в общем
интересе аудитории. Если core стабилен — фундамент здоров, можно
экспериментировать сверху.

VIRAL POST — >70-75% просмотров от неподписанных + заметный охват +
сильный engagement. Это «залёт». Анализируем что было особенного:
символ, hook, формат, время.

FLOOR — нижний устойчивый уровень выручки, не разовые виралы. Формула:
core × money_density (плотность денег на единицу внимания). Цель —
растить floor, не гнаться за разовыми выстрелами.

ШТРАФЫ В КОНТЕНТЕ (искать в подаче):
- банальность
- буквальная религиозность без приёма
- generic-люкс без идеи
- слабый знак / нет узнаваемости за 3 сек

ФОРМАТ АНАЛИЗА:

—— Что вижу в цифрах ——
3-4 буллета сухими цифрами и наблюдениями. БЕЗ интерпретации.

—— Что значит ——
2-3 строки расшифровки. Где аномалии, на что обратить внимание.

—— Что зашло (виралы / залёты) ——
Если в данных есть посты с явно выше среднего — разбор почему. Если
данных нет — пиши «недостаточно данных для разбора виралов, нужны
посты с метриками».

—— Где течёт ——
Просадки / провалы / штрафы. Конкретно — какой пост, что не так.

—— Что чинить первым ——
3 действия в приоритете. Каждое — конкретное (не «улучшить контент»,
а «протестировать hook'и через провокацию вместо вопроса», «выкатить
серию SPOTLIGHT по Матрёшкам»).

—— Эксперименты на следующую неделю ——
2-3 гипотезы что протестировать."""


async def insta_audit(metrics_or_text: str, context: str = "") -> str:
    """Analyze Instagram metrics with AURA-specific heuristics.

    metrics_or_text: цифры/описание/выдержка из Insights. Может быть
                     неструктурированным текстом.
    context: дополнительный контекст (период, цели, что недавно
             меняли в стратегии)"""
    system = _AUDIT_SYSTEM_TMPL.format(aura=_aura_context_for_smm())
    user = (
        f"Метрики / данные:\n\n{metrics_or_text}\n"
    )
    if context.strip():
        user += f"\nКонтекст: {context.strip()}\n"
    return await _run_subllm(system, user, max_tokens=2500)
