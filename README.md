# Vlad Assistant

Personal Telegram AI assistant.

- **Phase I (current):** Telegram Bot via `aiogram` + Bot API. Quick to deploy, no `api_id/api_hash` needed.
- **Phase II (later):** migration to userbot (Telethon, MTProto) — same business logic, only the `TelegramAdapter` implementation swaps.

See [`docs/TZ.md`](docs/TZ.md) for the full spec, architecture, and roadmap.

## Quick start (local)

```bash
cp .env.example .env
# fill TELEGRAM_BOT_TOKEN, OPENROUTER_API_KEY (OWNER_TELEGRAM_USER_ID is pre-filled)
docker compose up --build
```

After it boots, write any message to your bot in Telegram — it should reply with an echo.

## Quick start (Railway)

Railway service `vlad-assistant` is wired to this repo. Push to `main` triggers an auto-deploy. Required env vars (Shared Variables in the Railway project):

- `TELEGRAM_BOT_TOKEN`
- `OPENROUTER_API_KEY`
- `OWNER_TELEGRAM_USER_ID`

## Status

- [x] **Phase 0** — scaffold + echo
- [x] **Phase 1** — Claude tool-use loop (OpenRouter), sliding-window context (SQLite), `web_fetch` tool
- [ ] Phase 2 — Brain (OpenRouter, Claude Opus 4 default)
- [ ] Phase 3 — Memory / RAG (Qdrant + local embeddings)
- [ ] Phase 4 — Stranger script
- [ ] Phase 5 — Google Docs + Instagram Graph API
- [ ] Phase 6 — Outbound actions (`send_message`, digests)
- [ ] Phase 7 — Deploy hardening + observability
- [ ] Phase 8 — Voice (Whisper) + cron digests
- [ ] Phase 9 — Migration to userbot (Telethon)

## Layout

```
src/
  config.py                 # pydantic-settings, env contract
  main.py                   # entry point: wires adapter + handlers
  telegram/
    adapter.py              # TelegramAdapter Protocol
    bot_api_adapter.py      # aiogram-based Phase I implementation
    handlers.py             # on_message logic
docs/
  TZ.md                     # the full spec
```

## Bot identity

- Display name: **Vlad Assistant**
- Username: [@vladimirov_pa_bot](https://t.me/vladimirov_pa_bot)
