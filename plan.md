# Voice to Text - Desktop App Plan

## Goal
Simple macOS desktop app for speech-to-text with one-button/key recording.

## Tech Stack
- **PyQt6** for the UI
- **Enter key** to toggle recording (in-app)
- Reuse transcription logic from `transcriber.py`

## File Structure
```
vtt/
├── vtt.py            # CLI tool (imports from transcriber.py)
├── transcriber.py    # Shared recording + transcription logic
├── app.py            # PyQt6 desktop app
├── settings.py       # Settings management (NEW)
├── price_cache.json  # Cached API price + last checked timestamp
├── requirements.txt
├── .env
```

---

## Current: Settings Feature

### Overview
Add a Settings dialog accessible via the macOS menu bar (Voice to Text > Settings or Cmd+,) with configurable transcription options.

### Settings to Include

#### Local Mode (faster-whisper)
| Setting | Options | Default | Notes |
|---------|---------|---------|-------|
| Model size | tiny, base, small, medium, large-v3 | small | Larger = better quality, slower, more RAM |
| Device | cpu, cuda, auto | cpu | cuda only works if NVIDIA GPU + CUDA installed; auto detects |
| Compute type | int8, float16, float32 | int8 | int8 fastest, float32 highest quality |
| Language | en, es, fr, de, zh, ja, auto, ... | en | "auto" lets Whisper detect language |

#### API Mode
- No model choice (OpenAI only offers `whisper-1`)
- **API Key**: Allow updating the key from settings

#### Storage
- Save settings to `~/Library/Application Support/VoiceToText/settings.json`
- Load on app start, apply defaults if missing

### Implementation Steps

#### Step 1: Create settings module (`settings.py`)
- `Settings` class with all configurable values
- `load()` and `save()` methods using JSON
- Default values as class attributes
- Path: `get_data_dir() / "settings.json"`

#### Step 2: Update `transcriber.py`
- `transcribe_locally()` accepts `model_size`, `device`, `compute_type`, `language` parameters
- Pass these through from `transcribe_audio()`

#### Step 3: Create Settings dialog in `app.py`
- QDialog with sections:
  - **Local Transcription**: dropdowns for model size, device, compute type, language
  - **API**: text field for API key (masked)
- Save button applies and persists settings
- Cancel discards changes

#### Step 4: Wire up macOS menu bar in `app.py`
- Create `QMenuBar` with app menu
- Add "Settings..." action with Cmd+, shortcut
- Connect to open Settings dialog

#### Step 5: Apply settings in transcription
- Load settings on app start
- Pass settings values to `transcribe_audio()`
- Clear cached model if local settings changed (lazy-reload on next transcription)

### Testing
Run `python app.py` from terminal to test without rebuilding:
```bash
cd ~/vtt
source vttenv/bin/activate
python app.py
```

The macOS menu bar works in script mode too.

### Decisions
1. **Model downloads**: Prompt user before downloading. When selecting a new model size in settings, check if it's downloaded. If not, show confirmation dialog with estimated size before proceeding.
2. **Reset to Defaults**: Yes, include button in settings dialog.

---

## Completed Features

### UI Layout
```
┌──────────────────────────┐
│       Status label       │
│  [Record] [API/Local ▾]  │
│                          │
│  ┌────────────────────┐  │
│  │ Transcription text │  │
│  │ area (editable)    │  │
│  └────────────────────┘  │
│       [Copy All]         │
└──────────────────────────┘
```

### Keyboard Behaviour
- **Enter**: Toggles recording start/stop (when text area is NOT focused)
- **Esc**: Exits/unfocuses the text area, so Enter works again
- Clicking outside text area also unfocuses it

### Controls
- **Record button**: Click to start (turns red), click to stop
- **API/Local toggle**: Checkable button to switch mode. Disabled while recording.
- **Copy All button**: Copies all text to clipboard

### Automatic Price Checking
- Uses OpenAI gpt-4o-mini to look up current Whisper API price
- Caches in `price_cache.json` with 7-day refresh interval
- Lazy evaluation (only checks on first API transcription per session)

### Packaging
- PyInstaller creates standalone `.app` bundle
- `build.sh` builds, signs, and installs to `/Applications`
- First-launch API key dialog
- Microphone permission declared in Info.plist
- `multiprocessing.freeze_support()` prevents phantom windows
