# Progress

## Current state (2026-07-16)

Working macOS app, installed at `/Applications/Voice to Text.app`. Latest fixes merged to `main` via [PR #1](https://github.com/timwyse/voice_to_text/pull/1) (2026-07-16).

## Done

- Core app: record via button/Enter, transcribe via Whisper API with automatic local (faster-whisper) fallback, editable transcript area, Copy All
- Settings dialog (Cmd+,): local model size/device/precision/language, noise filter, API key, polish prompt; model-download confirmation; reset to defaults
- macOS packaging: PyInstaller bundle, ad-hoc signing, `build.sh` installs to /Applications; mic permission; first-launch API key prompt
- mac keybindings in text areas (Cmd+Backspace / Cmd+Delete)
- LLM transcript polishing with Original/Polished tabs and customisable prompt
- API price auto-check (asks gpt-4o-mini weekly, cached in `price_cache.json`) with warn/block thresholds
- 2026-07-16 (PR #1):
  - Fixed polish endpoint — was pointing at `aicohort.org` with a fake model, never worked; now official OpenAI API, `gpt-5-mini` + `reasoning_effort="minimal"`, same key as transcription (OpenRouter key field removed)
  - Fixed polish inventing text (transcript wrapped in `<transcript>` tags + stricter default prompt, with auto-upgrade of saved prompts)
  - Whisper API timeout 5s → 60s (long recordings were silently falling back to local)
  - Cancel button + Esc: discard recording, abandon transcription, or stop polishing
  - Crash fixes: empty recording (`np.concatenate([])`), `None` polish response content

## Open items

- Revoke the old OpenRouter key (was being sent to `aicohort.org`) and figure out how that endpoint got into commit a03a12c
- API price check asks an LLM for pricing — unreliable; consider a hardcoded constant
- `gh` CLI not installed (PRs created via REST API with git credentials)
- From `human_todos.md`: discuss system requirements / failure modes; clean up repo of unused files
