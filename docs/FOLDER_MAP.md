# TrackImage — folder map (v4.57)

Corrected in v4.57: the launchers sit in the unpacked folder and everything
TrackImage owns lives one level down in `Trackimage_files/`. The launcher checks
for `Trackimage_files/app.py` and refuses to start if the two were separated.

```
TrackImage_v4.57/                 <- what the ZIP unpacks to
├─ start-windows.bat              the only things the user should see
├─ start-linux.sh
├─ start-macos.command
└─ Trackimage_files/
    ├─ app.py                     entry point; the changelog header lives here
    ├─ launcher_check.py          readiness probe the launchers call
    │
    ├─ trackimage/                Python package, 27 layers, order fixed in __init__.py
    │   ├─ __init__.py            the load order — read this first
    │   ├─ state.py               layer 0   shared runtime variables
    │   ├─ config.py              layer 1   VERSION, paths, extensions, _XMP_MAP, Flask app
    │   ├─ logging_setup.py       layer 2
    │   ├─ platform_bits.py       layer 3
    │   ├─ appconfig.py           layer 4
    │   ├─ db.py                  layer 5
    │   ├─ events.py              layer 6
    │   ├─ media.py               layer 7
    │   ├─ metadata.py            layer 9   EXIF / XMP / IPTC / sidecars
    │   ├─ hashing.py             layer 10
    │   ├─ thumbnails.py          layer 11
    │   ├─ processing.py          layer 12
    │   ├─ tagger.py              layer 13  WD-EVA02 ONNX + tagging workers
    │   ├─ duplicates.py          layer 14
    │   ├─ scanning.py            layer 15
    │   ├─ network.py             layer 16
    │   ├─ runtime.py             layer 17  model download, asset check, benchmarks
    │   ├─ picker.py              layer 18
    │   ├─ importing.py           layer 19
    │   ├─ updater.py             layer 20  GitHub check, download, staged swap
    │   ├─ api_system.py          layer 21
    │   ├─ api_folders.py         layer 22
    │   ├─ api_images.py          layer 23
    │   ├─ api_tags.py            layer 24
    │   ├─ api_duplicates.py      layer 25
    │   ├─ api_media.py           layer 26
    │   └─ desktop.py             layer 27  window, main()
    │
    ├─ Static/                    static_folder AND template_folder
    │   ├─ index.html             Jinja shell; loads css + the 13 js files in order
    │   ├─ trackimage.ico         7 sizes, 16 to 256
    │   ├─ trackimage.png
    │   ├─ css/app.css
    │   ├─ fonts/                 bundled, never a CDN
    │   │   ├─ dm-sans-300/400/500/600/700.ttf
    │   │   ├─ space-mono-400/700.ttf
    │   │   └─ OFL-DMSans.txt, OFL-SpaceMono.txt
    │   └─ js/
    │       ├─ 01-state.js        S{} — the whole client state
    │       ├─ 02-util.js         helpers, topbar, librarySidebarHtml
    │       ├─ 03-api.js
    │       ├─ 04-render.js
    │       ├─ 05-gallery.js      renderGallery, startResize, infinite scroll
    │       ├─ 06-detail.js       full-screen overlay, toggleSidebarCol
    │       ├─ 07-folders.js      folder tree, renderFolderSidebar
    │       ├─ 08-tags.js         tag column, rerenderTagCol
    │       ├─ 09-duplicates.js
    │       ├─ 10-import.js
    │       ├─ 11-settings.js
    │       ├─ 12-modals.js
    │       └─ 13-startup.js
    │
    ├─ models/                    NOT shipped — created and filled on first run
    │   └─ wd-eva02-large-tagger-v3/   ~1.26 GB, downloaded from Settings
    │
    ├─ _ti_update/                NOT shipped — only exists while an update installs
    └─ Userdata/                  NOT shipped — the launcher creates it
        ├─ Databank/              SQLite (Flask instance_path)
        ├─ Logs/
        └─ ignored_tags.txt
```

## Rules that follow from this layout

- A release replaces everything **except** `Userdata/` and `models/`. Nothing
  outside those is user state, nothing inside them is rewritten by an update.
- `Static/js` files load in numeric order into one shared global scope. A
  function defined in `08-tags.js` cannot be called at load time from
  `04-render.js` — only later, from an event. Getting this wrong is what caused
  the black screen in v4.50.
- The version lives in five places and all five must agree:
  `trackimage/config.py` (`VERSION`), the `app.py` header, and the three
  launchers.
- `REQUIRED_ASSETS` in `config.py` is the package manifest. Check a build
  against it before shipping — 25 entries as of v4.57.
- Route count is the equivalence proof for structural changes: **112 routes** as of v4.57.
