"""py2app build configuration for cmkview."""

from setuptools import setup

APP = ["cmkview.py"]
DATA_FILES = [("", ["popup.html", "setup.html"])]

OPTIONS = {
    "argv_emulation": False,
    "iconfile": None,  # Replace with "cmkview.icns" if you have an icon
    "plist": {
        "CFBundleName": "cmkview",
        "CFBundleDisplayName": "cmkview",
        "CFBundleIdentifier": "com.cmkview.app",
        "CFBundleVersion": "0.1.0",
        "CFBundleShortVersionString": "0.1.0",
        "LSUIElement": True,  # Hide from Dock, menu bar only
    },
    "packages": ["requests", "certifi"],
    "frameworks": [],
}

setup(
    name="cmkview",
    app=APP,
    data_files=DATA_FILES,
    options={"py2app": OPTIONS},
    setup_requires=["py2app"],
)
