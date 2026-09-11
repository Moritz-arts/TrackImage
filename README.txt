TrackImage v4.58
================

INSTALL
  Unpack the whole ZIP into an EMPTY folder. Keep the launcher and the
  Trackimage_files folder side by side — the launcher will not start without it.

  Windows   double-click  start-windows.bat
  Linux     ./start-linux.sh
  macOS     double-click  start-macos.command

  The first start installs the Python packages it needs and creates
  Trackimage_files/Userdata for the database and the logs. The tagging model
  (~1.26 GB) is not in this ZIP; fetch it from Settings when you want tagging.

  Python 3.10, 3.11 or 3.12.


WHAT IS NEW IN v4.59
  - Updates come from the repository's main branch now, not from releases.
    Settings -> Repair & Update reads the version the branch carries and
    installs the branch itself, so what you get is what the repository holds
    rather than whatever was last packed into a release.

  - The version number is raised automatically whenever something is pushed
    there, so "newer" always means newer.


WHAT IS NEW IN v4.58
  - Full view: the folder tree and the tag list beside the picture work. A
    branch clicked there opens, and clicking a folder, a name, a tag or a
    rating puts the filtered gallery back on screen instead of filtering a
    view hidden behind the photograph.

  - The buttons in the panel are named for what they do: Locate in Explorer,
    Locate in TrackImage, Wipe metadata.

  - Settings -> Repair & Update can install a release that has no ZIP attached
    to it. GitHub builds a source archive from every tag, and that archive
    holds the same folders TrackImage runs from; it is checked exactly as an
    attached file would be before anything is replaced.


WHAT IS NEW IN v4.57
  - Settings has a new tab, Repair & Update. The installation check moved
    there out of Help, which was holding two unrelated things: how the app is
    used, and what state the install is in.

  - A button asks GitHub whether a newer release exists, and can install it.
    The download is checked before anything is touched: the archive has to be
    intact, has to actually be TrackImage, has to match the version its tag
    claims, and has to be newer than what is running. Your database is copied
    to Userdata-backup-v<version>.zip beside the installation, and only then
    does the swap happen. Your pictures, database, settings and the tagging
    model are carried across untouched. If any step fails the previous version
    is put back.

  - The check can also run once at start, but only if you switch it on in that
    tab. It is off by default: TrackImage still opens no connection of its own.

  - Help & Reference lists every shortcut, and the global ones can be changed.
    Click a key and press the combination you want. A combination already in
    use is refused rather than quietly stealing the other action. Escape and
    the digits stay fixed - Escape is the way out of every state in the app,
    and the digits are ten keys that would have to move together. Bindings are
    stored with the other settings, so they follow the app rather than the
    browser it was opened in.

  Turning keywords from files into real tags is still off by default. Settings
  -> Auto-tagging -> Import embedded keywords.


UPGRADING FROM AN OLDER VERSION
  Unpack into a new empty folder, then copy your old
  Trackimage_files/Userdata folder into the new Trackimage_files.
  Nothing else carries over and nothing else needs to.
  From v4.57 onward, Settings -> Repair & Update does this for you.


FONTS
  DM Sans and Space Mono are bundled under the SIL Open Font License 1.1.
  The licences are in Trackimage_files/Static/fonts.

  TrackImage makes no network call on its own. The only downloads are the
  Python packages during setup and the tagging model when you ask for it.


Moritz
