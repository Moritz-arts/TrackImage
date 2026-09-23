# TrackImage v4.79

[what changed](Trackimage_files/docs/CHANGELOG.md) · [releases](../../releases)

A local danbooru-style image library that never leaves your machine.

TrackImage catalogues pictures and video you already have on disk. It reads the
metadata that is in them, tags them with a local ML model, finds duplicates, and
gives you a gallery you can search. There is no account, no sync, no telemetry,
and no cloud. The only connections it ever makes are the Python packages it
installs on first start, the tagging model when you ask for it, and a check
against this repository when you press the button.

## Install

1. Download **Source code (zip)** from [the latest release](../../releases/latest).
   That archive is the program: no build step, nothing to compile.
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

Settings › Repair & Update checks this repository and offers two channels:

| | |
|---|---|
| **Stable** | the newest release. Versions that have been looked at and declared finished. |
| **Latest (Beta)** | the `main` branch as it stands. Every change, minutes after it is pushed — untested, so bugs are part of the deal. |

Both use the same version numbers and the same files — they differ only in which
commit they point at. The version is raised on every push to `main`, and
[the changelog](Trackimage_files/docs/CHANGELOG.md) lists what each one brought.

Whichever channel you pick, the button downloads it, verifies the archive,
copies your database into
`Trackimage_files/Userdata/Backup`, and restarts into the new version. A window
names each step in TrackImage's own console. The folder keeps its name, so a
shortcut to it keeps working; which version is installed is shown in the app.
Your pictures, database, settings and the tagging model are carried
across untouched. If anything goes wrong the previous version is put back.

You can also just download the source ZIP and unpack it into a new empty folder,
then move your old `Trackimage_files/Userdata` into it. That works too and always
will.

## Layout

```
TrackImage/
├─ start-windows.bat / start-linux.sh / start-macos.command
├─ README.md
└─ Trackimage_files/
    ├─ docs/        CHANGELOG.md and FOLDER_MAP.md
    ├─ app.py
    ├─ trackimage/   the Python package, 27 layers
    ├─ Static/       index.html, css, js, fonts, icons
    ├─ models/       created on first use, never in an archive
    └─ Userdata/     your database and logs, never touched by an update
```

`Trackimage_files/docs/FOLDER_MAP.md` describes it in full. The repository also holds the
automation and the notes for whoever works on TrackImage; those are kept out of
the archive, so what you unpack is the program and nothing else.

## Fonts

DM Sans and Space Mono are bundled under the SIL Open Font License 1.1; the
licences sit next to them in `Static/fonts`. Nothing is loaded from a CDN.
