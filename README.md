# TrackImage

A local danbooru-style image library that never leaves your machine.

TrackImage catalogues pictures and video you already have on disk. It reads the
metadata that is in them, tags them with a local ML model, finds duplicates, and
gives you a gallery you can search. There is no account, no sync, no telemetry,
and no cloud. The only connections it ever makes are the Python packages it
installs on first start, the tagging model when you ask for it, and a check
against this page's Releases when you press the button.

## Install

1. Download the ZIP from [Releases](../../releases/latest) — the file attached to
   the release, not the source archive.
2. Unpack it into an **empty** folder.
3. Start it:

   | | |
   |---|---|
   | Windows | double-click `start-windows.bat` |
   | Linux | `./start-linux.sh` |
   | macOS | double-click `start-macos.command` |

The first start sets up a Python environment beside the app and creates
`Trackimage_files/Userdata` for the database and the logs. Nothing is written
outside the folder you unpacked into, apart from a small settings file.

Needs Python 3.10, 3.11 or 3.12.

## Auto-tagging

Tagging uses WD-EVA02-Large v3 (~1.26 GB), which is **not** in the release and is
fetched from Settings › Auto-tagging when you want it. It runs on your GPU if
one is available and on the processor otherwise. Everything stays local.

## Updating

Settings › Repair & Update has a button that checks this repository for a newer
release. It downloads it, verifies the archive, copies your database to
`Userdata-backup-v<version>.zip` beside the installation, and restarts into the
new version. Your pictures, database, settings and the tagging model are carried
across untouched. If anything goes wrong the previous version is put back.

You can also just download the new ZIP and unpack it into a new empty folder,
then move your old `Trackimage_files/Userdata` into it. That works too and always
will.

## Layout

```
TrackImage/
├─ start-windows.bat / start-linux.sh / start-macos.command
└─ Trackimage_files/
    ├─ app.py, FOLDER_MAP.md
    ├─ trackimage/   the Python package, 27 layers
    ├─ Static/       index.html, css, js, fonts, icons
    ├─ models/       created on first use, never in a release
    └─ Userdata/     your database and logs, never touched by an update
```

`Trackimage_files/FOLDER_MAP.md` describes it in full.

## Fonts

DM Sans and Space Mono are bundled under the SIL Open Font License 1.1; the
licences sit next to them in `Static/fonts`. Nothing is loaded from a CDN.
