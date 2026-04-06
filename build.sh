#!/bin/bash
set -e

VERSION=$(python3 -c "import re; print(re.search(r'__version__\s*=\s*\"(.+?)\"', open('cmkview.py').read()).group(1))")
echo "Building cmkview v${VERSION}..."

# Clean previous build
rm -rf build dist

# Build .app
python3 setup.py py2app

# Create DMG
DMG_DIR="dist/dmg_staging"
mkdir -p "$DMG_DIR"
cp -R dist/cmkview.app "$DMG_DIR/"
ln -s /Applications "$DMG_DIR/Applications"

hdiutil create \
  -volname "cmkview" \
  -srcfolder "$DMG_DIR" \
  -ov \
  -format UDZO \
  "dist/cmkview-${VERSION}.dmg"

rm -rf "$DMG_DIR"

echo ""
echo "Done! Built:"
echo "  dist/cmkview.app"
echo "  dist/cmkview-${VERSION}.dmg ($(du -h "dist/cmkview-${VERSION}.dmg" | cut -f1))"
