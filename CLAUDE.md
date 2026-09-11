# Working on TrackImage

A local image library: a Flask server, a vanilla-JS front end, an SQLite
database, and no build step anywhere. The repository *is* the program — what
people download and unpack is these folders, unchanged.

`Trackimage_files/FOLDER_MAP.md` describes the layout in full. Read it before
moving anything between layers.

## Versioning — do not do this by hand

**Never edit a version number.** A workflow (`.github/workflows/version-bump.yml`)
raises it on every push to `main` and rewrites it in all seven places:

```
Trackimage_files/trackimage/config.py    VERSION = "4.60"   ← the one that counts
README.md                                **Version 4.60**
Trackimage_files/app.py                  the title line
README.txt                               the title line
start-linux.sh / start-macos.command / start-windows.bat
```

Editing one by hand puts it out of step with the others, and the updater
compares exactly this number. If a change genuinely must not raise the version,
put `[skip version]` in the commit message.

**Never write `CHANGELOG.md` by hand either.** The same workflow prepends an
entry from the commits since the previous tag — one line per commit, taken from
the subject. So **the commit subject is the changelog line**: write it as a
statement about what changed, in English, readable on its own.

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
   hand and paste that version's section out of `CHANGELOG.md`.

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
- **`Userdata/` and `models/` belong to the machine, not the program.** They are
  git-ignored, never travel in an archive, and an update carries them across
  untouched. Nothing may write into them from a release path.

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
