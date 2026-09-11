"""The native folder dialogs, and the fallbacks when none work.

Layer 18 of 27 -- see trackimage/__init__.py for the order these load in.
"""
from pathlib import Path
import os
import subprocess
import sys
from .config import PICKER_TIMEOUT
from .platform_bits import _no_window


_PICKER_CODE_WIN = (
    "import sys, ctypes\n"
    "from ctypes import wintypes, byref, addressof, cast, POINTER, c_void_p\n"
    "ole32 = ctypes.WinDLL('ole32')\n"
    "user32 = ctypes.WinDLL('user32')\n"
    "user32.GetForegroundWindow.restype = c_void_p\n"
    "class GUID(ctypes.Structure):\n"
    "    _fields_ = [('a', ctypes.c_ulong), ('b', ctypes.c_ushort),\n"
    "                ('c', ctypes.c_ushort), ('d', ctypes.c_byte * 8)]\n"
    "def guid(text):\n"
    "    out = GUID()\n"
    "    if ole32.CLSIDFromString(ctypes.c_wchar_p(text), byref(out)) < 0:\n"
    "        raise OSError('bad interface id ' + text)\n"
    "    return out\n"
    "def call(obj, slot, *args):\n"
    "    table = cast(obj, POINTER(POINTER(c_void_p)))[0]\n"
    "    proto = ctypes.WINFUNCTYPE(ctypes.c_long, *([c_void_p] * (len(args) + 1)))\n"
    "    return proto(table[slot])(obj, *args)\n"
    "def check(hr, what):\n"
    "    if hr < 0:\n"
    "        raise OSError('%s failed (0x%08X)' % (what, hr & 0xFFFFFFFF))\n"
    "ole32.CoInitialize(None)\n"
    "dialog = c_void_p()\n"
    "check(ole32.CoCreateInstance(\n"
    "          byref(guid('{DC1C5A9C-E88A-4DDE-A5A1-60F82A20AEF7}')), None, 1,\n"
    "          byref(guid('{42F85136-DB7E-439C-85F1-E4075D135FC8}')), byref(dialog)),\n"
    "      'opening the Windows folder dialog')\n"
    "opts = wintypes.DWORD()\n"
    "check(call(dialog, 10, addressof(opts)), 'reading the dialog options')\n"
    "check(call(dialog, 9, opts.value | 0x20 | 0x40), 'switching the dialog to folders')\n"
    "title = ctypes.c_wchar_p('Select image folder')\n"
    "call(dialog, 17, cast(title, c_void_p))\n"
    "shown = call(dialog, 3, user32.GetForegroundWindow())\n"
    "path = ''\n"
    "if shown >= 0:\n"
    "    item = c_void_p()\n"
    "    check(call(dialog, 20, addressof(item)), 'reading the chosen folder')\n"
    "    name = ctypes.c_wchar_p()\n"
    "    check(call(item, 5, 0x80058000, addressof(name)), 'reading the folder path')\n"
    "    path = name.value or ''\n"
    "    ole32.CoTaskMemFree(cast(name, c_void_p))\n"
    "    call(item, 2)\n"
    "elif (shown & 0xFFFFFFFF) != 0x800704C7:\n"
    "    check(shown, 'showing the Windows folder dialog')\n"
    "call(dialog, 2)\n"
    "sys.stdout.buffer.write(path.encode('utf-8'))\n"
)


_PICKER_CODE_TK = (
    "import sys, tkinter as tk\n"
    "from tkinter import filedialog\n"
    "r = tk.Tk(); r.withdraw(); r.wm_attributes('-topmost', 1)\n"
    "p = filedialog.askdirectory(title='Select image folder')\n"
    "r.destroy()\n"
    "sys.stdout.buffer.write((p or '').encode('utf-8'))\n"
)


def _picker_env():
    """The environment the Tk dialog gets.

    TCL_LIBRARY and TK_LIBRARY left behind by another program -- Anaconda,
    ActiveTcl, an older Python -- point Tcl at a version that is not this one,
    and Tcl then reports that it was not installed properly. Clearing them is
    the fix in most cases; where this Python ships its own tcl folder that one
    is named explicitly, which also covers a venv whose base install moved.
    """
    env = dict(os.environ)
    for var in ("TCL_LIBRARY", "TK_LIBRARY", "TIX_LIBRARY"):
        env.pop(var, None)
    try:
        root = Path(getattr(sys, "base_prefix", sys.prefix)) / "tcl"
        for tcl_dir in sorted(root.glob("tcl8.*"), reverse=True):
            if not (tcl_dir / "init.tcl").exists():
                continue
            env["TCL_LIBRARY"] = str(tcl_dir)
            tk_dir = tcl_dir.parent / tcl_dir.name.replace("tcl", "tk", 1)
            if tk_dir.is_dir():
                env["TK_LIBRARY"] = str(tk_dir)
            break
    except Exception:
        pass
    return env


def _run_picker(code, env=None):
    kwargs = {"capture_output": True, "timeout": PICKER_TIMEOUT}
    if env is not None:
        kwargs["env"] = env
    proc = subprocess.run([sys.executable, "-c", code], **_no_window(kwargs))
    return (proc.returncode,
            proc.stdout.decode("utf-8", "replace").strip(),
            proc.stderr.decode("utf-8", "replace").strip())
