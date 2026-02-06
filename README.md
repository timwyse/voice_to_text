# Voice to Text

A macOS desktop app for speech-to-text transcription. Supports both OpenAI's Whisper API (fast, requires internet and API credits) and local transcription using faster-whisper (offline, private, free).

## Features

- **Dual transcription modes**: Switch between API and local transcription with one click
- **Local transcription**: Uses [faster-whisper](https://github.com/guillaumekln/faster-whisper) for offline, private transcription
- **Background noise filtering**: VAD (Voice Activity Detection) filters out typing, background noise, and non-speech audio. Available only in local mode.
- **Multiple model sizes**: Choose from tiny, base, small, medium, or large-v3 based on your speed/accuracy needs
- **15 language support**: English, Spanish, French, German, Italian, Portuguese, Dutch, Polish, Russian, Chinese, Japanese, Korean, Arabic, Hindi, plus auto-detection
- **Keyboard-driven**: Press Enter to start/stop recording
- **Automatic fallback**: Falls back to local transcription when API is unavailable

## How It Works

1. Press **Record** (or hit **Enter**) to start recording
2. Speak into your microphone
3. Press **Stop** (or hit **Enter** again) to finish
4. The app transcribes your audio and displays the text
5. Click **Copy All** to copy the transcription to your clipboard

**API mode** sends audio to OpenAI's Whisper API for transcription. It's fast but requires an internet connection and API key.

**Local mode** runs the faster-whisper model on your machine. The first transcription downloads the model (~500MB for "small"). Subsequent transcriptions are instant. Your audio never leaves your device.

## Installation

### Option 1: Build the App (Recommended)

```bash
# Clone the repository
git clone https://github.com/timwyse/vtt.git
cd vtt

# Create and activate virtual environment
python3 -m venv vttenv
source vttenv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Build and install the app
./build.sh
```

The app will be installed to `/Applications/Voice to Text.app`. You can open it from Finder, Spotlight, or drag it to your Dock.

### Option 2: Run from Source

```bash
# Clone and set up
git clone https://github.com/YOUR_USERNAME/vtt.git
cd vtt
python3 -m venv vttenv
source vttenv/bin/activate
pip install -r requirements.txt

# Run the app
python app.py
```

## Requirements

- **macOS** 10.15 (Catalina) or later
- **Python** 3.9+
- **Microphone access** (the app will request permission on first launch)

### Python Dependencies

- `PyQt6` - GUI framework
- `faster-whisper` - Local transcription engine
- `openai` - OpenAI API client
- `sounddevice` - Audio recording
- `soundfile` - Audio file handling
- `python-dotenv` - Environment variable management
- `numpy` - Numerical operations
- `pyinstaller` - App bundling

## Configuration

Open **Settings** via the menu bar (`Cmd + ,`) or `Voice to Text > Settings`.

### Local Transcription Settings

| Setting | Options | Description |
|---------|---------|-------------|
| Model size | tiny, base, small, medium, large-v3 | Larger = more accurate but slower. "small" is a good balance. |
| Device | cpu, auto | CPU works everywhere. Auto uses GPU if available. |
| Precision | int8, float16, float32 | Lower precision is faster. int8 recommended. |
| Language | 15 languages + auto-detect | Select the language being spoken. |
| Filter background noise | On/Off | Uses VAD to filter non-speech audio. Recommended. |

### API Settings

Enter your OpenAI API key to enable API transcription mode. Get one at [platform.openai.com](https://platform.openai.com/api-keys).

## Data Storage

The app stores user data in `~/Library/Application Support/VoiceToText/`:

| File | Purpose |
|------|---------|
| `settings.json` | Your transcription settings |
| `.env` | Your OpenAI API key |
| `price_cache.json` | Cached API pricing info |

Whisper models are cached in `~/.cache/huggingface/hub/`.

## Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| `Enter` | Start/stop recording (when text area not focused) |
| `Escape` | Unfocus text area |
| `Cmd + ,` | Open Settings |
| `Cmd + W` | Close window |

## Troubleshooting

**"No API key set"** - Enter your OpenAI API key in Settings, or use Local mode.

**Model download taking long** - The first local transcription downloads the model. "small" is ~500MB. Larger models take longer.

**Microphone permission denied** - Go to System Preferences > Privacy & Security > Microphone and enable access for Voice to Text.

**Transcription quality poor** - Try a larger model size, or enable "Filter background noise" in Settings.

## License

MIT License
