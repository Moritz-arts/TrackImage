# Working on TrackImage

A local image library: a Flask server, a vanilla-JS front end, an SQLite
database, and no build step anywhere. The repository *is* the program — what
people download and unpack is these folders, unchanged.

`Trackimage_files/docs/FOLDER_MAP.md` describes the layout in full. Read it before moving
anything between layers.

The repository root stays short on purpose — README.md, CLAUDE.md and the three
launchers. Everything else lives in `Trackimage_files/`, `docs/` included, so an
installation is six entries. Do not add another file beside the launchers.

**What people download is not what the repository holds.** `.gitattributes`
marks the workshop files `export-ignore`, so `.github/`, `CLAUDE.md` and the
ignore lists are absent from the source archive GitHub builds — an installation
is README.md, `Trackimage_files/` and the launchers. A new file that
belongs to the workshop rather than to the program goes in that list too, and
in the helper's cleanup in `updater.py` so installations made before it stop
carrying it. It changes nothing for a clone, and Actions is unaffected: it
checks the repository out rather than unpacking an archive.

## Versioning — do not do this by hand

**Never edit a version number.** A workflow (`.github/workflows/version-bump.yml`)
raises it on every push to `main` and rewrites it in all six places:

```
Trackimage_files/trackimage/config.py    VERSION = "4.60"   ← the one that counts
README.md                                **Version 4.60**
Trackimage_files/app.py                  the title line
start-linux.sh / start-macos.command / start-windows.bat
```

Editing one by hand puts it out of step with the others, and the updater
compares exactly this number. If a change genuinely must not raise the version,
put `[skip version]` in the commit message.

**Never write `[skip ci]` in a commit message, not even to talk about it.**
GitHub reads that marker anywhere in the message and skips the whole run, so a
commit *describing* the marker silently skips its own version bump — which has
already happened once, and cost main a version number. In a commit message call
it "the skip marker" and spell it nowhere. Inside a file like this one it is
harmless; only commit messages are scanned.

**Never write the changelog by hand either.** The same workflow prepends an
entry from the commits since the previous tag — one line per commit, taken from
the subject. So **the commit subject is the changelog line**: write it as a
statement about what changed, in English, readable on its own. The bump commit
is named after the last real commit of the version, so a merge commit's "Merge
pull request #4 from…" never becomes the title.

```
good: Full view: the library beside the picture actually works
bad:  fix stuff / wip / address review
```

The body is where the reasoning goes — as much as it deserves. It does not
reach the changelog, and that is the point: the list stays short, the reasoning
stays with the diff.

## How a change reaches people

1. Work on the branch you were told to use, push it.
2. The user merges it into `main`.
3. The workflow raises the version, writes the changelog line, tags the commit
   (`v4.60`), and pushes. It does **not** publish a release.
4. When the user judges a version ready, they draft a release from its tag by
   hand and paste that version's section out of `Trackimage_files/docs/CHANGELOG.md`.

TrackImage offers two channels in Settings › Repair & Update:

| | |
|---|---|
| **Stable** | the newest GitHub release → `archive/refs/tags/<tag>.zip` |
| **Latest** | the `main` branch → `archive/refs/heads/main.zip` |

Neither needs an uploaded file: GitHub's own source archive is the release.
`trackimage/updater.py` verifies every archive — intact, actually TrackImage,
and newer than what is installed — before anything is replaced.

Do not create releases or tags yourself, and do not push to `main`.

## Traps that have already cost time

- **The detail overlay carries a second copy of the sidebar.** Both the gallery
  and the open picture render the folder tree and the tag list, so every `id`
  in them exists twice and `getElementById` only ever finds the gallery's.
  Anything that touches those columns must address **all** copies —
  `querySelectorAll` with a class or a `data-` attribute. See `toggleFolderIdx`,
  `renderTagList`, `rerenderTagCol`, `renderFolderSidebar`.
- **A tag must sit on a commit that contains the version it names.** v4.58 was
  once tagged over a tree that still said 4.57; the updater refused it, and
  correctly so. The workflow tags its own bump commit for this reason.
- **An update replaces, it does not merge.** `Trackimage_files/` is swapped
  whole by the helper in `updater.py`, and a file an older version shipped and
  this one does not is deleted by name there. Drop a file from the
  root and it has to be added to that list, or it survives on every machine
  that updates.
- **`Userdata/`, `models/` and `venv/` belong to the machine, not the program.**
  They sit inside `Trackimage_files/`, which an update replaces whole, so the
  helper in `updater.py` moves all three across by hand. They are git-ignored
  and never travel in an archive. Forgetting one costs the user their database,
  a 1.3 GB model, or minutes of pip on every single update.
- **The helper must not live in the folder it deletes.** A shell reads a script
  as it goes, so when the helper removed the staging folder it was being read
  from, execution simply stopped there — and the two lines after it, the tidy-up
  and the restart, never ran. It is written to the system temp folder now and
  deletes itself last.
- **A cleanup added to the helper takes effect one version late.** The script
  that performs a swap comes from the version being replaced, so it only knows
  the names that version knew. `tidy_installation()` in `updater.py` runs at
  start from the version that actually knows them; add a newly dropped name to
  its `_STALE` list as well as to the helper.
- **A backup belongs to the user.** Backups go to
  `Trackimage_files/Userdata/Backup`, the last three are kept, and older ones
  are removed. Stray ones from the layout before that are *moved* there at
  start, never deleted — deleting somebody's backup is not a tidy-up.
- **The update helper runs unseen, and reports afterwards.** It cannot show its
  work as it happens — TrackImage is closed for the swap — so it writes each
  step to a log, hands that log to `Userdata/Logs/update.log`, and
  `report_last_update()` reads it into the app's own console on the next start.
  On Windows `timeout` and `pause` are ruled out: they read from a console and
  fail or hang wherever there is none. `ping -n` is the sleep, and every exit
  path restarts TrackImage — including the ones that failed.
- **Nothing the helper starts may wait for a keypress.** Nobody is sitting in
  front of a window that opened by itself, so a launcher branch ending in
  `pause` stays on screen for ever — which is what `:other_instance` and
  `:no_start` did after an update. The helper exports `TI_AFTER_UPDATE`, and
  `:hold` in the launchers counts down and closes instead of pausing.

- **Ask for everything at once.** The settings page fetched seven endpoints one
  after another, so it cost the sum of them and each one queued behind whatever
  the background workers were doing. The server runs `threaded=True`, so a
  `Promise.all` costs the slowest instead of the total — measured at 437 ms
  against 68 ms. Any page that needs several endpoints should do the same.
- **A poll is a delay.** Anything driven by polling is stale for as long as the
  interval: the work spinner kept turning for up to four seconds after the work
  had finished. `pollWork()` in `13-startup.js` asks both endpoints together and
  follows the work — 1.2 s while something is running, 5 s when nothing is.

## House style

Both languages here are written the same way: compact code, and comments that
explain *why* — usually the thing that was wrong before, so the next reader does
not undo the fix. Look at the surrounding file and match it; do not add a
comment that only restates the line under it.

JavaScript is plain ES5-flavoured DOM code in numbered files (`01-state.js` …
`13-startup.js`) loaded in order, no modules and no framework. Python is layered
the way `trackimage/__init__.py` lists. Keep both as they are.

## Checks before pushing

There is no test suite. Run at least:

```bash
python3 -m py_compile Trackimage_files/trackimage/*.py Trackimage_files/app.py
for f in Trackimage_files/Static/js/*.js; do node --check "$f" || echo "FAIL $f"; done
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/version-bump.yml'))"
```

Never commit `__pycache__`, `Userdata/`, or anything the `.gitignore` names —
one `.pyc` has already reached `main` this way.
