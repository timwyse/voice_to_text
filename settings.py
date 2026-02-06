"""Settings management for Voice to Text app."""
import json
import sys
from pathlib import Path
from transcriber import get_data_dir

SETTINGS_FILE = get_data_dir() / "settings.json"

# Model sizes and their approximate download sizes in GB
MODEL_SIZES = {
    "tiny": 0.07,
    "base": 0.14,
    "small": 0.46,
    "medium": 1.42,
    "large-v3": 2.87,
}

# On macOS, CUDA isn't available (Apple Silicon uses Metal, not NVIDIA)
# Only show cpu/auto on macOS
if sys.platform == "darwin":
    DEVICES = ["cpu", "auto"]
else:
    DEVICES = ["cpu", "cuda", "auto"]

COMPUTE_TYPES = ["int8", "float16", "float32"]

# Tooltips for settings
TOOLTIPS = {
    "model_size": "Larger models are slower but more accurate. Smaller models are faster but may make more errors.",
    "device": "CPU works everywhere. Auto will use GPU if available.",
    "compute_type": "Lower precision (int8) is faster. Higher precision (float32) may be slightly more accurate.",
    "language": "Select the language being spoken, or select Auto-detect.",
}
LANGUAGES = [
    ("auto", "Auto-detect"),
    ("en", "English"),
    ("es", "Spanish"),
    ("fr", "French"),
    ("de", "German"),
    ("it", "Italian"),
    ("pt", "Portuguese"),
    ("nl", "Dutch"),
    ("pl", "Polish"),
    ("ru", "Russian"),
    ("zh", "Chinese"),
    ("ja", "Japanese"),
    ("ko", "Korean"),
    ("ar", "Arabic"),
    ("hi", "Hindi"),
]

DEFAULTS = {
    "model_size": "small",
    "device": "cpu",
    "compute_type": "int8",
    "language": "en",
    "filter_background_noise": True,
}

TOOLTIPS["filter_background_noise"] = "Filter out background noise, typing sounds, and non-speech audio. Recommended."


class Settings:
    """Manages app settings with JSON persistence."""

    def __init__(self):
        self.model_size = DEFAULTS["model_size"]
        self.device = DEFAULTS["device"]
        self.compute_type = DEFAULTS["compute_type"]
        self.language = DEFAULTS["language"]
        self.filter_background_noise = DEFAULTS["filter_background_noise"]
        self.load()

    def load(self):
        """Load settings from disk, using defaults for missing values."""
        if SETTINGS_FILE.exists():
            try:
                data = json.loads(SETTINGS_FILE.read_text())
                self.model_size = data.get("model_size", DEFAULTS["model_size"])
                self.device = data.get("device", DEFAULTS["device"])
                self.compute_type = data.get("compute_type", DEFAULTS["compute_type"])
                self.language = data.get("language", DEFAULTS["language"])
                self.filter_background_noise = data.get("filter_background_noise", DEFAULTS["filter_background_noise"])
            except (json.JSONDecodeError, KeyError):
                pass

    def save(self):
        """Persist settings to disk."""
        data = {
            "model_size": self.model_size,
            "device": self.device,
            "compute_type": self.compute_type,
            "language": self.language,
            "filter_background_noise": self.filter_background_noise,
        }
        SETTINGS_FILE.write_text(json.dumps(data, indent=2))

    def reset_to_defaults(self):
        """Reset all settings to defaults."""
        self.model_size = DEFAULTS["model_size"]
        self.device = DEFAULTS["device"]
        self.compute_type = DEFAULTS["compute_type"]
        self.language = DEFAULTS["language"]
        self.filter_background_noise = DEFAULTS["filter_background_noise"]

    def to_dict(self):
        """Return settings as a dictionary."""
        return {
            "model_size": self.model_size,
            "device": self.device,
            "compute_type": self.compute_type,
            "language": self.language,
            "filter_background_noise": self.filter_background_noise,
        }


def is_model_downloaded(model_size: str) -> bool:
    """Check if a faster-whisper model is already downloaded."""
    # Models are cached in ~/.cache/huggingface/hub/
    cache_dir = Path.home() / ".cache" / "huggingface" / "hub"
    if not cache_dir.exists():
        return False

    # Model naming pattern: models--Systran--faster-whisper-{size}
    model_name = f"models--Systran--faster-whisper-{model_size}"
    model_path = cache_dir / model_name

    # Check if the model directory exists and has content
    if model_path.exists():
        # Check for the snapshots directory which contains the actual model
        snapshots = model_path / "snapshots"
        if snapshots.exists() and any(snapshots.iterdir()):
            return True

    return False


def get_model_size_gb(model_size: str) -> float:
    """Get the approximate download size in GB for a model."""
    return MODEL_SIZES.get(model_size, 0.5)
