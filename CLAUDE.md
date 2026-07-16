# CLAUDE.md

macOS desktop app (PyQt6) for speech-to-text: record with one button/Enter key, transcribe via OpenAI Whisper API with local faster-whisper fallback, optionally polish the transcript with an LLM.

**Check `PROGRESS.md` at the start of a session** for current state and open items, and update it when you complete meaningful work, discover new open items, or find it stale (e.g. a listed PR has since merged). Don't log minor tweaks.

## Commands

```bash
source vttenv/bin/activate     # project virtualenv (Python 3.13)
python app.py                  # run from source (menu bar works in script mode)
./build.sh                     # PyInstaller build, sign, install to /Applications
python -m py_compile app.py transcriber.py settings.py   # quick syntax check
```

There is no test suite. Verify changes by running `python app.py`.

## Architecture

- `app.py` — all UI: main window (`VTTApp`), settings dialog, background `QThread` workers for transcription and polishing
- `transcriber.py` — recording (`Recorder`), transcription (API + local fallback logic in `transcribe_audio`), API price checking/caching
- `settings.py` — `Settings` class (JSON persistence), constants, default polish prompt
- `voicetotext.spec` / `build.sh` — PyInstaller packaging

## Git workflow

PRs in this repo get merged quickly, often while a session is still working. **Before pushing to a branch that has a PR, check the PR is still open** — commits pushed after a merge land on the dead branch and appear in no PR. If it has merged, start a fresh branch from `origin/main` and cherry-pick.

## Key facts

- User data lives in `~/Library/Application Support/VoiceToText/`: `settings.json`, `.env` (holds `OPENAI_API_KEY`), `price_cache.json`
- One OpenAI key covers both transcription (`whisper-1`) and polishing (`gpt-5-mini`, `reasoning_effort="minimal"`)
- The polish transcript is wrapped in `<transcript>` tags and the prompt forbids inventing/completing text — keep it that way; the model will otherwise treat speech as instructions
- If you change `DEFAULT_POLISH_PROMPT`, add the old value to `_OLD_POLISH_PROMPTS` in `settings.py` so saved settings auto-upgrade
- Local whisper models cache in `~/.cache/huggingface/hub/`; the loaded model is cached in-process and must be cleared via `clear_cached_model()` when model settings change
- Workers subclass `QThread` and shadow the built-in `finished` signal with a custom one — don't rely on `QThread.finished`
