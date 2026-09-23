#!/bin/bash
# .command so it can be launched from Finder by double-click.
# cd into the script's own folder (Finder starts it in $HOME otherwise).
# v4.33: and then one level down, into Trackimage_files, where everything
# TrackImage owns now lives -- app.py, Static, Database, Logs, venv, models.
cd "$(dirname "$0")"
TIDIR="$(pwd)/Trackimage_files"
if [ ! -f "$TIDIR/app.py" ]; then
    echo "  [ERROR] Trackimage_files/app.py not found next to this launcher."
    echo "          Unpack the whole archive, keeping start-macos.command and"
    echo "          the Trackimage_files folder side by side."
    exit 1
fi
cd "$TIDIR" || exit 1
# v4.51: these live under Userdata now. Making them where they used to be
# made TrackImage take two empty folders for an older layout and back them
# up as .pre449 on a brand new install.
mkdir -p Userdata/Logs Userdata/Database

echo ""
echo "  ========================================"
echo "   TrackImage v4.78 - Setup & Start (macOS)"
echo "  ========================================"
echo ""

# Check Python 3 (macOS no longer ships it)
if ! command -v python3 &> /dev/null; then
    echo "  [ERROR] Python 3 not found!"
    echo "  Install it with Homebrew:  brew install python python-tk"
    echo "  (or get the installer from https://www.python.org/downloads/macos/ )"
    exit 1
fi

# Check tkinter (needed by the native folder picker)
# v4.53: this used to read like a problem. Since v4.46 the folder picker
# tries the system dialog first and offers a box to type the path when no
# dialog works at all, so Tk is a convenience here and nothing more.
if ! python3 -c "import tkinter" &> /dev/null 2>&1; then
    echo "  [note] tkinter is not installed. Everything works without it;"
    echo "         you will type a folder path instead of picking it in a"
    echo "         dialog. To get the dialog:  brew install python-tk"
fi

# Create venv if needed
if [ ! -d "venv" ]; then
    echo "  [1/3] Creating virtual environment..."
    python3 -m venv venv
fi

source venv/bin/activate
# v3.76: keep the venv self-contained (see start-linux.sh)
export PYTHONNOUSERSITE=1
echo "  [2/3] Checking dependencies..."
# v4.14: name each package as it is checked. A silent minutes-long step looks
# like a hang, and a package that only half-installed left no trace at all.
# v4.21: each package is listed with what it is FOR, so a fresh install is
# readable rather than a wall of names.
# v4.22: the same lines also go to install.log, so the console inside Settings can
# show afterwards what happened during setup.
ILOG="$TIDIR/Userdata/Logs/install.log"
: > "$ILOG"
say(){ echo "$1"; echo "$1" >> "$ILOG"; }
# v4.36: pip, setuptools and wheel first. A fresh virtual environment on Python
# 3.12 ships pip and nothing else -- no setuptools, no wheel. Any package that
# comes as a source archive without a pyproject.toml then falls back to the old
# setup.py route, which needs exactly the setuptools that is not there.
# proxy_tools, pulled in by pywebview, is one of those: on one machine pip
# printed a deprecation notice and stopped there, and the start went quiet.
# A few seconds here instead of a first run that ends in silence.
python "$TIDIR/launcher_check.py" bootstrap
for E in \
  "flask|the local web server TrackImage runs on" \
  "pillow|reading and resizing images" \
  "pillow-heif|iPhone HEIC photos" \
  "imageio-ffmpeg|thumbnails for video files" \
  "watchdog|noticing when files change on disk" \
  "send2trash|deleting to the wastebasket instead of for good" \
  "qrcode|the scan-me code for opening TrackImage on a phone" \
  "numpy|the maths behind duplicate detection" \
  "pywebview|the app window (instead of a browser tab)"
do
    P="${E%%|*}"; WHY="${E#*|}"
    M=$(echo "$P" | tr '-' '_')
    case "$M" in pillow) M=PIL;; pywebview) M=webview;; esac
    if python -c "import importlib.util,sys; sys.exit(0 if importlib.util.find_spec('$M') else 1)" 2>/dev/null; then
        say "       $P ok - $WHY"
    else
        say "       installing $P - $WHY ..."
        python -m pip install "$P" -q || say "       [!] $P did not install"
    fi
done

# v4.36: check what is actually importable rather than trusting that pip stayed
# quiet. A package can install and still be unusable, and until now the only
# sign of that was a program that never came up.
echo ""
python "$TIDIR/launcher_check.py" deps
if [ $? -ne 0 ]; then
    echo ""
    echo "  [ERROR] TrackImage cannot start until the packages listed above are"
    echo "          installed. The full setup output is in Userdata/Logs/install.log."
    echo ""
    exit 1
fi
echo ""
# v3.85: the ONNX runtime is NOT installed here any more. It only arrives when the
# user clicks "Install auto-tagging" in Settings, which keeps a fresh install that
# never tags small. An already installed runtime is left alone -- app.py detects it
# on import, exactly as before. macOS gets the CPU runtime (no CUDA wheels exist).

echo "  [3/3] Starting TrackImage..."
echo ""
# Friendly hostname: map trackimage -> 127.0.0.1 so http://trackimage:5001 works. localhost always works.
URLHOST=localhost
if grep -qiE "[[:space:]]trackimage([[:space:]]|$)" /etc/hosts 2>/dev/null; then URLHOST=trackimage
elif sudo -n true 2>/dev/null; then echo "127.0.0.1 trackimage" | sudo -n tee -a /etc/hosts >/dev/null 2>&1 && URLHOST=trackimage; fi
echo "  Open http://$URLHOST:5001"
echo ""
# v4.06: TrackImage opens its own window through the system WKWebView -- pywebview
# pulls the pyobjc bindings from pip, nothing else is needed. The process is
# detached so the Terminal window can be closed right after the start; console
# output goes to the logfile and to Settings > Console.
nohup python3 app.py "$@" >> Userdata/Logs/trackimage.log 2>&1 &
# v4.36: find out who answers on the port instead of assuming it is us. A
# leftover process from an earlier attempt holds it just as convincingly, and
# the old check reported success for it without saying a word.
python "$TIDIR/launcher_check.py" wait 35
RC=$?
if [ $RC -eq 0 ]; then
    echo "  TrackImage is running - http://localhost:5001"
    echo "  You can close this Terminal window."
elif [ $RC -eq 2 ]; then
    echo "  Close that one - or end its python process - and run this file again"
    echo "  to start the version in this folder."
else
    echo ""
    echo "  [ERROR] TrackImage did not come up. Last lines of the log:"
    echo ""
    tail -n 25 Userdata/Logs/trackimage.log 2>/dev/null
    echo ""
fi
