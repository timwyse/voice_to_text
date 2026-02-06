import sys
import os
import multiprocessing
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QPushButton, QTextEdit, QLabel, QInputDialog, QDialog,
    QComboBox, QLineEdit, QDialogButtonBox, QMessageBox, QGroupBox,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QAction, QKeySequence
from transcriber import (
    Recorder, transcribe_audio, get_data_dir, clear_cached_model,
    check_api_available,
)
from settings import (
    Settings, MODEL_SIZES, DEVICES, COMPUTE_TYPES, LANGUAGES, TOOLTIPS,
    is_model_downloaded, get_model_size_gb,
)


def ensure_api_key():
    """Prompt for OpenAI API key on first launch if not set."""
    if os.environ.get("OPENAI_API_KEY"):
        return True
    env_path = get_data_dir() / ".env"
    key, ok = QInputDialog.getText(
        None, "Voice to Text — Setup",
        "Enter your OpenAI API key (for Whisper transcription).\n"
        "Leave blank to use local-only mode.",
    )
    if ok and key.strip():
        env_path.write_text(f'OPENAI_API_KEY="{key.strip()}"\n')
        os.environ["OPENAI_API_KEY"] = key.strip()
        return True
    return False


class SettingsDialog(QDialog):
    """Settings dialog for configuring transcription options."""

    def __init__(self, settings: Settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.setWindowTitle("Settings")
        self.setMinimumWidth(400)
        self.init_ui()

    def init_ui(self):
        from PyQt6.QtWidgets import QCheckBox

        layout = QVBoxLayout()

        def make_help_label(tooltip):
            """Create a help icon with tooltip."""
            label = QLabel("ⓘ")
            label.setToolTip(tooltip)
            label.setStyleSheet("color: #888; font-size: 14px;")
            return label

        def make_row_with_help(widget, tooltip):
            """Create an HBox with widget and help icon."""
            row = QHBoxLayout()
            row.addWidget(widget, 1)
            row.addWidget(make_help_label(tooltip))
            return row

        # Local transcription settings
        local_group = QGroupBox("Local Transcription")
        local_layout = QFormLayout()

        # Model size
        self.model_combo = QComboBox()
        for size in MODEL_SIZES.keys():
            downloaded = " ✓" if is_model_downloaded(size) else ""
            self.model_combo.addItem(f"{size}{downloaded}", size)
        self.model_combo.setCurrentIndex(
            list(MODEL_SIZES.keys()).index(self.settings.model_size)
        )
        local_layout.addRow("Model size:", make_row_with_help(
            self.model_combo, TOOLTIPS["model_size"]))

        # Device
        self.device_combo = QComboBox()
        for device in DEVICES:
            self.device_combo.addItem(device)
        self.device_combo.setCurrentText(self.settings.device)
        local_layout.addRow("Device:", make_row_with_help(
            self.device_combo, TOOLTIPS["device"]))

        # Compute type (renamed to Precision in UI)
        self.compute_combo = QComboBox()
        for ct in COMPUTE_TYPES:
            self.compute_combo.addItem(ct)
        self.compute_combo.setCurrentText(self.settings.compute_type)
        local_layout.addRow("Precision:", make_row_with_help(
            self.compute_combo, TOOLTIPS["compute_type"]))

        # Language
        self.language_combo = QComboBox()
        for code, name in LANGUAGES:
            self.language_combo.addItem(name, code)
        for i, (code, _) in enumerate(LANGUAGES):
            if code == self.settings.language:
                self.language_combo.setCurrentIndex(i)
                break
        local_layout.addRow("Language:", make_row_with_help(
            self.language_combo, TOOLTIPS["language"]))

        # Filter background noise
        self.noise_filter_checkbox = QCheckBox("Filter background noise")
        self.noise_filter_checkbox.setChecked(self.settings.filter_background_noise)
        noise_row = QHBoxLayout()
        noise_row.addWidget(self.noise_filter_checkbox, 1)
        noise_row.addWidget(make_help_label(TOOLTIPS["filter_background_noise"]))
        local_layout.addRow("", noise_row)

        local_group.setLayout(local_layout)
        layout.addWidget(local_group)

        # API settings
        api_group = QGroupBox("API")
        api_layout = QFormLayout()

        self.api_key_input = QLineEdit()
        self.api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key_input.setPlaceholderText("Enter API key...")
        current_key = os.environ.get("OPENAI_API_KEY", "")
        if current_key:
            self.api_key_input.setText(current_key)
        api_layout.addRow("OpenAI API Key:", self.api_key_input)

        api_group.setLayout(api_layout)
        layout.addWidget(api_group)

        # Buttons
        button_layout = QHBoxLayout()

        reset_btn = QPushButton("Reset to Defaults")
        reset_btn.clicked.connect(self.reset_to_defaults)
        button_layout.addWidget(reset_btn)

        button_layout.addStretch()

        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save |
            QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self.save_settings)
        button_box.rejected.connect(self.reject)
        button_layout.addWidget(button_box)

        layout.addLayout(button_layout)
        self.setLayout(layout)

    def reset_to_defaults(self):
        """Reset all fields to default values."""
        self.model_combo.setCurrentIndex(
            list(MODEL_SIZES.keys()).index("small")
        )
        self.device_combo.setCurrentText("cpu")
        self.compute_combo.setCurrentText("int8")
        for i, (code, _) in enumerate(LANGUAGES):
            if code == "en":
                self.language_combo.setCurrentIndex(i)
                break
        self.noise_filter_checkbox.setChecked(True)

    def save_settings(self):
        """Validate and save settings."""
        new_model = self.model_combo.currentData()

        # Check if model needs to be downloaded
        if new_model != self.settings.model_size:
            if not is_model_downloaded(new_model):
                size_gb = get_model_size_gb(new_model)
                reply = QMessageBox.question(
                    self,
                    "Download Model",
                    f"The '{new_model}' model (~{size_gb:.1f} GB) needs to be "
                    f"downloaded.\n\nDownload will happen automatically on "
                    f"first use.\n\nContinue?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                )
                if reply != QMessageBox.StandardButton.Yes:
                    return

        # Check if local settings changed (need to clear cached model)
        old_settings = (
            self.settings.model_size,
            self.settings.device,
            self.settings.compute_type,
        )
        new_settings = (
            new_model,
            self.device_combo.currentText(),
            self.compute_combo.currentText(),
        )
        if old_settings != new_settings:
            clear_cached_model()

        # Save settings
        self.settings.model_size = new_model
        self.settings.device = self.device_combo.currentText()
        self.settings.compute_type = self.compute_combo.currentText()
        self.settings.language = self.language_combo.currentData()
        self.settings.filter_background_noise = self.noise_filter_checkbox.isChecked()
        self.settings.save()

        # Update API key if changed
        new_key = self.api_key_input.text().strip()
        current_key = os.environ.get("OPENAI_API_KEY", "")
        if new_key != current_key:
            env_path = get_data_dir() / ".env"
            if new_key:
                env_path.write_text(f'OPENAI_API_KEY="{new_key}"\n')
                os.environ["OPENAI_API_KEY"] = new_key
            else:
                # Clear the key
                if env_path.exists():
                    env_path.unlink()
                if "OPENAI_API_KEY" in os.environ:
                    del os.environ["OPENAI_API_KEY"]

        self.accept()


class TranscribeWorker(QThread):
    """Background thread for transcription."""
    # Signal: text, elapsed, used_api, api_price, fallback_reason
    finished = pyqtSignal(str, float, bool, object, object)
    error = pyqtSignal(str)
    status_update = pyqtSignal(str)

    def __init__(self, audio_path, force_local, settings: Settings):
        super().__init__()
        self.audio_path = audio_path
        self.force_local = force_local
        self.settings = settings

    def run(self):
        try:
            text, elapsed, used_api, api_price, _, reason = transcribe_audio(
                self.audio_path,
                force_local=self.force_local,
                status=lambda msg: self.status_update.emit(msg),
                model_size=self.settings.model_size,
                device=self.settings.device,
                compute_type=self.settings.compute_type,
                language=self.settings.language,
                filter_background_noise=self.settings.filter_background_noise,
            )
            self.finished.emit(text, elapsed, used_api, api_price, reason)
        except Exception as e:
            self.error.emit(str(e))
        finally:
            if os.path.exists(self.audio_path):
                os.remove(self.audio_path)


class VTTApp(QWidget):
    def __init__(self, settings: Settings):
        super().__init__()
        self.settings = settings
        self.recorder = Recorder()
        self.is_recording = False
        self.use_local = False
        self.worker = None
        self.api_fallback_reason = None  # Tracks why API mode fell back to local
        self.fallback_warning_shown = False  # Only show dialog once per session
        self.init_ui()
        self.init_menu()

    def init_ui(self):
        self.setWindowTitle("Voice to Text")
        self.setMinimumSize(400, 500)

        layout = QVBoxLayout()

        # Status label (selectable for copying error messages)
        self.status = QLabel("Ready (press Enter to record)")
        self.status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.status.setWordWrap(True)
        self.status.setStyleSheet("font-size: 14px; color: #666; padding: 4px;")
        layout.addWidget(self.status)

        # Button row
        btn_row = QHBoxLayout()

        # Record button
        self.btn = QPushButton("Record")
        self.btn.setFixedHeight(60)
        self.btn.clicked.connect(self.toggle_recording)
        btn_row.addWidget(self.btn)

        # API/Local toggle
        mode_col = QVBoxLayout()

        # Warning label for forced local mode (hidden by default)
        self.fallback_warning = QLabel("")
        self.fallback_warning.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.fallback_warning.setWordWrap(True)
        self.fallback_warning.setStyleSheet(
            "font-size: 9px; color: #f57c00; background-color: #fff3e0; "
            "border-radius: 4px; padding: 2px 4px; margin: 0;"
        )
        self.fallback_warning.hide()
        mode_col.addWidget(self.fallback_warning)

        self.mode_label = QLabel("Mode")
        self.mode_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.mode_label.setStyleSheet("font-size: 10px; color: #999; margin: 0; padding: 0;")
        mode_col.addWidget(self.mode_label)
        self.mode_btn = QPushButton("API")
        self.mode_btn.setCheckable(True)
        self.mode_btn.setFixedHeight(40)
        self.mode_btn.setFixedWidth(100)
        self.mode_btn.clicked.connect(self.toggle_mode)
        mode_col.addWidget(self.mode_btn)
        mode_col.setSpacing(2)
        btn_row.addLayout(mode_col)

        layout.addLayout(btn_row)

        # Text area
        self.text_area = QTextEdit()
        self.text_area.setPlaceholderText("Transcriptions will appear here...")
        self.text_area.setStyleSheet("font-size: 14px; padding: 8px;")
        layout.addWidget(self.text_area)

        # Copy button
        self.copy_btn = QPushButton("Copy All")
        self.copy_btn.setFixedHeight(36)
        self.copy_btn.clicked.connect(self.copy_text)
        self.copy_btn.setStyleSheet("""
            QPushButton {
                font-size: 13px; border-radius: 6px;
                background-color: #e0e0e0; color: #333; border: none;
            }
            QPushButton:hover { background-color: #bdbdbd; }
        """)
        layout.addWidget(self.copy_btn)

        self.setLayout(layout)
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.update_styles()
        self.setFocus()

    def init_menu(self):
        """Set up the macOS menu bar."""
        from PyQt6.QtWidgets import QMenuBar

        menubar = QMenuBar(self)
        menubar.setNativeMenuBar(True)

        # App menu (shows as "Voice to Text" on macOS)
        app_menu = menubar.addMenu("Voice to Text")

        settings_action = QAction("Settings...", self)
        settings_action.setShortcut(QKeySequence("Ctrl+,"))
        settings_action.triggered.connect(self.open_settings)
        app_menu.addAction(settings_action)

        # File menu with Close Window
        file_menu = menubar.addMenu("File")

        close_action = QAction("Close Window", self)
        close_action.setShortcut(QKeySequence("Ctrl+W"))
        close_action.triggered.connect(self.close)
        file_menu.addAction(close_action)

    def open_settings(self):
        """Open the settings dialog."""
        dialog = SettingsDialog(self.settings, self)
        dialog.exec()

    def mousePressEvent(self, event):
        self.text_area.clearFocus()
        self.setFocus()
        super().mousePressEvent(event)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if not self.text_area.hasFocus():
                self.toggle_recording()
                return
        if event.key() == Qt.Key.Key_Escape:
            self.text_area.clearFocus()
            self.setFocus()
            return
        super().keyPressEvent(event)

    def copy_text(self):
        text = self.text_area.toPlainText()
        if text:
            QApplication.clipboard().setText(text)
            self.status.setText("Copied to clipboard")
            self.status.setStyleSheet("font-size: 14px; color: #4CAF50; padding: 4px;")

    def toggle_mode(self):
        self.use_local = not self.use_local
        # Clear fallback warning when user manually switches modes
        if self.use_local:
            self.fallback_warning.hide()
            self.api_fallback_reason = None
        self.update_styles()

    def toggle_recording(self):
        if self.is_recording:
            self.stop_recording()
        else:
            self.start_recording()

    def start_recording(self):
        self.is_recording = True
        self.recorder.start()
        self.btn.setText("Stop")
        self.btn.setStyleSheet("""
            QPushButton {
                font-size: 18px; font-weight: bold; border-radius: 8px;
                background-color: #f44336; color: white; border: none;
            }
            QPushButton:hover { background-color: #da190b; }
        """)
        self.mode_btn.setEnabled(False)
        self.status.setText("Recording... (press Enter to stop)")
        self.status.setStyleSheet("font-size: 14px; color: #f44336; padding: 4px;")

    def stop_recording(self):
        self.is_recording = False
        duration = self.recorder.stop()
        self.btn.setText("Record")
        self.btn.setEnabled(False)
        self.btn.setStyleSheet("""
            QPushButton {
                font-size: 18px; font-weight: bold; border-radius: 8px;
                background-color: #999; color: white; border: none;
            }
        """)

        # Check if API mode will fall back to local
        if not self.use_local:
            api_available, reason = check_api_available()
            if not api_available and reason:
                self.api_fallback_reason = reason
                self.fallback_warning.setText(f"Using local: {reason}")
                self.fallback_warning.show()

                # Show dialog once per session
                if not self.fallback_warning_shown:
                    self.fallback_warning_shown = True
                    QMessageBox.warning(
                        self,
                        "Using Local Mode",
                        f"API mode is unavailable:\n\n{reason}\n\n"
                        "Transcription will use the local model instead.",
                        QMessageBox.StandardButton.Ok,
                    )

        mode = "local" if self.use_local else "API"
        self.status.setText(f"Transcribing via {mode} ({duration:.1f}s of audio)...")
        self.status.setStyleSheet("font-size: 14px; color: #ff9800; padding: 4px;")

        temp_path = self.recorder.save_to_temp()
        self.worker = TranscribeWorker(temp_path, force_local=self.use_local,
                                       settings=self.settings)
        self.worker.status_update.connect(self.on_status_update)
        self.worker.finished.connect(
            lambda text, elapsed, used_api, api_price, reason: self.on_transcription(
                text, elapsed, duration, used_api, api_price, reason,
            )
        )
        self.worker.error.connect(self.on_error)
        self.worker.start()

    def on_status_update(self, msg):
        self.status.setText(msg)
        self.status.setStyleSheet("font-size: 14px; color: #ff9800; padding: 4px;")

    def on_transcription(self, text, elapsed, recording_duration, used_api, api_price, reason):
        if self.text_area.toPlainText():
            self.text_area.append("")
        self.text_area.append(text.strip())

        info = f"Done in {elapsed:.1f}s"
        if used_api and api_price:
            cost = (recording_duration / 60) * api_price
            info += f" (API, ~${cost:.4f})"
        else:
            info += " (local)"
        self.status.setText(info)
        self.status.setStyleSheet("font-size: 14px; color: #4CAF50; padding: 4px;")

        # Update fallback warning based on result
        if not self.use_local and not used_api and reason and reason != "Local mode selected":
            # API fell back to local - update warning label (dialog already shown)
            self.api_fallback_reason = reason
            self.fallback_warning.setText(f"Using local: {reason}")
            self.fallback_warning.show()
        elif self.use_local or used_api:
            # Clear warning if user switched to local or API worked
            self.api_fallback_reason = None
            self.fallback_warning.hide()

        self.reset_button()

    def on_error(self, error_msg):
        self.status.setText(f"Error: {error_msg}")
        self.status.setStyleSheet("font-size: 14px; color: #f44336; padding: 4px;")
        self.reset_button()

    def reset_button(self):
        self.btn.setEnabled(True)
        self.mode_btn.setEnabled(True)
        self.update_styles()

    def update_styles(self):
        self.btn.setText("Record")
        self.btn.setStyleSheet("""
            QPushButton {
                font-size: 18px; font-weight: bold; border-radius: 8px;
                background-color: #4CAF50; color: white; border: none;
            }
            QPushButton:hover { background-color: #45a049; }
        """)
        self.mode_btn.setChecked(self.use_local)
        if self.use_local:
            self.mode_btn.setText("Local")
            self.mode_btn.setStyleSheet("""
                QPushButton {
                    font-size: 13px; font-weight: bold; border-radius: 15px;
                    background-color: #607D8B; color: white; border: 2px solid #455A64;
                }
                QPushButton:hover { background-color: #546E7A; }
            """)
        else:
            self.mode_btn.setText("API")
            self.mode_btn.setStyleSheet("""
                QPushButton {
                    font-size: 13px; font-weight: bold; border-radius: 15px;
                    background-color: #2196F3; color: white; border: 2px solid #1565C0;
                }
                QPushButton:hover { background-color: #1976D2; }
            """)


def main():
    multiprocessing.freeze_support()
    app = QApplication(sys.argv)
    ensure_api_key()
    settings = Settings()
    window = VTTApp(settings)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
