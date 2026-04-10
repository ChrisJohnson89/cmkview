"""py2app build configuration for cmkview."""

from setuptools import setup

APP = ["cmkview.py"]
DATA_FILES = [("", ["popup.html", "setup.html"])]

OPTIONS = {
    "argv_emulation": False,
    "iconfile": "cmkview.icns",
    "plist": {
        "CFBundleName": "cmkview",
        "CFBundleDisplayName": "cmkview",
        "CFBundleIdentifier": "com.cmkview.app",
        "CFBundleVersion": "0.3.0",
        "CFBundleShortVersionString": "0.3.0",
        "LSUIElement": False,
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
