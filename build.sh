#!/bin/bash
set -e

cd "$(dirname "$0")"

echo "Installing PyInstaller..."
pip install pyinstaller

echo "Building Voice to Text.app..."
pyinstaller voicetotext.spec --noconfirm

echo "Signing app..."
codesign --force --deep --sign - "dist/Voice to Text.app"

echo "Installing to /Applications..."
rm -rf "/Applications/Voice to Text.app"
ditto "dist/Voice to Text.app" "/Applications/Voice to Text.app"

# Reset Launch Services cache so macOS recognises the new build
/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister -kill -r -domain local -domain system -domain user 2>/dev/null || true

echo ""
echo "Done! Voice to Text.app is installed in /Applications."
echo "You can open it from Finder, Spotlight, or drag it to your Dock."
