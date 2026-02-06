import sys
import os
import time
import sounddevice as sd
import soundfile as sf
import tempfile
from transcriber import transcribe_audio


def record_audio(duration=180, sample_rate=16000):
    """Record audio from the microphone (blocking, for CLI use)."""
    print(f"Recording for up to {duration} seconds... Press Ctrl+C to stop early.")
    start_time = time.time()
    try:
        recording = sd.rec(int(duration * sample_rate), samplerate=sample_rate, channels=1, dtype='float32')
        sd.wait()
    except KeyboardInterrupt:
        sd.stop()
        print("\nRecording stopped.")
    end_time = time.time()
    actual_duration = end_time - start_time
    return recording, sample_rate, actual_duration


def print_timing(recording_length, transcribe_time, total_time, used_api, api_price):
    """Print timing and cost information."""
    print(f"\n--- Timing Information ---")
    if recording_length is not None:
        print(f"Recording duration: {recording_length:.2f}s")
    print(f"Transcription time: {transcribe_time:.2f}s")
    print(f"Total script time: {total_time:.2f}s")
    if used_api and api_price and recording_length is not None:
        estimated_cost = (recording_length / 60) * api_price
        print(f"Estimated API cost: ${estimated_cost:.4f}")


def main():
    script_start = time.time()

    # Parse command-line arguments
    max_duration = 180  # Default recording duration
    audio_file = None

    if len(sys.argv) >= 2:
        # Check if argument is an existing file or a duration
        if os.path.isfile(sys.argv[1]):
            audio_file = sys.argv[1]
        else:
            try:
                max_duration = float(sys.argv[1])
            except ValueError:
                print(f"Error: '{sys.argv[1]}' is not a valid file or duration.")
                sys.exit(1)

    if audio_file is None:
        print(f"No audio file provided. Starting recording (max {max_duration}s)...")

        temp_fd, temp_path = tempfile.mkstemp(suffix='.wav')
        os.close(temp_fd)

        try:
            recording, sample_rate, recording_length = record_audio(duration=max_duration)
            print(f"\n✓ Recording length: {recording_length:.2f} seconds")

            actual_samples = int(recording_length * sample_rate)
            recording = recording[:actual_samples]
            sf.write(temp_path, recording, sample_rate)

            text, transcribe_time, used_api, api_price, warning = transcribe_audio(temp_path)
            if warning:
                print(f"Warning: {warning}")

            print("\nTranscription:")
            print(text)

            total_time = time.time() - script_start
            print_timing(recording_length, transcribe_time, total_time, used_api, api_price)

        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)
                print(f"\nTemporary audio file deleted.")
    else:
        print(f"Transcribing file: {audio_file}")
        text, transcribe_time, used_api, api_price, warning = transcribe_audio(audio_file)
        if warning:
            print(f"Warning: {warning}")

        print("\nTranscription:")
        print(text)

        total_time = time.time() - script_start
        print_timing(None, transcribe_time, total_time, used_api, api_price)


if __name__ == "__main__":
    main()
