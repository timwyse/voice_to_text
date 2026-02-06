import sounddevice as sd
import soundfile as sf
import numpy as np
import tempfile
import os
import time
import socket
import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from dotenv import load_dotenv


def get_data_dir():
    """Get the writable data directory for user files."""
    d = Path.home() / "Library" / "Application Support" / "VoiceToText"
    d.mkdir(parents=True, exist_ok=True)
    return d


# Load .env from data dir first, then fall back to project dir
_data_dir = get_data_dir()
_data_env = _data_dir / ".env"
if _data_env.exists():
    load_dotenv(_data_env)
else:
    load_dotenv()

DEFAULT_PRICE = 0.006
PRICE_CACHE_FILE = _data_dir / "price_cache.json"
PRICE_CHECK_INTERVAL_DAYS = 7
WARN_PRICE_PER_MINUTE = float(os.environ.get("WARN_PRICE_PER_MINUTE", 0.01))
BLOCK_PRICE_PER_MINUTE = float(os.environ.get("BLOCK_PRICE_PER_MINUTE", 0.1))

# Cached price — populated lazily on first API transcription
_cached_api_price = None


def _default_status(msg):
    print(msg)


def has_internet():
    """Quick check for internet connectivity."""
    try:
        socket.create_connection(("api.openai.com", 443), timeout=2)
        return True
    except OSError:
        return False


def check_api_available():
    """Check if API mode is available. Returns (available, reason)."""
    if not os.environ.get("OPENAI_API_KEY"):
        return False, "No API key set"
    if not has_internet():
        return False, "No internet connection"
    # Check cached price (don't trigger a new lookup here)
    if _cached_api_price is not None and _cached_api_price >= BLOCK_PRICE_PER_MINUTE:
        return False, f"API price too high (${_cached_api_price:.3f}/min)"
    # Also check file cache
    if PRICE_CACHE_FILE.exists():
        try:
            cache = json.loads(PRICE_CACHE_FILE.read_text())
            price = cache.get("price_per_minute", DEFAULT_PRICE)
            if price >= BLOCK_PRICE_PER_MINUTE:
                return False, f"API price too high (${price:.3f}/min)"
        except (json.JSONDecodeError, KeyError):
            pass
    return True, None


def get_api_price(status=None):
    """Get the Whisper API price, checking via LLM if cache is stale.
    Returns the price and caches it for the session."""
    global _cached_api_price
    if status is None:
        status = _default_status

    if _cached_api_price is not None:
        return _cached_api_price

    # Read existing cache
    cache = None
    if PRICE_CACHE_FILE.exists():
        try:
            cache = json.loads(PRICE_CACHE_FILE.read_text())
        except (json.JSONDecodeError, KeyError):
            cache = None

    # Check if we need to refresh
    needs_refresh = True
    if cache and "last_checked" in cache:
        last_checked = datetime.fromisoformat(cache["last_checked"])
        if datetime.now() - last_checked < timedelta(days=PRICE_CHECK_INTERVAL_DAYS):
            needs_refresh = False

    if not needs_refresh:
        _cached_api_price = cache["price_per_minute"]
        return _cached_api_price

    # Try to look up the current price via LLM
    cached_price = cache["price_per_minute"] if cache else DEFAULT_PRICE
    if not os.environ.get("OPENAI_API_KEY") or not has_internet():
        _cached_api_price = cached_price
        return _cached_api_price

    status("Checking API price (hasn't been checked in a week)...")
    try:
        from openai import OpenAI
        client = OpenAI(timeout=10.0)
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{
                "role": "user",
                "content": (
                    "What is the current OpenAI Whisper API (whisper-1) price "
                    "per minute of audio in USD? Reply with ONLY the numeric "
                    "value, e.g. 0.006"
                ),
            }],
        )
        text = response.choices[0].message.content.strip()
        match = re.search(r"(\d+\.?\d*)", text)
        if match:
            new_price = float(match.group(1))
            if 0.0001 <= new_price <= 1.0:
                cache = {
                    "price_per_minute": new_price,
                    "last_checked": datetime.now().isoformat(),
                }
                PRICE_CACHE_FILE.write_text(json.dumps(cache, indent=2))
                status(f"API price updated: ${new_price}/min")
                _cached_api_price = new_price
                return _cached_api_price

        status(f"Could not parse price from LLM. Using ${cached_price}/min")
    except Exception as e:
        status(f"Price check failed. Using ${cached_price}/min")

    # If lookup failed, update timestamp so we don't retry every launch
    cache = {
        "price_per_minute": cached_price,
        "last_checked": datetime.now().isoformat(),
    }
    PRICE_CACHE_FILE.write_text(json.dumps(cache, indent=2))
    _cached_api_price = cached_price
    return _cached_api_price


class Recorder:
    """Non-blocking audio recorder that can be started/stopped on demand."""

    def __init__(self, sample_rate=16000):
        self.sample_rate = sample_rate
        self.frames = []
        self.recording = False
        self.stream = None
        self.start_time = None

    def _callback(self, indata, frames, time_info, status):
        if self.recording:
            self.frames.append(indata.copy())

    def start(self):
        self.frames = []
        self.recording = True
        self.start_time = time.time()
        self.stream = sd.InputStream(
            samplerate=self.sample_rate, channels=1,
            dtype='float32', callback=self._callback,
        )
        self.stream.start()

    def stop(self):
        self.recording = False
        duration = time.time() - self.start_time
        if self.stream:
            self.stream.stop()
            self.stream.close()
            self.stream = None
        return duration

    def save_to_temp(self):
        """Save recorded audio to a temp file. Caller must delete it."""
        data = np.concatenate(self.frames)
        temp_fd, temp_path = tempfile.mkstemp(suffix='.wav')
        os.close(temp_fd)
        sf.write(temp_path, data, self.sample_rate)
        return temp_path


def transcribe_with_api(audio_path):
    """Transcribe using OpenAI Whisper API."""
    from openai import OpenAI
    client = OpenAI(timeout=5.0)
    with open(audio_path, "rb") as f:
        result = client.audio.transcriptions.create(model="whisper-1", file=f)
    return result.text


# Cache for the local whisper model (avoid reloading on each transcription)
_cached_local_model = None
_cached_model_params = None


def transcribe_locally(audio_path, model_size="small", device="cpu",
                       compute_type="int8", language="en",
                       filter_background_noise=True):
    """Fallback: transcribe locally using faster-whisper."""
    global _cached_local_model, _cached_model_params

    from faster_whisper import WhisperModel

    # Check if we need to reload the model (settings changed)
    current_params = (model_size, device, compute_type)
    if _cached_local_model is None or _cached_model_params != current_params:
        _cached_local_model = WhisperModel(model_size, device=device,
                                           compute_type=compute_type)
        _cached_model_params = current_params

    # language=None means auto-detect
    lang = None if language == "auto" else language

    # VAD filter removes non-speech segments (background noise, typing, etc.)
    if filter_background_noise:
        segments, _ = _cached_local_model.transcribe(
            audio_path,
            language=lang,
            vad_filter=True,
            vad_parameters=dict(min_silence_duration_ms=500),
        )
    else:
        segments, _ = _cached_local_model.transcribe(audio_path, language=lang)

    return "".join(segment.text for segment in segments)


def clear_cached_model():
    """Clear the cached local model (call when settings change)."""
    global _cached_local_model, _cached_model_params
    _cached_local_model = None
    _cached_model_params = None


def transcribe_audio(audio_path, force_local=False, status=None,
                     model_size="small", device="cpu", compute_type="int8",
                     language="en", filter_background_noise=True):
    """Transcribe audio, preferring API with local fallback.

    Args:
        audio_path: Path to the audio file
        force_local: If True, skip API and use local model
        status: Callback function for status messages
        model_size: Local model size (tiny, base, small, medium, large-v3)
        device: Device for local model (cpu, cuda, auto)
        compute_type: Compute type for local model (int8, float16, float32)
        language: Language code or "auto" for auto-detection
        filter_background_noise: If True, filter out non-speech sounds
    """
    if status is None:
        status = _default_status
    start = time.time()

    use_api = True
    reason = None

    if force_local:
        reason = "Local mode selected"
        use_api = False

    if use_api and not os.environ.get("OPENAI_API_KEY"):
        reason = "No OPENAI_API_KEY set"
        use_api = False

    if use_api and not has_internet():
        reason = "No internet connection"
        use_api = False

    # Lazy price check — only when using API
    api_price = None
    if use_api:
        api_price = get_api_price(status=status)
        if api_price >= BLOCK_PRICE_PER_MINUTE:
            reason = f"API price (${api_price:.3f}/min) exceeds ${BLOCK_PRICE_PER_MINUTE:.2f}/min"
            use_api = False

    warning = None
    if use_api and api_price >= WARN_PRICE_PER_MINUTE:
        warning = f"API price is ${api_price:.3f}/min (threshold: ${WARN_PRICE_PER_MINUTE:.2f}/min)"

    used_api = False
    if use_api:
        status("Transcribing via API...")
        try:
            text = transcribe_with_api(audio_path)
            used_api = True
        except Exception as e:
            status(f"API failed, falling back to local...")
            reason = str(e)
            text = transcribe_locally(audio_path, model_size=model_size,
                                      device=device, compute_type=compute_type,
                                      language=language,
                                      filter_background_noise=filter_background_noise)
    else:
        status("Transcribing locally...")
        text = transcribe_locally(audio_path, model_size=model_size,
                                  device=device, compute_type=compute_type,
                                  language=language,
                                  filter_background_noise=filter_background_noise)

    elapsed = time.time() - start
    # reason is None if API was used, otherwise explains why local was used
    return text, elapsed, used_api, api_price, warning, reason
