"""Business advisor toolkit — outreach, research, meeting prep, call summarization,
competitive briefs, strategic briefs. Each tool spawns a focused sub-LLM call with
a specialized system prompt encoding the methodology and deliverable structure.

Each tool returns a finished, ready-to-use deliverable (not just a template), so
the parent Friman can either pass it through, lightly edit, or comment on it.
Sub-LLM runs on Sonnet by default — these are non-trivial tasks where quality
matters more than latency.
"""

from __future__ import annotations

from loguru import logger

from src.brain.claude_client import make_client


async def _run_subllm(
    system: str,
    user: str,
    tier: str = "sonnet",
    max_tokens: int = 1500,
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
        logger.exception("business tool sub-llm failed")
        return f"(внутренняя ошибка тула: {type(e).__name__}: {e})"
    return (resp.choices[0].message.content or "").strip()


# ─── draft_outreach ──────────────────────────────────────────────────────────

_OUTREACH_SYSTEM = """Ты — мастер B2B/B2C outreach. Пишешь сообщения которые открывают,
а не помечаются как спам. Принципы (строго):

1. ЗАХОД (1 строка): конкретный наблюдаемый факт про адресата — недавний релиз/пост/
   интервью/изменение в команде/конкретная цифра. Не «увидел ваш профиль», не «нашёл
   вашу компанию». Если конкретики в input нет — оставь явный плейсхолдер
   «[вставь конкретный факт: ...]» вместо выдумок.
2. БОЛЬ или ВОЗМОЖНОСТЬ (1-2 строки): зеркаль их конкретную ситуацию. Не «вы наверно
   сталкиваетесь» — а «вы недавно вышли на рынок Y, наверняка фокус на Z».
3. VALUE-PROP (1 строка, без жаргона): что мы делаем и почему это релевантно ИМ.
   Не «leveraging cutting-edge AI», не «синергия», не «оптимизировать процессы». А
   конкретный результат: «подняли конверсию в чате до 12%», «собрали продукт за три
   недели», «закрыли поток подписок».
4. SOFT CTA (1 строка): не «давайте созвонимся 30 мин» — а маленький шаг: «ответьте
   одной строкой — это ваш приоритет или нет», «гляньте 1-страничник», «можно
   прислать 3 кейса под вас».
5. Никаких «hope this finds you well», «I would love to», «let me know if interested».
   Никакого пафоса, никакой воды.
6. Длина: cold = 4-6 строк, follow-up = 6-10. Краткость > вежливость.
7. Подпись не нужна — пользователь сам подпишет.
8. Без emoji кроме случая tone='playful' (тогда максимум 1).

Выдай ТОЛЬКО финальный текст сообщения. Без преамбулы, без объяснений, без
комментариев типа «вот ваш draft»."""


async def draft_outreach(
    channel: str,
    recipient: str,
    goal: str,
    tone: str = "warm",
    history: str = "",
) -> str:
    """Draft an outreach message (cold or follow-up).

    channel: email | linkedin | whatsapp | telegram | sms
    recipient: who they are + observable context (role, recent activity, company)
    goal: what we want them to do (reply, agree to call, look at the deck, etc.)
    tone: warm | direct | playful | formal
    history: prior exchange — provide if this is a follow-up, not a cold."""
    user_prompt = (
        f"Канал: {channel}\n"
        f"Адресат (кто и контекст): {recipient}\n"
        f"Цель сообщения: {goal}\n"
        f"Тон: {tone}\n"
    )
    if history.strip():
        user_prompt += f"\nИстория переписки:\n{history.strip()}\n"
    return await _run_subllm(_OUTREACH_SYSTEM, user_prompt, max_tokens=600)


# ─── research_company ───────────────────────────────────────────────────────

_RESEARCH_SYSTEM = """Ты — сильный business-researcher. Тебе дают название компании
или URL и сырые выдержки с веба. Собираешь действенный бриф для бизнес-решения.

Структура (строго в этом порядке, заголовки тоже строго):

—— Компания ——
2-3 строки: что делают, в каком сегменте, давно ли на рынке.

—— Продукт/Услуга ——
Конкретно что продают, как ценят, чем отличаются. Главные SKU/тарифы/услуги.

—— Клиенты ——
Кого обслуживают (ICP), есть ли публично известные кейсы, ключевые сегменты.

—— Деньги и команда ——
Выручка/инвестиции если публично, размер команды, ключевые люди (CEO/founders/CTO),
недавние раунды/сделки/M&A.

—— Текущие приоритеты и сигналы ——
Что они недавно запустили/нанимают/говорят в публичке. Свежие новости (последние
3-6 месяцев). Что это говорит об их фокусе.

—— Хуки для нас ——
3 буллета: конкретные точки контакта/боли/возможности под нашу позицию. Не «они
наверно нуждаются в...» — а «вот их ситуация и вот где мы цепляемся».

Стиль: плотный, без воды. Если данных нет — пиши «публично не нашёл» вместо
выдумок. НИКОГДА не выдумывай факты — если у тебя нет источника в данных, скажи
об этом.

Никакого markdown с # заголовками. Текст уйдёт в Telegram. Только разделители
«—— Раздел ——» и обычный текст под ними."""


async def research_company(
    name_or_url: str,
    focus: str = "",
    web_excerpts: str = "",
) -> str:
    """Build a structured business research brief for a company.

    name_or_url: company name or website URL
    focus: specific angle (e.g., 'partnership lead' or 'evaluating as competitor')
    web_excerpts: aggregated text from web_fetch calls (homepage, about, news,
                  LinkedIn). If empty, returns a fetch-plan instead of a brief —
                  the assistant should then call web_fetch on the suggested URLs
                  and re-invoke this tool with the excerpts."""
    if not web_excerpts.strip():
        plan = (
            f"—— План ресёрча на «{name_or_url}» ——\n\n"
            f"Чтобы собрать нормальный бриф, нужны выдержки из:\n\n"
            f"1. Главная страница сайта компании (что они делают, для кого)\n"
            f"2. Страница About / Команда (founders, CEO, размер)\n"
            f"3. Pricing / Services (если публично)\n"
            f"4. Свежие новости — Crunchbase, vc.ru, The Bell, RB.ru (зависит от рынка)\n"
            f"5. LinkedIn-страница компании (размер команды, недавние нанятия)\n\n"
            f"Дёрни web_fetch по этим URL, собери основной текст в один параметр "
            f"`web_excerpts` и вызови меня снова — я тогда сложу бриф."
        )
        if focus.strip():
            plan += f"\n\nОсобый фокус: {focus.strip()}"
        return plan

    user_prompt = (
        f"Компания: {name_or_url}\n"
        f"Особый фокус: {focus.strip() or '(общий ресёрч)'}\n\n"
        f"Сырые данные с веба (выдержки):\n\n{web_excerpts}\n"
    )
    return await _run_subllm(_RESEARCH_SYSTEM, user_prompt, max_tokens=2000)


# ─── prep_meeting ───────────────────────────────────────────────────────────

_PREP_SYSTEM = """Ты — операционный консильери Владимира. Готовишь его к встрече/звонку
так, чтобы он зашёл подготовленным, контролировал темп и закрыл свою цель.

Структура брифа (строго эти разделы, разделители «—— Раздел ——»):

—— Цель этой встречи ——
1-2 строки: чего конкретно нужно добиться. Не «обсудить», а «договориться о X /
получить Y / прояснить Z». Если цель размытая в input — задай явный уточняющий
вопрос в конце брифа.

—— Участники: что важно про каждого ——
По строке на человека: должность, что от него зависит, как принимает решения, что
для него важно. Если про кого-то неизвестно — пометь «(уточнить у Владимира)».

—— План разговора ——
5-7 пунктов тактически. Каждый пункт: тема + цель пункта + первая фраза/вопрос
которой Владимир открывает. В порядке прохождения.

—— 3 главных вопроса ——
Три вопроса, на которые нужны их ответы. Точные формулировки, не «узнать про X».

—— Аргументы и контраргументы ——
- Если они скажут X, ответ: ...
- Если они скажут Y, ответ: ...
- Если они начнут торговаться — план Z.

—— Что отдать им (после) ——
Что Владимир обещает прислать после встречи (one-pager, кейсы, цены). Это его
крюк для второго касания.

—— Красные флаги ——
2-3 вещи на которые обращать внимание во время разговора (тон, кто молчит, кто
тянет). Если заметит — что это значит и как реагировать.

Стиль: коротко, директивно. Никакой общей водички вроде «будьте уверены в себе»."""


async def prep_meeting(
    context: str,
    attendees: str,
    goal: str,
    timing: str = "",
) -> str:
    """Build a tactical pre-meeting brief.

    context: what's this meeting about, prior history with these people
    attendees: who's coming, their roles + what's known about each
    goal: what Vladimir wants out of this
    timing: optional — when and how long"""
    user_prompt = (
        f"Контекст встречи: {context}\n"
        f"Участники: {attendees}\n"
        f"Цель Владимира на встречу: {goal}\n"
    )
    if timing.strip():
        user_prompt += f"Когда / длительность: {timing.strip()}\n"
    return await _run_subllm(_PREP_SYSTEM, user_prompt, max_tokens=1500)


# ─── summarize_call ─────────────────────────────────────────────────────────

_SUMMARY_SYSTEM = """Ты обрабатываешь заметки или транскрипт звонка/встречи. Выдаёшь
короткий полезный конспект, а не пересказ.

Структура (строго эти разделы):

—— О чём говорили ——
3-5 буллетов. Только суть, не реплики. Что было важное.

—— Что решили ——
Конкретные решения, если были. Если не было — пиши «не зафиксировано».

—— Action items ——
Список с владельцем и дедлайном:
- [ ] @имя — что сделать — к когда

Если в заметках не сказано кто отвечает — пометь «@?». Если не сказано дедлайна —
пометь «(срок?)».

—— Открытые вопросы ——
Что осталось висеть. На что нужны ответы от кого.

—— Сигналы ——
Если в разговоре было что-то про настрой, бюджет, конкурентов, риски, политику —
зафиксируй 1-2 строки. Если ничего особого — этот раздел пропусти.

—— Draft follow-up ——
Короткое follow-up письмо (5-7 строк), которое Владимир может отправить после
звонка. Резюме + что мы делаем дальше + soft CTA. Без подписи.

Стиль: телеграфно, без воды. Если транскрипт обрывистый — не додумывай, помечай
«непонятно из заметок»."""


async def summarize_call(notes_or_transcript: str, context: str = "") -> str:
    """Process call notes or transcript into a structured summary + draft follow-up."""
    user_prompt = (
        f"Контекст звонка: {context.strip() or '(не указан)'}\n\n"
        f"Заметки / транскрипт:\n\n{notes_or_transcript}\n"
    )
    return await _run_subllm(_SUMMARY_SYSTEM, user_prompt, max_tokens=2000)


# ─── competitive_brief ──────────────────────────────────────────────────────

_COMPETITIVE_SYSTEM = """Ты делаешь сравнительный бриф между «мы» и «они» (конкурент).
Цель — дать Владимиру внятную позицию: где мы выигрываем, где сливаемся, что
говорить клиенту когда нас сравнивают.

Структура (строго):

—— Что у них хорошо ——
3-4 буллета — реальные сильные стороны конкурента. Не «у них есть продукт», а
конкретно: «у них дешевле на X / у них быстрее onboarding / у них есть мобильное
приложение».

—— Где они слабее нас ——
3-4 буллета — наша асимметрия. Что у нас лучше и почему.

—— Спорные места ——
Где напрямую не сравнить — зависит от сегмента / use-case / бюджета клиента.

—— Что говорить клиенту когда сравнивают ——
Готовые формулировки:
- Если клиент сравнивает по X: «...»
- Если клиент спрашивает «почему вы дороже»: «...»
- Если клиент уже у них и думает переходить: «...»

—— Стратегические выводы ——
2-3 пункта — что это значит для нас. Например: «надо подтянуть Y / нужно агрессивнее
бить по Z-сегменту / нужно сделать кейс показывающий ROI выше».

Стиль: честно, без понтов и без самоумаления. Если конкретики в input мало —
помечай «нужна доп. инфа про X» прямо в брифе."""


async def competitive_brief(us: str, them: str, focus: str = "") -> str:
    """Build a battlecard comparing us vs a competitor.

    us: brief description of our offering / positioning
    them: brief description of the competitor + what's known about them
    focus: optional angle — 'pricing battle', 'enterprise vs SMB', specific RFP"""
    user_prompt = (
        f"МЫ: {us}\n\n"
        f"ОНИ (конкурент): {them}\n\n"
        f"Особый фокус: {focus.strip() or '(общий бриф)'}\n"
    )
    return await _run_subllm(_COMPETITIVE_SYSTEM, user_prompt, max_tokens=1800)


# ─── business_brief ─────────────────────────────────────────────────────────

_BUSINESS_SYSTEM = """Ты — стратегический спарринг-партнёр Владимира. На входе — тема
бизнес-решения. На выходе — короткий, плотный, готовый к чтению decision-document.

Возможные форматы (выбери по `format` параметру, если он задан явно):

— decision_memo — один документ: рекомендация + аргументы + риски. 6-10 строк.
— options_compare — несколько вариантов в таблице (markdown) с критериями.
— one_pager — обзор темы для inform-собеседника. До одного экрана.
— swot — Strengths/Weaknesses/Opportunities/Threats по конкретной теме.
— pricing — анализ ценообразования: модель + сравнение + рекомендация.
— unit_economics — раскладка экономики юнита (доход, COGS, маржа, LTV/CAC).
— diagnose — диагностика проблемы (симптом → возможные корни → как проверить).

Если `format` пустой или «auto» — выбери уместный сам по теме и пометь выбор первой
строкой ответа: «Формат: <выбранный>».

Стиль: жёстко, без хедж-слов («возможно», «вероятно», «следует рассмотреть»). Прямые
выводы. Если данных мало — скажи «недостаточно данных для X, нужно узнать Y».

Никогда не выдавай советы по типу «обратитесь к юристу / бухгалтеру / финконсультанту».
Владимир сам решает, нужен ли ему профессионал. Дай его лучшее видение по теме.

Никакого markdown с # заголовками. Текст в Telegram. Только разделители
«—— Раздел ——» и (если формат это predполагает) markdown-таблицы."""


async def business_brief(
    topic: str,
    format: str = "auto",
    context: str = "",
) -> str:
    """Build a strategic business document.

    topic: the question or decision
    format: auto | decision_memo | options_compare | one_pager | swot | pricing |
            unit_economics | diagnose
    context: relevant data, constraints, prior thinking"""
    user_prompt = (
        f"Тема: {topic}\n"
        f"Формат вывода: {format}\n"
    )
    if context.strip():
        user_prompt += f"\nКонтекст и данные:\n{context.strip()}\n"
    return await _run_subllm(_BUSINESS_SYSTEM, user_prompt, max_tokens=2500)
