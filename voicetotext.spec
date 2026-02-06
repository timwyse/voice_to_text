# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_data_files

# Include faster_whisper assets (silero VAD model)
faster_whisper_datas = collect_data_files('faster_whisper')

a = Analysis(
    ['app.py'],
    pathex=[],
    binaries=[],
    datas=faster_whisper_datas,
    hiddenimports=[
        'sounddevice',
        'soundfile',
        'numpy',
        'faster_whisper',
        'openai',
        'dotenv',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Voice to Text',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='Voice to Text',
)

app = BUNDLE(
    coll,
    name='Voice to Text.app',
    icon='icon.icns',
    bundle_identifier='com.vtt.voicetotext',
    info_plist={
        'NSMicrophoneUsageDescription': 'Voice to Text needs microphone access to record audio for transcription.',
        'CFBundleShortVersionString': '1.1.0',
        'NSHighResolutionCapable': True,
        'LSMinimumSystemVersion': '10.15',
        'CFBundleSupportedPlatforms': ['MacOSX'],
    },
)
