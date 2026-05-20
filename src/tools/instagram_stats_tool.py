"""instagram_stats tool — live Instagram account stats via Composio.

Pulls real numbers from the Instagram Graph API (profile + account-level
insights) through the Composio connection. This is the live-data counterpart
to insta_audit, which only interprets numbers the user pastes in.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from src.integrations import composio as cmp

# period name → number of days back
_PERIODS: dict[str, int] = {
    "today": 1,
    "day": 1,
    "сегодня": 1,
    "week": 7,
    "неделя": 7,
    "month": 30,
    "месяц": 30,
}

# account-level insight metrics to request; any that come back empty are skipped
_METRICS = ["reach", "views", "accounts_engaged", "total_interactions"]

_METRIC_LABELS = {
    "reach": "Охват",
    "views": "Просмотры",
    "accounts_engaged": "Вовлечённых аккаунтов",
    "total_interactions": "Взаимодействий",
}

_PERIOD_LABELS = {1: "за сегодня", 7: "за 7 дней", 30: "за 30 дней"}


def _fmt(n) -> str:
    try:
        return f"{int(n):,}".replace(",", " ")
    except (TypeError, ValueError):
        return str(n)


def _metric_total(m: dict):
    """A metric's value: total_value if present, otherwise sum of daily values."""
    tv = m.get("total_value")
    if isinstance(tv, dict):
        if tv.get("value") is not None:
            return tv["value"]
    elif isinstance(tv, (int, float)):
        return tv
    vals = m.get("values")
    if isinstance(vals, list) and vals:
        total = 0
        got = False
        for v in vals:
            x = v.get("value") if isinstance(v, dict) else None
            if isinstance(x, (int, float)):
                total += x
                got = True
        if got:
            return total
    return None


async def instagram_stats(period: str = "week") -> str:
    """Return a readable summary of Instagram account stats for the period.

    period: today / week / month (default week).
    """
    days = _PERIODS.get((period or "week").strip().lower(), 7)
    now = datetime.now(timezone.utc)
    since = (now - timedelta(days=days)).strftime("%Y-%m-%d")
    until = now.strftime("%Y-%m-%d")

    try:
        info = await cmp.execute("INSTAGRAM_GET_USER_INFO", {"ig_user_id": "me"})
    except Exception as e:
        return f"Не получилось получить данные Instagram: {type(e).__name__}: {e}"

    try:
        insights = await cmp.execute(
            "INSTAGRAM_GET_USER_INSIGHTS",
            {
                "ig_user_id": "me",
                "metric": _METRICS,
                "period": "day",
                "since": since,
                "until": until,
            },
        )
    except Exception as e:
        insights = {"_error": f"{type(e).__name__}: {e}"}

    username = info.get("username") or "—"
    lines: list[str] = [
        f"Instagram @{username} — статистика {_PERIOD_LABELS.get(days, f'за {days} дн.')}",
        "",
    ]
    if info.get("followers_count") is not None:
        lines.append(f"Подписчики: {_fmt(info['followers_count'])}")
    if info.get("media_count") is not None:
        lines.append(f"Публикаций всего: {_fmt(info['media_count'])}")
    lines.append("")

    rows = insights.get("data") if isinstance(insights, dict) else None
    shown = 0
    if isinstance(rows, list):
        for m in rows:
            if not isinstance(m, dict):
                continue
            val = _metric_total(m)
            if val is not None:
                label = _METRIC_LABELS.get(m.get("name"), m.get("name"))
                lines.append(f"{label}: {_fmt(val)}")
                shown += 1
    if shown == 0:
        if isinstance(insights, dict) and insights.get("_error"):
            lines.append(f"(метрики за период недоступны: {insights['_error']})")
        else:
            lines.append("(метрики за период Instagram не вернул)")

    return "\n".join(lines)
