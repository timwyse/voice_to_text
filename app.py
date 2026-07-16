import sys
import os
import multiprocessing
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QPushButton, QTextEdit, QLabel, QInputDialog, QDialog,
    QComboBox, QLineEdit, QDialogButtonBox, QMessageBox, QGroupBox,
    QTabWidget,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QAction, QKeySequence
from transcriber import (
    Recorder, transcribe_audio, get_data_dir, clear_cached_model,
    check_api_available,
)
from settings import (
    Settings, MODEL_SIZES, DEVICES, COMPUTE_TYPES, LANGUAGES, TOOLTIPS,
    DEFAULT_POLISH_PROMPT, is_model_downloaded, get_model_size_gb,
)


class VTTTextEdit(QTextEdit):
    """QTextEdit subclass that adds missing macOS key bindings."""

    def keyPressEvent(self, event):
        mods = event.modifiers()
        key = event.key()
        # Cmd+Backspace: delete to start of line
        if key == Qt.Key.Key_Backspace and mods == Qt.KeyboardModifier.ControlModifier:
            cursor = self.textCursor()
            cursor.movePosition(cursor.MoveOperation.StartOfBlock, cursor.MoveMode.KeepAnchor)
            cursor.removeSelectedText()
            return
        # Cmd+Delete (Fn+Cmd+Backspace): delete to end of line
        if key == Qt.Key.Key_Delete and mods == Qt.KeyboardModifier.ControlModifier:
            cursor = self.textCursor()
            cursor.movePosition(cursor.MoveOperation.EndOfBlock, cursor.MoveMode.KeepAnchor)
            cursor.removeSelectedText()
            return
        super().keyPressEvent(event)


def ensure_api_key():
    """Prompt for OpenAI API key on first launch if not set."""
    if os.environ.get("OPENAI_API_KEY"):
        return True
    env_path = get_data_dir() / ".env"
    key, ok = QInputDialog.getText(
        None, "Voice to Text — Setup",
        "Enter your OpenAI API key (for transcription and polishing).\n"
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
        self.api_key_input.setPlaceholderText("Used for transcription and polishing...")
        current_key = os.environ.get("OPENAI_API_KEY", "")
        if current_key:
            self.api_key_input.setText(current_key)
        api_layout.addRow("OpenAI API key:", self.api_key_input)

        api_group.setLayout(api_layout)
        layout.addWidget(api_group)

        # Polish settings
        polish_group = QGroupBox("Transcript Polishing")
        polish_layout = QFormLayout()

        self.polish_prompt_input = QTextEdit()
        self.polish_prompt_input.setPlainText(self.settings.polish_prompt)
        self.polish_prompt_input.setFixedHeight(100)
        self.polish_prompt_input.setPlaceholderText("Enter system prompt for polishing...")
        polish_layout.addRow("Instruction prompt:", make_row_with_help(
            self.polish_prompt_input, TOOLTIPS["polish_prompt"]))

        polish_group.setLayout(polish_layout)
        layout.addWidget(polish_group)

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
        self.polish_prompt_input.setPlainText(DEFAULT_POLISH_PROMPT)

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
        self.settings.polish_prompt = self.polish_prompt_input.toPlainText().strip()
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


class PolishWorker(QThread):
    """Background thread for LLM transcript polishing."""
    finished = pyqtSignal(str)
    error = pyqtSignal(str)
    status_update = pyqtSignal(str)

    def __init__(self, raw_text: str, system_prompt: str):
        super().__init__()
        self.raw_text = raw_text
        self.system_prompt = system_prompt

    def run(self):
        try:
            from openai import OpenAI, AuthenticationError, PermissionDeniedError
            self.status_update.emit("Polishing transcript...")
            api_key = os.environ.get("OPENAI_API_KEY", "")
            if not api_key:
                self.error.emit("No OpenAI API key — add one in Settings")
                return
            client = OpenAI(api_key=api_key, timeout=60.0)
            try:
                response = client.chat.completions.create(
                    model="gpt-5-mini",
                    reasoning_effort="minimal",
                    messages=[
                        {"role": "system", "content": self.system_prompt},
                        {"role": "user", "content": (
                            f"<transcript>\n{self.raw_text}\n</transcript>"
                        )},
                    ],
                )
            except (AuthenticationError, PermissionDeniedError):
                self.error.emit("OpenAI key rejected — it may be expired or invalid")
                return
            polished = (response.choices[0].message.content or "").strip()
            self.finished.emit(polished)
        except Exception as e:
            self.error.emit(str(e))


class VTTApp(QWidget):
    def __init__(self, settings: Settings):
        super().__init__()
        self.settings = settings
        self.recorder = Recorder()
        self.is_recording = False
        self.use_local = False
        self.worker = None
        self.polish_worker = None
        # Cancelled transcribe workers we keep alive until their thread exits
        self._orphan_workers = []
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

        # Cancel button (only visible while recording/transcribing/polishing)
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setFixedHeight(60)
        self.cancel_btn.setFixedWidth(80)
        self.cancel_btn.clicked.connect(self.cancel_current)
        self.cancel_btn.setStyleSheet("""
            QPushButton {
                font-size: 14px; border-radius: 8px;
                background-color: transparent; color: #d32f2f;
                border: 1px solid #d32f2f;
            }
            QPushButton:hover { background-color: #fdecea; }
        """)
        self.cancel_btn.hide()
        btn_row.addWidget(self.cancel_btn)

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

        # Polish toggle
        polish_col = QVBoxLayout()
        self.polish_label = QLabel("Polish")
        self.polish_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.polish_label.setStyleSheet("font-size: 10px; color: #999; margin: 0; padding: 0;")
        polish_col.addWidget(self.polish_label)
        self.polish_btn = QPushButton("Off")
        self.polish_btn.setCheckable(True)
        self.polish_btn.setChecked(self.settings.polish_enabled)
        self.polish_btn.setFixedHeight(40)
        self.polish_btn.setFixedWidth(100)
        self.polish_btn.clicked.connect(self.toggle_polish)
        polish_col.addWidget(self.polish_btn)
        polish_col.setSpacing(2)
        btn_row.addLayout(polish_col)

        layout.addLayout(btn_row)

        # Tab widget for original and polished transcripts
        self.tab_widget = QTabWidget()

        self.text_area = VTTTextEdit()
        self.text_area.setPlaceholderText("Transcriptions will appear here...")
        self.text_area.setStyleSheet("font-size: 14px; padding: 8px;")
        self.tab_widget.addTab(self.text_area, "Original")

        self.polished_area = VTTTextEdit()
        self.polished_area.setPlaceholderText("Polished transcriptions will appear here...")
        self.polished_area.setStyleSheet("font-size: 14px; padding: 8px;")

        # Only show polished tab if polish is enabled
        if self.settings.polish_enabled:
            self.tab_widget.addTab(self.polished_area, "Polished")

        layout.addWidget(self.tab_widget)

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
            if not self.text_area.hasFocus() and not self.polished_area.hasFocus():
                self.toggle_recording()
                return
        if event.key() == Qt.Key.Key_Escape:
            busy = (
                self.is_recording
                or (self.worker and self.worker.isRunning())
                or (self.polish_worker and self.polish_worker.isRunning())
            )
            if busy:
                self.cancel_current()
            else:
                self.text_area.clearFocus()
                self.setFocus()
            return
        super().keyPressEvent(event)

    def copy_text(self):
        current_widget = self.tab_widget.currentWidget()
        text = current_widget.toPlainText() if current_widget else ""
        if text:
            QApplication.clipboard().setText(text)
            self.status.setText("Copied to clipboard")
            self.status.setStyleSheet("font-size: 14px; color: #4CAF50; padding: 4px;")

    def toggle_polish(self):
        self.settings.polish_enabled = not self.settings.polish_enabled
        self.settings.save()
        if self.settings.polish_enabled:
            if self.tab_widget.count() == 1:
                self.tab_widget.addTab(self.polished_area, "Polished")
        else:
            if self.tab_widget.count() == 2:
                self.tab_widget.removeTab(1)
        self.update_styles()

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
        elif self.btn.isEnabled():
            self.start_recording()

    def cancel_current(self):
        """Cancel the current recording, transcription, or polishing."""
        if self.is_recording:
            self.is_recording = False
            self.recorder.stop()
            self.status.setText("Recording cancelled")
        elif self.worker and self.worker.isRunning():
            # Detach the running worker and let it finish quietly in the
            # background (it deletes its own temp file). Keep a reference
            # until the thread exits so it isn't garbage-collected mid-run.
            for sig in (self.worker.finished, self.worker.error,
                        self.worker.status_update):
                try:
                    sig.disconnect()
                except TypeError:
                    pass
            self._orphan_workers = [w for w in self._orphan_workers
                                    if w.isRunning()]
            self._orphan_workers.append(self.worker)
            self.worker = None
            self.status.setText("Transcription cancelled")
        elif self.polish_worker and self.polish_worker.isRunning():
            self.polish_worker.terminate()
            self.polish_worker = None
            self.status.setText("Polishing cancelled")
        else:
            return
        self.status.setStyleSheet("font-size: 14px; color: #666; padding: 4px;")
        self.reset_button()

    def start_recording(self):
        # Cancel any in-progress polishing
        if self.polish_worker and self.polish_worker.isRunning():
            self.polish_worker.terminate()
            self.polish_worker = None
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
        self.polish_btn.setEnabled(False)
        self.cancel_btn.show()
        self.status.setText("Recording... (Enter to stop, Esc to cancel)")
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

        try:
            temp_path = self.recorder.save_to_temp()
        except RuntimeError as e:
            self.on_error(str(e))
            return
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

        # Chain polishing if enabled
        stripped = text.strip()
        if self.settings.polish_enabled and stripped:
            self.polish_worker = PolishWorker(stripped, self.settings.polish_prompt)
            self.polish_worker.status_update.connect(self.on_status_update)
            self.polish_worker.finished.connect(self.on_polish_complete)
            self.polish_worker.error.connect(self.on_polish_error)
            self.polish_worker.start()
            return

        self.reset_button()

    def on_polish_complete(self, polished_text):
        if self.polished_area.toPlainText():
            self.polished_area.append("")
        self.polished_area.append(polished_text)
        self.tab_widget.setCurrentWidget(self.polished_area)
        self.status.setText("Done (polished)")
        self.status.setStyleSheet("font-size: 14px; color: #4CAF50; padding: 4px;")
        self.reset_button()

    def on_polish_error(self, error_msg):
        self.status.setText(f"Polish failed: {error_msg}")
        self.status.setStyleSheet("font-size: 14px; color: #ff9800; padding: 4px;")
        self.reset_button()

    def on_error(self, error_msg):
        self.status.setText(f"Error: {error_msg}")
        self.status.setStyleSheet("font-size: 14px; color: #f44336; padding: 4px;")
        self.reset_button()

    def reset_button(self):
        self.btn.setEnabled(True)
        self.mode_btn.setEnabled(True)
        self.polish_btn.setEnabled(True)
        self.cancel_btn.hide()
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
        self.polish_btn.setChecked(self.settings.polish_enabled)
        if self.settings.polish_enabled:
            self.polish_btn.setText("On")
            self.polish_btn.setStyleSheet("""
                QPushButton {
                    font-size: 13px; font-weight: bold; border-radius: 15px;
                    background-color: #009688; color: white; border: 2px solid #00796B;
                }
                QPushButton:hover { background-color: #00897B; }
            """)
        else:
            self.polish_btn.setText("Off")
            self.polish_btn.setStyleSheet("""
                QPushButton {
                    font-size: 13px; font-weight: bold; border-radius: 15px;
                    background-color: #9E9E9E; color: white; border: 2px solid #757575;
                }
                QPushButton:hover { background-color: #8E8E8E; }
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
