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
- [x] **Phase 5 (partial)** — Google Sheets tools: `find_google_sheet`, `read_google_sheet`, `write_google_sheet`, `create_google_sheet` via OAuth
- [x] **Phase 2 (partial)** — local Whisper (faster-whisper, base, int8) for voice messages
- [x] **Phase 6** — local skills: `generate_pptx` / `generate_docx` / `generate_pdf` / `generate_chart`, files shipped as Telegram attachments
- [x] **Phase 7** — incoming file parsing (PDF/DOCX/XLSX/CSV/TXT) + new persona prompt mirrored from Vladimir's communication style profile
- [x] **Phase 7.1** — three-tier memory: session state (active spreadsheet/sheet/focus), pinned facts (`remember`/`recall`/`forget`), 10-msg sliding window. Persona prompt hardened: no markdown, no structural headings.
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
