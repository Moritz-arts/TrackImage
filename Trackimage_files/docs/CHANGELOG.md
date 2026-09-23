# TrackImage — version history

Every push to `main` raises the version by one and adds its entry here
automatically -- one line per change, newest first. A release is drafted by hand
from the tag of whichever version is judged ready, and this is the text to paste
into it.

## v4.79 — 2026-09-23

- Smart clean first greys out what would go, and deletes only when confirmed
- Settings are laid out as cards in one readable column, with the long explanations folded away
- Settings: Keyboard, Help and Repair & Update in the same cards as the other pages

## v4.78 — 2026-09-23

- Duplicates: a phone photo and its shared copy are found as the same picture
- Duplicates: Max difference moves in single percent steps up to 10%
- Smart clean works up to 5%, and keeps anything moved, retouched or animated
- Smart clean keeps the least compressed copy, measured in the pixels, not by file size
- Smart clean works one group at a time and shows every picture before anything goes

## v4.77 — 2026-09-22

- Full view: no black flash between pictures, and the zoom stays when stepping to the next
- Dragging a picture out of a browser tab delivers the original file again
- Duplicates: a single click selects a picture instead of opening it
- Settings: keyboard shortcuts have a tab of their own
- Duplicates: Smart clean keeps the best copy and trashes only pixel-identical ones
- Ctrl+A selects every picture in the view, not only the loaded ones
- Ctrl + mouse wheel sets how many pictures fit in a row
- Paste lands where the mouse is, and brings files copied outside TrackImage

## v4.76 — 2026-09-16

- Rename: clicking a suggested name takes it instead of closing the dialog
- Full view: hiding the info panel no longer leaves a white bar beside it

## v4.75 — 2026-09-13

- The automatic check says which channel it looked at

## v4.74 — 2026-09-13

- The database folder is called Database, and the last German comments are gone
- The installation folder keeps its name instead of carrying the version
- The staging folder goes even when the installation folder was renamed

## v4.73 — 2026-09-13

- Dropping files in works from any page, and no longer needs the window in front

## v4.72 — 2026-09-13

- An update is noticed the minute it is pushed, not five minutes later

## v4.71 — 2026-09-13

- A backup holds the database, not the thumbnails, and Latest says it is beta

## v4.70 — 2026-09-13

- The launcher window closes when TrackImage is up, instead of returning to a prompt

## v4.69 — 2026-09-12

- An update turns the indicator, narrates itself, and names the folder after itself

## v4.68 — 2026-09-12

- Settings opens at the speed of its slowest request, not the sum of them

## v4.67 — 2026-09-12

- The update reports into TrackImage's own console, and no window is left waiting

## v4.66 — 2026-09-12

- Drop the changelog link from the update card

## v4.65 — 2026-09-12

- An update shows its progress, keeps its backups in Userdata, and docs moves in

## v4.64 — 2026-09-12

- An update leaves nothing behind, and stale files go on the next start

## v4.63 — 2026-09-12

- The workshop files stay out of what people download

## v4.62 — 2026-09-12

- The version sits in the README title, and a hint stops overlapping its buttons
- An update that fails now says so, restarts, and keeps your venv
- Say in CLAUDE.md that a commit must never spell the skip marker

## v4.61 — 2026-09-12

- Docs move into one folder, and the update dialog lists what is new

## v4.60 — 2026-09-11

- Two channels, and a history that writes itself
- The front page says which version it is, and the history stays short
- A CLAUDE.md, so the next session does not re-derive the rules

## v4.59
- TrackImage follows the repository's main branch instead of its releases. A
  release was a snapshot somebody had to remember to attach a file to, and a
  forgotten one left the app announcing a version it could not fetch. The
  branch is always there and always complete: the check reads the version out
  of config.py as it stands in the branch, and the install takes the archive
  GitHub builds from it -- the same folders TrackImage runs from.
- The version is raised automatically on every push to that branch, by a
  workflow that rewrites it in config.py and in the five places the same number
  is shown to a human. A number nobody remembers to raise is a number that
  quietly stops meaning anything, and that is what the check rests on.
  [skip version] in a commit message pushes without raising it.
- The archive is verified as before -- intact, actually TrackImage, and newer
  than what is installed. It is no longer required to match the version that
  was announced a moment earlier: a branch moves, and someone pushing between
  the check and the download is not an error worth refusing an update over.

## v4.58
- Full view: the library beside the picture works. The open picture carries its
  own copy of the folder and tag columns, so every id in them exists twice, and
  getElementById only ever answered with the first -- the hidden gallery copy
  behind the picture. A branch of the tree clicked beside the photograph stayed
  shut and a tag clicked there filtered a gallery nobody could see. Both copies
  are addressed by class now and fold and redraw together.
- Choosing a folder, a name, a tag or a rating there also leaves the picture:
  the overlay steps aside and the gallery it just filtered comes forward, which
  is what "show me these" was asking for. Folding a branch open is not a choice
  of that kind and leaves the picture where it is. The same goes for removing
  one of the filter chips above the tag column.
- Keyboard navigation of those columns looks inside the open picture's copy
  rather than at whichever copy the document lists first.
- The buttons in the panel say what they do: Locate in Explorer, Locate in
  TrackImage, Wipe metadata.
- The updater installs a release that has no file attached to it. GitHub builds
  a source archive from every tag, and for this project that archive IS the
  release -- the same folders TrackImage runs from. It was invisible here
  because only uploaded assets were looked at, so a release published without
  a hand-made ZIP reported "cannot be installed from here" while the download
  sat on the page. The archive is still verified the same way: it has to be
  intact, has to be TrackImage, and has to contain the version its tag claims.
  GitHub packs it on the fly and announces no length, so the progress reads in
  megabytes rather than as a percentage.

## v4.57
- Settings has a new tab, Repair & Update. The installation check moved there
  out of Help, which was holding two unrelated things: how the app is used, and
  what state the install is in.
- A button asks GitHub whether a newer release exists, and can install it. The
  download is checked before anything is touched -- the archive has to be
  intact, has to actually be TrackImage, has to match the version its tag
  claims, and has to be newer than what is running. The database is copied to
  Userdata-backup-v<version>.zip beside the installation, and only then does the
  swap happen: a small helper waits for TrackImage to close, exchanges the
  folders, carries Userdata and models across untouched, and starts the new
  version. If any step fails the previous version is put back.
  A download is only ever fetched from the TrackImage repository; a request
  naming any other address is refused.
- The check can run once at start, but only if switched on in the new tab. It
  is off by default: TrackImage still opens no connection of its own.
- Help & Reference lists every shortcut, and the global ones can be rebound.
  Click a key, press the combination you want. A combination already in use is
  refused rather than silently stealing the other action. Escape and the digits
  stay fixed -- Escape is the way out of every state in the app, and the digits
  are ten keys that would have to move together.
  Bindings live beside the other settings, so they follow the app rather than
  the browser it was opened in.
- What a key means is now resolved in one place instead of being spelled out in
  each branch of the handler.

## v4.56
- Keywords written into an XMP sidecar as one separated string are read again.
  Downloaders driving ExifTool put them under pdf:Keywords, not dc:subject, so
  a sidecar could be found, parsed and still hand back nothing. exif:DateTimeOriginal
  is read as well. An rdf:Seq is still taken one keyword per entry and never cut
  a second time, so a keyword containing a comma survives.
- Sidecars are read for pictures too, not only for video. A writer that cannot
  reach into an MP4 container often cannot reach into a JPEG either and drops a
  .xmp next to both; those keywords were invisible here while every other
  program showed them.
- One splitter and one merge for keywords across the whole app. Semicolons and
  commas both count as separators wherever keywords are read, and the merge
  dedupes case-insensitively, so a word carried by both the file and its sidecar
  can no longer arrive twice. What the file itself holds keeps its spelling.
- The folder and tag columns work while a picture is open. Both the gallery and
  the open picture held a copy of those columns under the same id, so collapsing
  a column, dragging it wider, opening a folder or filtering tags in full screen
  reached the hidden gallery copy instead. Nothing on screen moved until the
  picture was closed and opened again.

## v4.55
- The window stops waiting on a server that is already listening. It asked
  whether the port was open twice a second, so up to half a second could pass
  after Flask had bound it with nothing happening -- and the log reported that
  as time Flask had taken. It asks twenty times a second now. The minute it is
  willing to wait altogether has not changed.
- Counting the network adapters no longer holds up the start. It took over a
  second of every start with network sharing on, and the answer is only ever a
  line in the log: the window connects to 127.0.0.1 either way, and the
  settings page asks for the address when it needs it. It is worked out
  alongside the rest of the start and reported a moment later, so that line now
  arrives after the one saying TrackImage is running rather than before it.

## v4.54
- Starting no longer waits on a machine that does not exist. Every start asked
  the network to resolve a host called "trackimage", so a browser could be sent
  to a friendlier address than localhost. There is no such machine on an
  ordinary network, and Windows works patiently through DNS, then LLMNR, then
  NetBIOS before it agrees -- several seconds, every time. The answer is only
  ever used for the address printed for a browser, so the window mode does not
  ask at all now, and the browser mode gives up after a third of a second.
- The log says where the time went. It used to jump from "everything is ready"
  straight to "the window is up" with six silent seconds in between and no way
  to tell what had spent them. Each stage of the start now reports its own
  duration when it takes longer than a quarter second, and the total is printed
  once the server is up. A slow start answers itself from here on.

## v4.53
- The folder and tag columns stay beside a picture opened full size. They are
  the same columns the gallery shows, with their own folded state kept apart
  from it, so putting them away here leaves the gallery as it was. L folds
  just them; F clears everything and leaves nothing but the picture, and F
  again brings both panels back exactly as they were.
- Those columns were written out twice before, once for the gallery and once
  for the duplicates page. A third copy for the detail view would have been
  one place too many to keep in step, so there is one now.
- An XMP sidecar next to a video is read. MP4 has no EXIF -- it carries
  QuickTime atoms -- so the tools that write metadata for video write a .xmp
  beside the file instead, and TrackImage could not see it: a video whose
  keywords and rating every other program showed had none here. Nothing is
  written. Where the file itself carries a field, the file wins.
- A sidecar follows its file. It is bound to the file by name and nothing
  else, so renaming, moving, importing or deleting without it would leave a
  stray .xmp behind and a video that had quietly lost what it knew.
- Keywords already in a file can become tags. Pictures out of Lightroom or
  Bridge often carry keywords someone spent real time on. Off unless switched
  on, and stored as source=embedded so they stay apart from what the tagger
  produced -- and can be removed again without touching anything else.
- Folding the write-ahead log back into the database on the way out has its
  own budget now, ten seconds rather than sharing three with the trash sweep.
  Closing mid-scan over a 1 Gbit/s link could leave the .db behind what had
  actually been written. Nothing was ever lost -- SQLite replays the log on
  the next open -- but the file on disk is what a backup copies.

## v4.52
- The note about tkinter on Linux and macOS no longer reads like a problem. It
  was written when the folder picker was a Tk dialog and nothing else; since
  v4.46 the system dialog comes first and a box to type the path is there when
  no dialog works at all. Tk is a convenience now and the message says so.
- start-windows.bat has CRLF line endings, which is what cmd.exe expects. It had
  been LF for a long time without visible trouble, but a batch file with the
  wrong endings fails in ways that are hard to read when it does fail. The
  linter had never caught it: it opened the file in text mode, where Python
  quietly turns CRLF into LF before the check can see it.
- Python 3.13 is tested. The version warning stopped naming it, and the build
  compiles and runs the whole package on 3.10, 3.11, 3.12 and 3.13.
- The empty folders module is gone. Nothing had been filed into it -- the routes
  it was meant to hold live in api_folders -- so it was a name in the load order
  and nothing else.
- updater.py carries the settings a repository will be named in. Until
  GITHUB_OWNER has a value nothing there touches the network, by design.

## v4.51
- The window is not black any more. v4.50 loaded thirteen script files and the
  first one died on its first line: it built the icon set by calling a helper
  that only arrived ten files later. Nothing after that had the state object to
  work with, so the page loaded, asked the server for nothing, and sat there.
  The splitter no longer takes its own filing for granted -- it works out what
  each file needs the moment it loads and moves those declarations to the front
  until nothing is left waiting.
- The tagger probe stopped crashing. _tag_runtime_set takes a parameter named
  state, and the split had made state the name of the module holding values that
  change while the program runs -- so the function set an attribute on the string
  it was handed instead. The thread died on every start.
- No more .pre449 folders on a fresh install. The launcher made Logs and
  Databank where they used to live, before Python ran, so TrackImage found two
  empty folders, took them for an older layout and dutifully backed up nothing.
  All three launchers make them under Userdata now, and an empty folder is
  recognised for what it is rather than copied first.
- Two tests that would have caught all of this: the load-order check walks every
  node now, and the files are loaded in order into a real DOM afterwards.

## v4.50
- TrackImage starts when pillow-heif is installed. v4.49 did not. The block that
  adds .heic to the known image types moved into media.py during the split, but
  the name it adds to lives in config.py, and media never imported it. The block
  sits inside a try that catches ImportError, and a missing name is a NameError,
  so nothing caught it -- the app stopped on the way up.
- HEIC pictures are seen by the scanner again. MEDIA_EXTENSIONS is built once out
  of IMAGE_EXTENSIONS, and in one file the HEIC block ran two lines before that.
  Split apart it ran seven modules later, so .heic reached the image set and
  never the media set the scanner walks.
- Optional packages are now tested by standing in for them, which is how the two
  faults above would have been caught.

## v4.49
- app.py is a package. What was one file of 12,437 lines is now 25 modules under
  trackimage/, so changing how duplicates are grouped means opening
  duplicates.py and nothing else. __init__.py lists them in the order they load,
  foundations first, and that list is literally what runs.
- The move is provably a move and not a rewrite. Every function kept the source
  it had, comments and all. The thirty names that get rebound while the program
  runs live in state.py; ten calls that reach from a lower layer to a higher one
  import inside the function that makes them. The routing table was compared
  before and after: 106 rules, same paths, endpoints and methods.
- index.html is a shell. The stylesheet and 3,338 lines of script became
  css/app.css and thirteen numbered script files that load in number order.
- Databank, Logs and ignored_tags.txt moved into Userdata. An older layout is
  moved in on first run, with a copy left behind as Databank.pre449 and so on --
  never deleted, so there is always a way back.

## v4.48
- The download has the folder layout back that v4.33 introduced. The v4.46
  and v4.47 archives unpacked everything into one heap: app.py, Static and
  launcher_check.py sat beside the three launchers instead of inside
  Trackimage_files, so the launcher looked for app.py one level down, did not
  find it, and stopped with the error it is meant to print when a ZIP has been
  unpacked wrong. Nothing in the program changed; the archive was built wrong.
  The folder a user unpacks holds the three start files and Trackimage_files,
  and everything else -- Databank, Logs, models, venv -- is made inside it on
  first run, as before.

## v4.47
- Linking a folder no longer touches the disk to decide whether it may be
  linked. The check added in v4.46 resolved the path and asked the file
  system whether it was a directory, which on a network folder that happens
  to be offline means waiting for SMB to give up and then refusing -- with
  the folder lock held the whole time. A library on a NAS could not be
  linked at all while the NAS was away, which is exactly when a fresh
  install needs to be able to write it down. The path is now normalised
  without asking the file system anything, and a network path that cannot
  be reached is accepted and noted in the log instead of refused. Local
  paths are still checked, so a typo is still caught.
- Resolving is gone with it. It rewrote a junction or a symlink to whatever
  it pointed at, so a library reached through a link was stored under a name
  the user never chose and would not recognise.
- The TrackImage button works when the picture was opened from the
  duplicates page. It filtered to the folder, but the duplicates view does
  not load a gallery, so nothing was ever found to scroll to and the search
  ran sixty empty rounds before giving up. It now goes to the gallery first.
- Clicking a picture to unselect it works again after it has been dragged.
  The press remembers that it did the selecting so the click does not undo
  it (v4.46); a press that ended in a drag rather than a click left that
  note behind, and the next click on the same picture spent it instead.
- When no folder dialog works, both reasons are reported rather than only
  the last one, and neither dialog is waited on for longer than a minute.

## v4.46
- The folder picker no longer depends on Tcl. A user reported "Error: This
  probably means that Tcl wasn't installed properly" on "Link new folder" and
  could not add a folder at all, which leaves the whole app unusable. The
  picker was a tkinter dialog and nothing else, so a Python without a working
  Tcl had no way in. Windows now asks the shell for its own folder dialog
  (IFileDialog, the one Explorer shows) and never touches Tcl. Where Tk is
  still used -- Linux, macOS, and Windows if the shell dialog fails -- it runs
  with TCL_LIBRARY and TK_LIBRARY cleared first, since a stale one left behind
  by some other program is the usual reason Tcl cannot start, and with the tcl
  folder shipped alongside this Python pointed at instead when it exists. If
  every dialog fails the page offers to type the path in, so the answer is
  never "you cannot add a folder".
- A folder path is checked before it is linked. Typing one by hand makes that
  possible for the first time, and a path that is not a readable directory is
  refused with the reason rather than stored and silently scanning nothing.
- Dragging a picture in from a browser works. Firefox hands a picture from a
  web page over as a promise of a file rather than a file, and the drop
  arrived with dataTransfer.files empty. Nothing claimed the drop, so the
  webview did what it does with an unclaimed one and navigated to the picture,
  taking the app off the page -- which is why it looked frozen and had to be
  restarted. The page now reads promised files through the entry API, claims
  every drop it sees so the webview can never navigate away again, and can no
  longer be left with an import overlay it forgot to take down.
- Clicking a picture once selects it and it stays selected. Selecting on the
  press (v4.40, so a drag knows what it carries) and toggling on the click
  were two halves of the same gesture undoing each other: the press selected,
  the click saw it selected and unselected it. Only Ctrl-click worked, because
  the press leaves Ctrl-clicks alone.
- A TrackImage button next to Explorer in the detail panel opens the picture
  where it lives inside the app: the folder is filtered to, the tree opens
  down to it, and the picture itself is scrolled to and selected.

## v4.45
- A duplicate group's percentage is the WORST pair in it, not the average. A user
  reported groups presented as "100% similar" holding pictures that plainly were
  not -- the same figure with a hand raised in one and lowered in the other. The
  hash had always seen the difference: measured on their own, that pair is 27%
  apart. What hid it was the headline, which averaged every pair in the group.
  Groups are cliques, so ten images means forty-five pairs; forty-four identical
  ones dilute a single real difference into nothing. From twelve images upward,
  one genuinely different pair disappeared into a group still calling itself
  100%. Because every member is within the threshold of every other, the worst
  pair is the number that actually means something: EVERY picture here is at
  least this close to EVERY other.
- 100% now means a distance of zero and nothing else. It used to be reached by
  rounding -- a distance of 1 came out as round(99.6) = 100 -- so a measurably
  different pair was reported as a perfect match. Everything else rounds down
  as well: 98.8% reads as 98, never 99. The number is a floor the pair is known
  to clear rather than a generous reading of it.
- Both apply everywhere a percentage is shown: groups, the single-image search,
  and the "already in your library" note after an import.
- Nothing about detection changed. The same pictures are found and grouped as
  before, at the same thresholds, from the same hashes -- no re-scan, no
  re-hashing. Only the number attached to a group is now one it can keep.

## v4.44
- Deleted pictures no longer come back. If TrackImage is installed inside the
  folder it scans -- which is a perfectly reasonable place to put it -- then its
  own Databank/.trash sat inside the library, and deleting a duplicate simply
  moved the file somewhere the scan would find it again. A user's log shows the
  moment: "Folder sync: 10 new" immediately after he deleted ten images, then
  those ten read straight back in as .trash entries, where they reappeared as
  duplicates of the very pictures he had chosen to keep.
- TrackImage now never reads its own working folder -- Databank, Logs, Static,
  venv, models and the trash inside them -- wherever it has been installed. The
  test is done on the resolved real path, so a junction or a symlink pointing
  back inside cannot get around it.
- Entries already read out of the trash are removed on start-up, and it says how
  many. The FILES are not touched: what is in the trash stays there and leaves on
  its usual timer, so nothing that could have been restored is lost.
- Also skipped now: $RECYCLE.BIN, System Volume Information, .git, .svn,
  __pycache__, node_modules, lost+found and the hidden folders macOS keeps. Only
  exact folder names count, so a real album called "Trash Panda Art" or "Git Gud"
  is scanned like any other.
- This is also why the Duplicates page kept flipping back to the gallery for that
  user and almost never for anyone else. Every deletion of his produced a folder
  change, and a folder change is what set off the refresh that redrew the page.
  The redraw itself was fixed in v4.42; its trigger is fixed here.

## v4.43
- Fixed the crash that made TrackImage look frozen. A user's log shows every one
  of his 27 worker threads dying inside the same second with "too many SQL
  variables", after which the progress bar sat at 9,274 images of 53,000 and
  nothing moved again. He restarted, reasonably concluding the program had hung.
- What happened. The queue excluded images it had set aside by naming each one as
  its own SQL parameter -- "id NOT IN (?,?,?,...)". His network drive stopped
  answering mid-run, so every read timed out and every image was set aside in
  turn. At 32,754 set aside, plus the images in flight, the list crossed SQLite's
  limit of 32,766 parameters and the query stopped being legal. Nothing named in
  SQL any more: a short page of candidates is read and the skipping happens in
  Python, so the query costs the same whether nothing has been set aside or the
  whole library has.
- That list is also why it crawled long before it crashed. The query runs while
  holding a lock every worker needs, so one that grows with each failure holds up
  the entire pool -- which is why failures arrived one every sixteen seconds
  rather than twenty-seven at a time, and why the interface went sluggish and the
  database started reporting itself as locked.
- The auto-tagger had exactly the same construction and would have died exactly
  the same way on a large enough library. Fixed with it.
- A drive that goes quiet no longer costs a library. "Cannot reach the file" and
  "cannot make sense of the file" were the same answer, so a share that stopped
  responding wrote off 52,000 perfectly good images in one morning -- files that
  read without a complaint that evening. Being unable to read a file is now its
  own outcome: the pool waits, a little longer each time up to a minute, and
  carries on the moment a read succeeds. Nothing is marked bad, nothing loses its
  place in the queue.
- Background processing can no longer stop in silence. An unexpected error is
  caught, written to the log with its traceback, and retried before that worker
  gives up; if the pool does stop, Settings says so and why, with a Resume
  button, instead of showing a progress bar that has quietly stopped moving.
- Start-up says so when Python is outside the tested range. Every release is
  checked against 3.10, 3.11 and 3.12. Newer usually works -- the user above is
  on 3.14 -- but it belongs in the log before anything else gets investigated.

## v4.42
- The duplicate slider goes down to 0. It stopped at 5, so the one question it
  could not answer was the strictest one: which of these files are byte-for-byte
  the same picture rather than merely alike. 0 means an identical hash. The
  server had always accepted it; only the control refused to offer it.
- Setting it to 0 now sticks. Reading it back was written as `S.dupThreshold||5`,
  and zero is false in Javascript, so a slider dragged to 0 silently snapped to
  5 -- the reason simply lowering the minimum would not have been enough.
- Fixed: the Duplicates page replaced itself with the ordinary gallery, roughly
  ten seconds after deleting anything. The auto-sync rebuild checked whether the
  detail view was open and nothing else, while the function that draws the main
  area always draws the GALLERY and knows nothing about which page is showing.
  Deleting files makes the folder watcher report a change, which is what set the
  rebuild off -- so the page appeared to jump back on its own, with Duplicates
  still highlighted in the topbar because the page had not actually changed.
  Auto-sync now leaves any page but the gallery alone.
- Fixed by the same change: the page that would not scroll. Every one of those
  rebuilds put the scroll position back to the top, so on a library busy in the
  background the list kept snapping back while being read. The sidebar, tags and
  counts still refresh -- only the part being read is left where it is.
- A drag no longer shares a name with the right-click menu. The window's own drag
  introduced a variable called _cd, which is what showImageCtx already calls its
  own local; the two never met, but only because of where they sit.

## v4.41
- A file dropped into TrackImage is MOVED into the folder you have open, not
  copied. The original no longer stays behind in Downloads waiting to be tidied
  up by hand. Hold Ctrl while dropping to copy instead, the way Ctrl does
  everywhere else in Windows.
- Why this could not be done before. A drop through the browser hands over the
  file's bytes and its name and nothing else -- where it came from is withheld by
  the engine on purpose. With no source path there is nothing to move, which is
  why v4.39 could only ever copy. pywebview 5 supplies the missing half: it sees
  the same drop from the Windows side, where the real paths are. The page now
  asks Python for those paths first and only falls back to uploading the bytes
  when there are none.
- Dropping a large file is no longer slow. The old road pushed every byte through
  HTTP before anything was written; a move on the same drive is a rename and
  takes the same instant whatever the file weighs.
- Nothing can be lost on the way. On one drive the move is a rename, which either
  happened or did not -- there is no moment where the file exists in neither
  place. Across drives it is copied first, the copy is checked to be the same
  size, and only then is the original removed; if that check fails the half-copy
  is thrown away and the original is left untouched.
- Ctrl+Z puts them back. An import that took files out of their old folder is
  undoable, and undoing walks each one back to the exact path it came from and
  forgets it again. A file that was copied has nothing to undo, and does not
  offer it.
- A file that is already in your library changes FOLDER instead of being added a
  second time. Dragging one in from Explorer used to leave the old entry pointing
  at a file that had moved and put a second entry beside it.
- It always says which of the two happened. "Moved" is only ever used when the
  original really is gone from where it was. A browser tab, a phone, or a
  pywebview older than 5 cannot know the path, so those keep copying and the
  message says copied.
- Also refused rather than done quietly: a file dropped into the folder it is
  already in, and one that vanished between the drop and the import.

## v4.40
- Dragging out of the app window works again, and this time from the full view
  as well. Drop a tile or the open picture onto Explorer, Discord, an upload
  dialog or the desktop and the ORIGINAL FILE arrives -- original name, original
  bytes, nothing re-encoded. Several selected images travel together.
- Dragging INSIDE TrackImage is untouched: a preview follows the cursor, the
  folder under it lights up, letting go moves the files there. That preview now
  exists in the full view too, which never had one.
- How the two live side by side. WebView2 still refuses to be a drag source, so
  the app window draws the drag itself instead of asking the browser engine for
  one. Python watches the cursor, and the moment it is over a window belonging to
  another program it starts the real Windows drag (DoDragDrop) with the original
  files. That is what v4.13 could not do: it had to switch the ordinary drag off
  to work at all, which is why moving images into a folder broke and why the
  whole thing was removed in v4.30.
- Being maximised no longer matters. The obvious test -- has the cursor left the
  window? -- is wrong whenever TrackImage fills the screen and the target program
  floats on top of it. The window under the cursor is asked instead, through its
  ROOT window, since WebView2 draws the page from a separate process and would
  otherwise look like a foreign program at the very first pixel.
- A file handed to Windows and then dropped back onto TrackImage is recognised
  and ignored. Without that the v4.39 import would have written a copy of each
  original right next to itself.
- A drag can no longer fire without a gesture. The Windows drag is only started
  while the left button is genuinely still down; if it came up in the meantime
  the files are simply left on the clipboard instead of being dropped wherever
  the cursor happened to be.
- Fixed: the full view could not be dragged at all, not even to the clipboard.
  A CSS rule from the v4.30 zoom rework switched dragging off on the picture
  permanently, when it is only needed while zoomed in, where the mouse belongs to
  panning. That is why a drag from the full view did nothing whatsoever.
- Unchanged everywhere else. A browser tab, Linux and macOS are real drag sources
  already and keep the drag they had. If pywin32 is missing, the app window falls
  back to the clipboard exactly as v4.39 did, and says so.

## v4.32
- The network address is found without reading localised text. The previous
  version parsed netsh output for "configuration for interface" and "ip
  address:"; on a German Windows those lines read differently, so nothing
  matched, no adapter was classified, and a VPN tunnel was offered as the
  address to type into a phone. PowerShell returns objects whose property names
  are English on every install, and Get-NetAdapter states outright whether an
  adapter is virtual -- so a real network card is now identified as such rather
  than guessed at from its name.
- Sharing switches on and off without a restart. app.run() fixes its address for
  the life of the process; the server now runs on werkzeug's make_server in a
  thread, so the socket can be re-bound while the database, the watcher, the
  tagger and the open window carry on. Measured at about a second, with the old
  address restored if the new one cannot be opened.
- Database, NAS and sharing are one tab, "Data & Network". They kept pointing at
  each other across two tabs for what is a single subject: where the data lives
  and who can reach it.
- Full view sharpness is a setting. Switching to real pixels at 1.15x made
  ordinary zooming look blocky almost at once, when at that point you are still
  looking at the picture rather than inspecting it. The threshold is now a
  slider in Interface & Gallery, defaulting to 400%, with Off for always-smooth.
  The detail view still loads nothing but the original file.
- Phone tiles no longer run off the edge. The row builder used the desktop
  column count, so on a narrow screen the target width hit its floor and rows
  overflowed instead of wrapping. Columns are derived from the actual width
  below 820px, and a final check scales any row that would still exceed it.
- Hiding the detail panel on a phone gives the image the whole screen instead of
  leaving a 44px strip. A floating button brings the panel back.
- "Duplicate compare: N pairs..." is logged when the answer changes rather than
  every few seconds. With autosync on, each idle pass of the worker pool
  recomputed the cache and logged the same numbers again.

## v4.31
- The address shown for sharing is the one that actually works. Listing every
  adapter produced two, one of them a VPN tunnel that exists only inside this
  machine and is unreachable from anywhere else. Tunnel adapters are recognised
  by name and set aside, and an address a device has genuinely connected on
  outranks every guess -- that is evidence rather than inference.
- The port is shown with the address, and a QR code next to it so a phone can
  scan instead of typing an IP by hand. qrcode is optional: TrackImage falls
  back to the plain address if it is missing.
- The interface works on a phone. It was built for a desktop window -- two fixed
  sidebar columns, a dozen topbar controls in one row, a 196px settings rail --
  and on a 400px screen that left a squeezed layout with controls pushed off
  the edge entirely. Below 820px the shell is single-column, the sidebar is a
  drawer that opens on a tap and closes once a filter is picked, the settings
  rail scrolls horizontally, and every control is a finger-sized target. The
  search field is 16px so iOS stops zooming the page when it is focused.

## v4.30
- The native drag is gone. It required HTML5 drag to be switched off for it to
  work at all, and once v4.28 made it wait for the pointer to leave the window
  there was no drag left INSIDE the window -- moving images into a folder stopped
  working entirely. Dragging out now goes through the webview as it does on Linux
  and macOS, with Ctrl+C as the fallback.
- Ctrl+C in the detail view respects a text selection. It fired unconditionally,
  so selecting the dimensions or the creation date and pressing Ctrl+C put the
  image FILE on the clipboard -- the one thing that was not selected. The file is
  only copied when nothing is selected, and the metadata panel is selectable.
- Full view renders at the image's natural size. It was laid out at width:100%,
  so a 1792px image was rasterised down to the window (~800px) and every zoom
  magnified THAT -- detail already thrown away could never come back. 100% is now
  a true 1:1 pixel match, the percentage is shown while zoomed, and past 1:1 the
  rendering switches to real pixels rather than a blur. Smaller images still fill
  the window, aspect ratio intact. The source was never the problem: /full/ has
  always served the untouched original bytes, and still does.
- Settings names the work in progress instead of showing an unlabelled dot, and
  the poll refreshes auto-tagging state too -- the tag category never lit up.
- Network sharing, off by default, under a new Settings tab together with the NAS
  options. Switching it on opens the port to the LAN behind a password (default
  1234, changeable, four characters minimum). Every remote request is gated,
  including the API, because deleting a folder is an API call. This machine is
  never challenged, settings can only be changed here, and ten wrong guesses buy
  a five minute pause.

## v4.29
- DirectML was being configured wrongly, and the probe was configuring it wrongly
  too. ONNX Runtime documents that the DML provider does not support the
  memory-pattern optimiser or parallel execution; both were left at their
  defaults, which makes session creation fail or behave erratically. The tagger
  and the probe now both set enable_mem_pattern=False and ORT_SEQUENTIAL whenever
  DML is in play, so the probe finally tests the runtime the way the app uses it.
- Auto-tagging ran up to twenty worker threads calling run() on one shared
  session. CUDA tolerates that; DirectML does not, and it is documented not to.
  Inference is serialised with a lock only when DML is the bound provider, and
  the worker count drops to one there -- threads taking turns on a lock is
  strictly worse than one thread, and each waiting thread still holds a decoded
  image in memory.
- The probe runs an inference instead of only building a session. DirectML
  failures are routinely thrown by the first or second run(), not by
  construction, so the old probe could report a healthy runtime that then took
  the program down on its first real image.
- The GPU is benchmarked against the processor once per runtime, and the result
  is shown in Settings. For this model the published evidence runs from a clear
  win on a discrete card to a loss against a well-threaded CPU on integrated
  graphics, and no benchmark exists at all for it on AMD -- so it is measured on
  the machine it is running on rather than assumed from the vendor name. When the
  processor wins, TrackImage says so and points at the CPU runtime.

## v4.28
- Switching to DirectML still closed TrackImage, and the reason was the one the
  CUDA test made obvious: installing CUDA into a fresh venv works because nothing
  is loaded yet, while switching afterwards pulls the floor out from under a
  running session. _get_tagger() returns early when a tagger already exists, so
  the guard added in v4.26 was never reached -- the live session kept its CUDA
  libraries mapped, pip rewrote those files underneath it, and the next call into
  the session landed in a library that no longer matched the one beside it. A
  swap requested while onnxruntime is loaded is now recorded and carried out at
  the next start, before anything has imported it, which is the only moment it is
  actually safe. Python cannot unload a native library; there is no in-process
  version of this that works.
- preload_dlls() only runs when CUDA is really the provider. It maps the
  nvidia-*-cu12 libraries, and doing that in a DirectML build pulled a second
  vendor's libraries into the address space for no reason. The CUDA wheels are
  also removed when leaving CUDA, rather than left behind.
- The working indicator covers the phases that actually take time. It watched
  only the embedding pass and the tagger, and tested p.thumbs.pending -- a field
  that does not exist, so the thumbnail back-fill never lit it. The folder scan,
  the back-fill and the unlink were all silent. The same wrong field was in the
  settings navigation. It now names the phase it is showing, survives a page
  change, and is polled so a dropped event stream cannot freeze it.
- A native drag starts only when the pointer leaves the window. It used to fire
  after five pixels of movement anywhere inside it, so panning a zoomed image was
  read as dragging the file out and the shell opened Windows Photos.

## v4.26
- A normal start can no longer delete the library. The startup sweep removed
  every image row that did not match a linked folder by string prefix, which
  inverted a safety net into a demolition crew: a folder linked as a mapped
  drive stores its images under the UNC path it points at (or the other way
  round), matches no prefix, and the entire collection was wiped before the
  window even opened. An empty scan_folders table deleted everything outright.
  An unlink now writes the folder it is removing into a new pending_unlink
  table, committed before anything is touched, and the sweep only finishes THAT
  folder. It also refuses to act when the marker would cover more than a fifth
  of the library -- one interrupted unlink cannot legitimately be most of a
  collection, so at that point the paths are wrong, not the rows.
- Rows that match no linked folder are reported instead of deleted. The count
  appears in Settings with a button to remove them, and the check runs in the
  background after the server is up rather than as a full table scan blocking
  the start -- on a large library that scan kept port 5001 closed long enough
  for the launcher to give up, which looked exactly like a frozen program.
- Closing the window can no longer leave the process behind. The tidy-up before
  exit walks the trash and waits on the file watcher, both of which can take
  minutes on a slow or disconnected network drive; the process then sat holding
  port 5001 with no window to show for it. Tidying now gets three seconds and
  the process leaves regardless -- the trash is swept again on the next start.
- Starting a second time says what is happening. When something holds port 5001
  but no TrackImage window can be found, the launcher used to exit without a
  word, so clicking it appeared to do nothing at all. It now names the process
  holding the port and the command to close it.
- The duplicate scan shows a rate and an expected finish time. A percentage on
  its own cannot tell slow from stuck: over a network share this phase reads
  well under two images a second, and one user waited four and a half hours at
  68% before reasonably concluding it had hung.
- Installing DirectML closed TrackImage and it would not start again. The real
  cause was one function: _tag_runtime_available() answered "is the runtime
  usable?" by importing onnxruntime, and it is reached from _tag_notify() --
  which the pip progress callback fires every half second for the entire length
  of an install. So while pip was replacing onnxruntime's libraries, the server
  imported that very package twice a second. Catch it mid-write and the DLL that
  loads is half of one build and half of another: not a Python exception, an
  access violation, and the program is gone. The same call ran on the way up
  through _tag_ensure_running(), so once the installation was mixed it crashed
  the start too -- which is why TrackImage could not be opened afterwards.
  Whether the runtime works is now a verdict recorded by probe_runtime(), which
  does the dangerous part in a child process, and nothing else may grant it.
  Anything unproven counts as unavailable, the whole install is a no-touch
  window, and the tagger refuses to load until a child has actually built a
  session. Tagging switched off is a nuisance; a program that vanishes is not.
- v4.25 also fixed how the old runtime is removed and then verified the result
  with a plain import inside the running server -- the same unsafe move. If onnxruntime had already been imported, that import is a no-op
  against a module whose libraries pip has just replaced, so it reported success
  and the crash arrived later; if it had not, it loaded whatever mixture was on
  disk, and a mismatched native library does not raise a Python exception -- it
  ends the process on the spot. Verification happens in a child process now.
  Windows also cannot delete a DLL this process has open, and pip skips those
  files while still reporting success, so a runtime swap after tagging has run
  leaves both builds on disk whatever the installer does. Leftovers are detected
  and the switch asks for a restart rather than pretending it worked.
- After that crash, TrackImage would not come back. The startup check built a
  real ONNX session before the port was opened, with a three minute timeout, and
  a damaged runtime raises Windows Error Reporting on an invisible child process
  -- a modal dialog nobody can see, holding the start until it times out, long
  past the thirty seconds the launcher waits. The check now runs in the
  background after the port is open, crash dialogs are suppressed in the child,
  and the timeout is 45 seconds. With a damaged runtime present the port now
  opens in well under a second instead of not at all; tagging stays switched off
  until the check reports back, which is the safe direction.
- The fonts and the window icon ship with the program. Seven TTF files and
  static/trackimage.ico were listed as required and then left out of the
  package, so every install fell back to a system typeface and the generic
  Python feather in the taskbar.

## v4.25
- Switching to DirectML made TrackImage close itself and refuse to start again.
  Two faults, both mine. The old runtime was cleared out by testing whether one
  package name appeared inside another, and "onnxruntime" appears inside
  "onnxruntime-directml" -- so the processor build was never removed. Both then
  occupy the same onnxruntime folder and overwrite each other's libraries. CUDA
  had the same hole; that it worked was luck. Names are compared exactly now, and
  changing runtime removes all three first.
  The start-up check was also too shallow. It only tried to import the module,
  and a mixed installation imports perfectly well -- it dies later, building the
  session, in the tagging thread, which takes the program with it. The check now
  builds a real session in a separate process, which is the thing that actually
  fails.
- Dragging worked in the app window but not in a browser tab pointed at the same
  program. Whether this was the window was decided on the server and baked into
  the page, so a browser tab was told it was the app window, the HTML drag was
  switched off for it, and the native drag it was offered instead does not exist
  there. The window now identifies itself, so each client knows what it is.
- Settings can move TrackImage between its own window and a browser tab, and the
  choice is remembered. Window to tab happens straight away; tab to window needs
  a restart, because a window has to be created from the main thread. Either way
  it says what changes about drag and drop first.

## v4.24
- TrackImage could stop starting altogether, with a Windows error box about a
  read at address zero and nothing at all in the logfile. The start-up check
  introduced in v4.14 imported onnxruntime to see whether it was usable, and that
  import loads the CUDA libraries into this very process. A library that is
  damaged or does not match its neighbours does not raise a Python error there --
  it takes the process down. Auto-tagging used to be loaded only when tagging
  actually began, so this could never happen at start-up before; that was my
  doing.
  The heavy modules are now tried in a separate process with a time limit.
  Whatever happens to it -- an exception, a crash, a hang -- comes back as an
  exit code, and TrackImage says which module is at fault and offers to repair
  it. A broken installation is a message now, not a dead program.
- Starting while an instance is already running brings that window to the front
  instead of opening a second one onto the same address. Two windows on one
  instance was never intended and is a poor idea besides -- each one starts its
  own browser engine.
- If the program does die at the Windows level, the launcher says so plainly and
  explains that trackimage.log will be empty because Python never got to write
  anything, rather than leaving that to be worked out.

## v4.23
- The runtime choice sits next to the install button instead of in a card above
  it. It decides how big the download is -- 2.5 GB for CUDA against 25 MB for
  DirectML -- so it belongs on the same line as the button, and the button now
  names the size that actually applies rather than always saying 3.7 GB.
- Which card was found, which runtime it leads to and why are one line under that
  same button. They were in a separate card further up, which meant reading two
  places to answer one question. Once auto-tagging is installed the same block
  shows the runtime in use and offers to reinstall with a different one.

## v4.22
- The Windows launcher works again. v4.21 put each package's description in
  brackets and echoed it from inside an if(...)else(...) block; cmd expands the
  variable BEFORE it parses the block, so the ")" in "the app window (instead of
  a browser tab)" closed the block early and everything after it was skipped.
  The packages installed and then no window ever appeared. The descriptions no
  longer contain brackets and the block is gone entirely -- plain jumps cannot
  fail that way. A checker for the launcher now runs before release: it refuses
  a description containing a character cmd treats specially, and it verifies
  every label jumped to exists and that the file still reaches the step that
  starts the program. It reproduces the v4.21 fault on the old file.
- What the launcher prints during setup shows up in the console under Settings.
  All of it happens before Python starts, so the console never had any of it --
  the very moment somebody wants to look back at what was installed. The
  launcher writes the same lines to install.log and they are replayed at
  start-up, so the whole record sits in one place.

## v4.21
- The launcher says what each package is FOR, not just its name: "installing
  pillow-heif (iPhone HEIC photos)". A first install should be readable by the
  person running it -- nothing here should look like a mystery dependency.
- The Auto-tagging page is the right way round. Which card is in the machine and
  which runtime it will use now sit ABOVE the download button rather than below
  it, so it is clear what is about to be fetched, and why, before 2.5 GB starts
  moving.
- The repair button is findable. It used to appear only once something was
  already damaged -- exactly the moment nobody can find it. It now lives under
  Help & Reference, permanently, next to the health check. On a healthy install
  it says so and offers to reinstall the runtime anyway, which is the usual
  answer when tagging misbehaves for no visible reason.

## v4.20
- AMD and Intel graphics can do the tagging now. Until today the installer fetched
  the CUDA runtime whatever card was in the machine: an AMD owner downloaded
  2.5 GB of NVIDIA libraries that could never run, and then tagged on the
  processor anyway. The card is identified first, and the runtime that matches it
  is installed -- CUDA for NVIDIA, DirectML for AMD and Intel on Windows, the
  plain processor runtime where neither applies. Nothing about an existing NVIDIA
  install changes.
- The runtime can also be chosen by hand, because the two differ enormously in
  size: CUDA is about 2.5 GB and the fastest thing an NVIDIA card has; DirectML is
  25 GB smaller at 25 MB and works on every DirectX 12 card, at some cost in
  speed. Switching is one button and a restart.
- TrackImage checks its own installation and can repair it. pip records the
  sha256 and the size of every file it writes, so a library that arrived
  truncated -- a download cut short, a disk that filled up -- can be named
  exactly rather than guessed at. Before, this showed up much later as an
  unexplained fall back to the processor with no reason given. The check runs at
  start-up and reports; repairing reinstalls the affected package without using
  pip's cache, since the cache would hand back the same damaged file.

## v4.19
- The console was drowning in logging errors. Every detail line went into the
  logfile as well, so the 2 MB mark arrived within minutes instead of weeks; from
  then on each new line tried to roll the file over, the rename failed because
  something else on the machine held it open, and Python printed a
  twenty-five-line traceback about it. With twenty tagger threads that is
  hundreds of tracebacks a second, all of them going through the console buffer
  and out to the browser.
  Three things now prevent it. Detail lines go to the console only and never
  touch the logfile, so it grows at the pace it always did. A rollover that
  fails is ignored and writing simply carries on with the current file, which is
  what a logfile should do when it cannot be renamed. And logging no longer
  reports its own failures to stderr at all, so nothing like this can flood the
  console again.
- Detail is always on. There is no switch for it any more: the console says what
  is being opened, generated, embedded and tagged, all the time. It costs nothing
  now that those lines stay out of the logfile.
- The outline around a selected image is a little heavier and brighter, so it
  stays visible on pale pictures.

## v4.18
- Settings would not open. Not during an import, not after it, not at all: v4.16
  left a reference to a variable that only exists inside a string built for a
  slider's oninput handler, never in the function itself. It threw on every call,
  and because the page is drawn from an async function whose rejection nobody
  catches, the failure was completely silent -- the click simply did nothing.
  Fixed, and found by calling the function in a real DOM rather than by reading it.
- Settings is now drawn before its data arrives. The frame and the navigation come
  up immediately and the cards replace them when they are ready, so a slow call
  can no longer hold the page back. If building the cards fails, the page says so,
  with the actual error, instead of leaving a dead button behind.
- The progress bar over the gallery is gone, as requested. The spinner in the top
  bar already reports background work.

## v4.17
- The window stopped answering while a folder was being taken in, and this time
  the cause was in the page rather than the machine. Every time the watcher
  reported new files the gallery was rebuilt from scratch: the whole grid string
  regenerated and dropped into the DOM, which throws away every <img> in it. The
  browser then re-requested every thumbnail already on screen -- competing with
  the import that was producing them -- and the main thread stayed busy long
  enough that clicks, the Settings button included, never landed. The grid is now
  brought up to date in place: tiles that are already correct are left exactly
  where they are, new ones are inserted between them, and only a tile whose
  thumbnail actually changed is rebuilt. Nothing the user is looking at is
  discarded, so nothing the user is looking at has to be fetched again.
- A sync also used to drop the gallery back to the first 60 images, so during an
  import the view collapsed under anyone who had scrolled. It now reloads as far
  as the user had already got.
- Auto-sync waits a second before redrawing rather than 300 ms. During an import
  the reports arrive faster than that, and redrawing on each one was work nobody
  asked for.
- The progress bar in the gallery follows the live progress events, so it moves
  on the gallery page as well. It only updated while Settings was open, which is
  the one place it was not needed.

## v4.16
- The model download was rejecting perfectly good files. v4.15 held the finished
  download against the ETag HuggingFace sends, on the assumption that it is the
  sha256 of the file. It is not: a small file returns a 40-character git hash, and
  a large one served from Xet storage returns a 64-character Xet content hash --
  the right length to look like a sha256 and the wrong number entirely. Every
  download therefore failed with "checksum mismatch" and started over. The
  comparison is gone. What actually guarantees the file is the per-stream check
  added in v4.15 -- every range must answer 206, name the range it was asked for,
  and deliver exactly the promised number of bytes -- and the tagger deleting a
  file it cannot parse. Those are both kept. The sha256 is written to the log once
  so a known-good value can be pinned later if it is ever wanted.
- Auto is gone from the worker sliders. There is no longer a position past the end
  of the scale that means "decide for me": the sliders run from 1 to the number of
  logical processors, they start at 85% of them, and they always show both the
  count and the share. A slider that reads 20 and 83% says what is happening; one
  that reads "Auto" at the far right said the opposite of what it did.
- Starting is quicker and no longer silent. After the console closed, the launcher
  waited for the app to answer by starting a fresh Python interpreter up to twenty
  times over, with a pause between each -- most of the delay was the waiting
  itself. One interpreter now does the whole wait, and it says what it is doing
  instead of leaving a blank window.
- The console resize grip works. It was hooked up when the panel was drawn, which
  is not reliably after the panel exists, so on most visits it was never hooked at
  all -- the cursor changed on hover and nothing moved.

## v4.15
- The auto-tagging model could arrive corrupt and stay that way. It is fetched
  over six parallel range requests, and nothing checked that the server had
  honoured the Range header at all -- HuggingFace redirects to a CDN, and a
  redirect can drop it, so a stream answers 200 with the WHOLE file and writes it
  from its own offset over everybody else's. The file ends up exactly the right
  length, because it was pre-sized, and complete nonsense inside: "Protobuf
  parsing failed". Every stream now has to answer 206, its Content-Range has to
  say what was asked for, and it has to deliver exactly as many bytes as it
  promised. The finished file is checked against the checksum HuggingFace
  publishes, and if the tagger still cannot open it the file is deleted so the
  next attempt fetches it again instead of failing forever.
- Auto means the same share everywhere now. Three of the stages still read it as
  every logical processor while the other two had moved to 85%, which is why the
  sliders disagreed -- Processing power and Worker threads said 24 while Compute
  and Thumbnails said 20. All five, auto-tagging included, come from one number.
- Both readings stay on the sliders while dragging. The percentage used to vanish
  the moment the handle moved and only came back on release.
- The console can be resized by dragging its top edge. The earlier attempt set a
  CSS handle that a more specific rule overrode, and that handle sat at the
  bottom of the panel, off the screen.
- The console keeps its history properly. The "Waiting for output" placeholder
  counted as content, so the panel appended to it instead of painting the log
  back in, and looked empty on every return to Settings.
- New Detail switch in the console, where the HTTP checkbox used to be. With it
  on, the log says what is being opened, generated and tagged, file by file --
  which is what the console was being opened to find out. Off by default, because
  on a library this size it is a lot of lines.
- The activity marker on the Settings tabs is the same spinner the main page uses,
  and it goes away when the work does.

## v4.14
- Deleting a group of duplicates took ten to fifteen minutes and ended in a
  freeze. The bulk delete asked the pair cache to forget ONE image at a time, and
  each of those asks counted every hashed image in the database and rebuilt the
  whole pair list from scratch. Deleting nine images meant doing that nine times
  over. It is done once for the whole batch now, and the duplicate groups are
  trimmed in place instead of being thrown away -- so the page stays where it is
  and there is nothing to re-scan afterwards.
- The window stopped answering while a folder was being taken in. Every compute
  worker asked Windows for ABOVE_NORMAL priority, so twenty-four of them
  outranked the interface and the Settings button could not even be clicked.
  Workers now run BELOW_NORMAL and keep their opt-out from the efficiency cores:
  the same speed when the machine is idle, and the interface wins whenever it
  needs to.
- Auto no longer means every last core. It means 85% of them, so something is
  always left for the interface, the disk and the rest of the system. The sliders
  say what that is in percent as well as in numbers.
- The console panel can be dragged taller, and it no longer starts over every
  time Settings is opened -- it keeps what it had and simply carries on. It also
  remembers more history than it used to.
- The HTTP checkbox is gone. It hid the web server's own chatter, which nobody
  wants to read; that chatter is now always hidden, while failed requests stay
  visible because those are worth seeing.
- "Advanced - set each stage separately" folds away, and the Processing and
  Auto-tagging tabs show a spinner while their stage is working, so it is
  visible WHERE the work is happening without opening each tab.
- The gallery shows a progress bar while a fresh library is still being taken in,
  instead of looking finished while thousands of images are still queued.
- The start-up check looks at the virtual environment as well: a package that
  failed to install completely is named instead of surfacing later as an
  unexplained crash.
- The launcher says which package it is installing rather than only "checking
  dependencies".
- New icon, and the archive is tidier: the loose image in the root folder is
  gone, and ignored_tags.txt is written the moment there is something to write
  instead of shipping empty.

## v4.13
- Real drag-out of the app window on Windows. A tile or the full view can be
  dragged straight into Explorer, WhatsApp, Discord or an upload dialog and the
  ORIGINAL FILE arrives -- original name, original bytes, nothing re-encoded.
  WebView2 refuses to be a drag source, so the gesture is recognised in the page
  and the drag is then run by Python itself through the OLE call Explorer uses,
  DoDragDrop. Several selected images travel together: a native drag carries a
  whole file list, which an HTML drag never could.
- Linux and macOS drag out as well, by a different and simpler road: inside the
  window the drag carries a file:// address of the original, which is what a file
  manager on those systems expects.
- Everything the program needs now ships with it. The interface asked for seven
  font files and the window asked for its icon, and neither was ever in the
  archive -- the fonts silently fell back to a system face and Windows showed the
  generic Python feather. static/ with the fonts and both icons is part of the
  release from here on, and a start-up check names anything missing in the log
  instead of quietly limping on.
- New switch in Settings > Interface: "Native drag out of the window". On by
  default; turning it off restores the v4.12 behaviour (files go to the clipboard)
  without needing an older version.

## v4.12
- Dragging a tile or the full view now hands over the ORIGINAL FILE with its
  ORIGINAL NAME and ORIGINAL BYTES. The drag no longer offers the generated WebP
  thumbnail: thumbnail and full view are two views of one file, so both drag that
  one file. Nothing is re-encoded, re-compressed or renamed on the way out.
- New route /file/<id>. It streams the untouched file from disk and names it in
  Content-Disposition, so the receiving program writes "sunset_final.png" and not
  "4711". /full/ is unchanged and keeps serving the viewer.
- A drag now carries four formats instead of one, so every kind of target gets
  something it understands: DownloadURL (the real file, Chromium), text/uri-list,
  text/html (an <img> pointing at the original), and text/plain -- which finally
  holds the FILE NAME. It used to hold an internal ID array, which is what landed
  in a text editor or a chat box when the target could not take a file.
- The duplicates and similar-images pages can be dragged from as well. They were
  the only galleries without it.
- Clipboard ownership fixed. OpenClipboard was called with a NULL window handle;
  Windows documents that this sets the clipboard owner to NULL and makes
  SetClipboardData fail. The clipboard is now owned by a message-only window
  created for the purpose, so copying a file to the clipboard works in the app
  window for the first time.
- Dragging several images at once puts all originals on the clipboard and says
  so, because a browser drag can only ever carry one file.

## v4.11
- Copying to the system clipboard did nothing at all in v4.10. The Win32 calls
  were made without declaring their signatures, so ctypes marshalled every
  argument as a 32-bit int. On 64-bit Windows GlobalAlloc returns a 64-bit
  handle, and that handle arrived truncated at GlobalLock and SetClipboardData --
  the call could not succeed. Every signature is declared now, the libraries are
  loaded with use_last_error, and a failure carries the Windows error number.
- A failed copy is no longer silent. Ctrl+C asked the backend in "quiet" mode,
  and quiet suppressed the error as well as the confirmation, so a broken
  clipboard looked exactly like a copy that had never been attempted. Quiet now
  only holds back the success message; every failure reaches both the toast and
  the console panel, and every attempt is logged either way.
- Opening the clipboard is retried for half a second. Another program holding it
  for a moment is normal on Windows and is no longer an instant failure.

## v4.10
- Copying finally hands over the ORIGINAL FILE. Ctrl+C, the Copy button and the
  context menu now put the file itself on the system clipboard, so it pastes into
  Explorer, chat windows and upload dialogs as the file it is -- not as a picture
  and not as a link. A browser can never do this; the Python process can, through
  CF_HDROP, which is exactly what Explorer itself uses for Copy. The paste is
  marked as a copy, so nothing can move the originals away.
  TrackImage's own clipboard for moving and copying between folders is untouched
  and works exactly as before -- Ctrl+C now simply serves both.
- "Copy as picture" added to the toolbar and the context menu for image editors
  that want a bitmap rather than a file.
- The full view joins in: its picture can be dragged like a tile, and Ctrl+C
  copies the file that is open.
- Dragging out of the app window cannot work. WebView2 accepts a drop but is not
  an OLE drag source, so a file dragged out never reaches the target program --
  that is a limit of the embedded control, not of TrackImage, and the move to the
  window in v4.0 took the browser's drag-out with it. Instead of letting the
  gesture die silently, the files go to the clipboard when a drag starts and a
  hint says so once. Dragging INSIDE TrackImage, between folders, is unaffected.
- macOS and Linux get the same two actions through osascript and
  wl-copy / xclip; where neither exists the reason is named instead of failing
  quietly.

## v4.09
- The console no longer drowns in its own polling. It asks the server for new
  lines roughly every 1.5 s, and the web server logged every one of those
  requests -- which the console then displayed. /api/console, /api/scan-progress,
  /api/hash-status and the duplicate poll join the filter that already silenced
  /api/processing/status and /api/events, so they reach neither the console nor
  the logfile.
- Web server request lines are folded out of the console by default. Anything
  that still arrives -- image and thumbnail requests while browsing, for instance
  -- sits behind an "HTTP" switch next to Copy and Follow and shows in a muted
  colour when switched on. They keep their place in trackimage.log either way;
  only the view is quieter, so the app's own messages are readable.

## v4.08
- The Settings cards no longer fold away. Every card had its own accordion on the
  heading, collapsed by default and remembered in localStorage -- that was why a
  freshly opened topic looked empty until the heading was clicked. The rail on
  the left picks the topic now, so the page is simply there. The accordion, its
  stored state and the arrow in front of the heading are gone.
- The heading inside the pane is gone with it. It repeated what the rail entry
  already says. Sub-headings inside a page, such as Thumbnails under
  Interface & Gallery, stay where they are.

## v4.07
- The Settings panes could come up empty. The pane to show was marked from a
  requestAnimationFrame after render(), which is a race: when the markup reaches
  the DOM after that frame, no pane is marked and all of them stay hidden. The
  visible pane is written into the HTML itself now, so it is correct on the first
  paint; clicking the rail still switches it afterwards.
- No collapsed blocks inside the Settings panes any more. "How it works",
  "Advanced", "Show columns", "Search & Ratings" and "How Tagging Works" were
  fold-outs; the rail on the left does the navigating now, so those sections are
  simply always open.
- The quick access toolbar is permanently visible. The tools button that folded
  it out is gone, and with it the stored open/closed state -- the icons are just
  there.

## v4.06
- The Settings page is rebuilt. An icon rail on the left holds the five
  categories -- Interface & Gallery, Processing, Auto-tagging, Database, Help --
  and the matching page fills the area on the right instead of every card being
  stacked into one endless column. The chosen category is remembered.
- The console is pinned to the bottom of the Settings page and always visible, so
  what the app is doing can be watched while settings are changed. It can be
  folded away by its header and remembers that too.
- start-windows-console.bat is gone. If the window ever fails to come up the
  launcher restarts TrackImage with a visible console rather than in a browser --
  no path leads to the browser on purpose any more. The --browser flag still
  exists as a last resort inside app.py.
- Linux and macOS start detached now: the terminal is free again right after the
  start and can be closed while TrackImage keeps running. Output goes to
  trackimage.log and to the console panel.
- Linux checks for the GTK bindings before starting and names the exact package
  for Debian/Ubuntu, Fedora and Arch. They cannot come from pip, and without them
  the window mode silently became a browser window. If it fails anyway, the log
  now says why per platform.

## v4.05
- v4.04 did not start at all: the console installed the dependencies, closed, and
  no window appeared. The window icon was to blame. pywebview only accepts the
  icon= argument on GTK and Qt and rejects it everywhere else; v4.04 passed it on
  every platform and caught TypeError only, so on Windows a ValueError escaped
  before the window was ever created. A cosmetic detail could stop the program
  from starting -- it now runs last and cannot fail the start: the argument is
  only used where pywebview supports it, and any error falls back to opening the
  window without it. The icon is still applied through the Win32 API, which was
  never the problem.
- The launcher checks readiness with Python instead of batch string juggling. A
  socket connect in one line replaces netstat piped into findstr, which produced
  two bugs in two attempts. If the app still does not come up, the console prints
  the last 25 lines of trackimage.log before restarting visibly, so the cause is
  on screen instead of having to be asked for.
- Starting while an instance is already running opens a window onto it as well,
  rather than a browser tab. That case also looked like "nothing happened".

## v4.04
- The window and the taskbar show the TrackImage diamond instead of the generic
  Python feather. pywebview draws its Windows window with WinForms, which
  inherits the icon of the running executable -- pythonw.exe -- and offers no way
  to override it, so the icon is pushed in through the Win32 API once the window
  exists, and an explicit AppUserModelID stops Windows from filing the window
  under the Python entry in the taskbar. GTK and Qt get the same logo as a PNG
  through pywebview itself. static/trackimage.ico carries seven sizes from 16 to
  256 px; the browser favicon already used the same shape.

## v4.03
- No more console windows flashing across the desktop. Every child process on
  Windows opens its own console unless it is told not to, and with pythonw there
  is no parent console to inherit -- so each ffmpeg call for a video thumbnail
  popped up a black box, one per file. All child processes now go through one
  helper that sets CREATE_NO_WINDOW: video thumbnails, video metadata, the ffmpeg
  probe at startup, the folder picker, the optional ExifTool call, "Open in
  Explorer" and the pip install for auto-tagging.
- Settings has a Console panel. Everything TrackImage would have printed to a
  terminal is kept in a ring buffer of 800 lines and shown live, warnings in
  amber and errors in red, with a Copy button and a "Follow output" switch. The
  tee sits on stdout and stderr, which is where both print() and the logger
  write, so nothing is missed. The same text still goes to trackimage.log.
  Polling stops as soon as Settings is left.

## v4.02
- The window opened, but the console stayed and a browser opened on top of it.
  The launcher's "did it come up?" check was written as
  "netstat | findstr && set UP=1" -- and the right-hand side of a pipe runs in a
  child shell in cmd, so the SET was thrown away and the check always read as a
  failure. The launcher then started a SECOND instance with console and browser
  while the window was running perfectly well. findstr now writes to a temp file
  and the result is read through ERRORLEVEL in a separate statement, with no pipe
  involved.
- A second start no longer fights the first one for port 5001. It used to crash
  on bind, which the launcher reported as "Server crashed!" although the running
  instance was fine. TrackImage now notices that the port already answers, opens
  the instance that is already there and exits quietly.

## v4.01
- start-windows.bat did not start anything: the console flashed and closed, and
  only the console variant worked. pythonw.exe hands the process
  sys.stdout = sys.stderr = None. print() then silently does nothing, but an
  unhandled exception goes to sys.stderr -- which is None -- so the traceback was
  lost and the process died without leaving a trace anywhere.
  v4.0 shipped the stream guard but only called it inside the compute workers;
  the main process ran unprotected. It now runs as the very first statement of
  the module, before any import that could fail, so every crash lands in
  trackimage.log. sys.stdin is replaced too -- multiprocessing/spawn duplicates
  that handle on Windows and cannot start the compute pool without it.
- The launcher no longer trusts the start. It checks that port 5001 is listening
  and, if nothing came up after ~15 s, restarts TrackImage visibly with console
  and browser so the error is on screen instead of nowhere. A venv without
  pythonw.exe falls back to the console straight away.

## v4.0
- TrackImage runs in its own window. pywebview hosts the interface in a native
  window -- WebView2 on Windows, WebKitGTK on Linux, WKWebView on macOS -- so no
  browser tab is involved any more. Closing the window shuts the app down and
  flushes the trash and the watcher exactly as the old tab watchdog did; the tab
  counter is switched off in this mode.
- No console window. The launcher keeps its console for the setup phase, because
  a first run installs packages for minutes and has to show that it is working,
  then hands the app over to pythonw.exe and closes. Under pythonw there is no
  stdout at all, so both streams are redirected to trackimage.log -- in the main
  process and inside every spawned compute worker, which would otherwise die on
  their first print().
- Nothing here is mandatory. pywebview is an optional dependency: if the wheel is
  missing or no webview runtime can be found, the old behaviour returns and the
  default browser is opened. Starting with --browser forces that on purpose, and
  start-windows-console.bat does both -- console and browser -- for diagnosis.

## v3.94
- Clicking a name or a tag a second time clears it again. Folders and star
  ratings already worked that way; these two set the filter to the clicked entry
  every time, so it could only be removed through its chip or through "All".
  Ctrl-click keeps toggling single entries, and a plain click while several are
  selected still narrows down to the clicked one.
- The star ratings are listed in the Tags column as well, pinned above the
  auto-tag ratings. They no longer need a switch to the Names column to be
  combined with a tag. "All" in that column stops showing as active while a star
  rating is on.

## v3.93
- Shift-click on folders now spans exactly what the tree shows. The range ran
  over the internal folder index, which also holds rows sitting inside a
  collapsed parent, so subfolders nobody could see joined the filter.
- The "&" between several folders on the duplicate page keeps the title colour;
  only the folder names are gold.
- Switching between the duplicate page and the gallery is clean now. Leaving the
  page cleared the poll timers, but a request that was already in flight still
  ran its callback to completion and called render() -- into a gallery that was
  loading at that moment. Every asynchronous load carries the navigation counter
  it started with and drops out if the page changed in the meantime. Leaving the
  duplicate page also cancels the background pair compare.
- A cancelled pair compare is no longer cached. It holds only part of the pairs,
  was stored under the current signature all the same, and the next open would
  have served that incomplete list -- the list images get deleted from. It is
  discarded now and recomputed on the next request.
- The region score and the heatmap are gone: the checkbox, the "Region flag"
  slider, the per-group "region NN%" badge, the tile-diff endpoint, the score
  helpers and the per-pair computation. They promised something the method could
  not deliver -- a watermark scored around 95% and never showed up, while
  genuinely different images scored low. The tile signatures stay in the
  database and are still written on import; nothing reads them any more.

## v3.92
- Folder selection follows the Explorer rules now. A plain click selects that
  one folder and drops whatever was selected before, Ctrl-click (Cmd on macOS)
  adds or removes a single folder, Shift-click takes the range from the last
  clicked folder. Clicking the already selected folder again clears the filter.
  In v3.91 a plain click added to the selection instead of replacing it, so
  every folder clicked stayed in the filter and the gallery kept growing.

## v3.91
- Adding a folder no longer fails with a 500. If none of the registered scan
  folders existed on disk at startup, start_watcher() left a created but never
  started Observer in the global, and the next stop_watcher() called join() on
  a thread that was never started. Every later "add folder" died on that.
  The observer is cleared on that path now, and stopping one can no longer
  raise regardless of how it got there.
- The local fonts are back in the release. static/fonts/ had gone missing from
  the ZIP, so all seven @font-face rules 404'd and the UI fell back to system
  fonts. DM Sans and Space Mono ship with the app again -- still no external
  request to Google.
- Quick access toolbar in the top bar, left of Find Duplicates. The tools
  button folds it out and remembers that across restarts. It carries the same
  actions as the right-click menu -- Explorer, move, copy, cut, paste, rename,
  edit tags, remove metadata, find duplicates, delete -- and both now use the
  same drawn icons instead of emoji. Remove metadata is gold in both places.
  Buttons that need a selection grey out until there is one.
- The folder tree and the tag groups keep their open/closed state across
  restarts, like the sidebar columns already did.
- "Subfolders" checkbox next to the info button, mirrored in Settings ->
  Interface & Gallery. On by default, which is the behaviour up to v3.90.
  Switch it off and an opened folder lists only the files sitting directly in
  it. Folder counts in the sidebar stay recursive.
- Several folders can be filtered at once. Ctrl-click adds or removes a folder,
  Shift-click takes a range, a plain click goes back to just that one. The
  gallery, the tag and name columns and both duplicate modes all follow the
  whole selection, so duplicates can be hunted across exactly two folders
  without touching the rest of the library. The duplicate page names them:
  "Duplicates in A & B", or "A & 3 more" beyond that.
- The API takes repeated folder= parameters and an optional subfolders=0 now.
  A single folder= without subfolders behaves exactly as it did before.

## v3.90
- XMP and IPTC metadata are read now. Downloaders such as Grabber write the
  creator, the keywords and the original filename through ExifTool, and
  ExifTool puts those into XMP and IPTC -- not into EXIF. TrackImage only ever
  looked at EXIF, so such a file showed nothing but its date and size and
  looked like it carried no metadata at all.
- XMP is read for a fixed set of fields: artist, title, description,
  copyright, original filename, creation date. Everything else in the packet
  is ignored on purpose, so Adobe-heavy files do not flood the panel.
- IPTC-IIM (the Photoshop APP13 block) contributes the same set plus its
  keyword list. Keywords from both sources are merged and de-duplicated.
- Both are parsed from what Pillow already hands over -- no ExifTool binary
  and no new dependency. EXIF still wins: XMP/IPTC only fill in blanks.
- Keywords are metadata, not tags: they show up in the panel and in search,
  and the tag columns stay ML-only.
- Fixed: a PNG carrying an XMP packet could dump the raw XML into the panel
  as an unnamed text chunk. It is parsed now instead of printed.
- Existing collections need one "Reprocess all" for the new fields; a fresh
  install picks them up on import.
- The duplicate group header is laid out with flexbox. The Ignore button hung
  in a float, which sits outside the line box -- so it was not vertically
  centred and it, not the text, decided the header height.

## v3.89
- Duplicate groups can be ignored. Intentional variants of the same picture kept
  showing up on every scan; the group header now has an Ignore button that files
  them away for good.
- Stored per PAIR, not per group: a group only exists at the current "max
  difference" setting, while the distance between two images never changes. An
  ignored pair therefore stays ignored at every slider position.
- If a new image joins an ignored set later, the group reappears -- the new pairs
  are not ignored, which is exactly the signal you want.
- The toolbar counts what is hidden and can show it again; each restored group
  gets its own Restore button. Nothing is ever deleted -- ignoring writes one row
  per pair, and deleting an image removes its rows via FK cascade.

## v3.88
- The runtime install shows live progress instead of one frozen line. pip ran
  under capture_output, which buffers everything until the process exits, so
  ~2.5 GB of CUDA wheels downloaded behind a static message that looked hung.
- pip is now read line by line. With pip >= 24.1 the machine-readable
  "--progress-bar raw" gives exact byte counts; older pip falls back to parsing
  the human bar, and if even that is missing the package name still updates.
- Two numbers are shown: the current wheel (exact) and an overall bar against
  the expected total (~2.5 GB GPU / ~15 MB CPU). The overall figure is an
  estimate and marked with a ~; it self-corrects if the real total is larger.
- The final unpack step reports "Installing packages" -- pip emits no progress
  there, so it stays a status line rather than a fake percentage.

## v3.87
- Unlinking a folder now removes it from scan_folders FIRST and wipes the image
  rows afterwards. Previously the folder row went last, so interrupting the wipe
  (reload, restart) left the folder registered -- and the next start re-scanned
  and re-imported the whole thing, as if the unlink had never happened.
- New startup sweep for the other half of that: image rows that belong to no
  linked folder any more are cleaned up. Files on disk are never touched, so
  re-linking the folder brings everything back.
- The tag_progress event now carries the runtime flag. Without it the Settings
  card fell back to assuming the runtime was installed, and the install button
  advertised ~1.2 GB instead of ~3.7 GB when neither part was present. Cosmetic
  only -- the button installed both parts either way.

## v3.86
- SQLite never shrinks its file on its own: deleting thumbnails only marks pages
  as reusable. Lowering the thumbnail resolution therefore freed nothing on disk.
  A VACUUM now runs automatically once a thumbnail regeneration finishes, and the
  Database card in Settings has a manual "Compact database" button with a
  before/after readout.
- The WAL is checkpointed and truncated around the VACUUM, so -wal and -shm do
  not keep the reclaimed space either.
- Guard rails: VACUUM needs roughly the database size again as free disk space,
  so the run is refused (with a clear message) instead of failing halfway. It
  holds the global write lock for its duration, so no worker can write into a
  database that is being rewritten -- reads are unaffected.

## v3.85
- The ONNX runtime is no longer installed by the launcher. A fresh install now
  stays at roughly 700 MB instead of ~3.9 GB, because the nvidia CUDA/cuDNN
  wheels (~2.5 GB) only arrive when auto-tagging is actually wanted.
- "Install auto-tagging" in Settings now installs BOTH parts: first the runtime
  into this venv (GPU wheel, CPU fallback), then the model files. Previously a
  missing runtime was a dead end that told the user to run pip by hand.
- The runtime is imported into the running process afterwards, so no restart is
  needed. If that import fails, Settings says so and a restart resolves it.
- Auto-tagging that is already installed is untouched: the launcher leaves an
  existing runtime alone, it simply no longer installs one up front.

## v3.84
- The resolution / file-size badges moved out of the thumbnail and into the info
  card below it. The thumbnail is now completely untouched -- no overlay, no
  gradient, no sub-pixel seam where the overlay met the image edge (a thin dark
  line was visible on some tiles and vanished on hover, because hovering
  promotes the tile to its own compositing layer and re-rasterises it).
- Consequence: the badges follow the "i" info toggle like the rest of the card.
- The middle-rank badge is now an outline chip instead of a near-black fill, so
  it stays readable on the card background.

## v3.83
- The duplicates grid is now a real gallery grid: same markup, same justified
  layout, same info card, same fixed/ratio setting. Thumbnails keep their aspect
  ratio instead of being cropped to a square.
- The duplicates top bar gained the refresh button and the "i" info-card toggle,
  so it matches the gallery bar (search, refresh, size slider, info).
- Badges are scored GROUP-WISE. The old code measured every card against one
  reference image (the highest-resolution member); resolution and file size are
  now ranked against the whole group and against each other independently.
  Four badges collapsed into two -- the bare number carries the verdict:
  green = best in the group, red = worst, blue = every member identical,
  grey = in between. The heatmap is pairwise by construction and is unchanged.
- The duplicate API returns rating and file_date (and width/height/file_size in
  tag-based mode) so the info card shows exactly what the gallery shows.

## v3.82
- Duplicates / Tag-based without auto-tagging installed: the generic install
  banner next to the mode toggle is gone. The empty state below now carries the
  whole message, adapts to whether the tagger is missing or merely has not run
  yet, links straight into Settings, and states that manual tags keep working.
- The thumbnail size slider moved from the duplicate filter row into the top
  bar, at the exact same spot and with the same look it has in the gallery.

## v3.81
- Completes the v3.80 fix. /api/hash-status now reports only files that CAN be
  hashed: videos are excluded by media_type (not by a list of five extensions)
  and rows marked hash_fail=1 are left out. Before this the frontend computed
  "unhashed = total - hashed", which stayed permanently above zero because the
  undecodable files are counted in total but never gain a pHash -- so the
  blocking "Hashing images..." screen reappeared every time the Duplicates page
  was re-entered (including via the mode toggle / nav / back button).
- The progress screen's first paint now uses the same label and numbers as the
  poller: "Comparing images... 8412 / 14933" instead of the placeholder
  "Hashing images... 0 / 14987", and the bar no longer divides by zero on an
  empty library.

## v3.80
- Duplicates: the "Hashing images... n / n" bar no longer reappears on every
  app start for files that can never produce a pHash.
  * New sticky column images.hash_fail — a file that fails to decode is marked
    once in the database instead of only in a RAM-only give-up set.
  * The gap-fill scan now excludes videos by media_type instead of a hard-coded
    list of five extensions (.m4v/.wmv/.ts/.mpg/... used to slip through and be
    re-decoded forever), and skips rows with hash_fail=1.
  * The video branch of the metadata worker writes an empty tile_sig, so videos
    never match the "tile_sig IS NULL" gap-fill condition again.
  * Metadata stripping clears hash_fail and no longer writes tile_sig back to
    NULL, which used to re-queue the image on the next scan.
- Duplicates toolbar: controls can no longer overlap. The slider group keeps a
  realistic minimum width and every other control is non-shrinking, so the row
  wraps to a second line instead of stacking labels on top of each other.
