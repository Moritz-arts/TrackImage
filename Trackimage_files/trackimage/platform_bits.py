"""Windows, Linux and macOS specifics: processes, windows, moving files.

Layer 4 of 27 -- see trackimage/__init__.py for the order these load in.
"""
import os
import platform
import shutil
import subprocess
import sys
import threading
import time as _time
from . import state
from .config import HAS_NUMPY, STATIC_DIR, _CPU_COUNT, app
from .logging_setup import _LOG_PATH, log


def _port_owner(port):
    """v4.26: (pid, name) of whatever holds `port`, or None. Used to tell the
    user which process to close instead of leaving them with a dead launcher."""
    try:
        if os.name == "nt":
            out = subprocess.run(["netstat", "-ano", "-p", "TCP"],
                                 **_no_window({"capture_output": True, "text": True, "timeout": 6})).stdout
            pid = None
            for line in out.splitlines():
                f = line.split()
                if len(f) >= 5 and f[0] == "TCP" and f[1].endswith(":%d" % port) and f[3] == "LISTENING":
                    pid = f[4]
                    break
            if not pid:
                return None
            name = "unknown"
            try:
                t = subprocess.run(["tasklist", "/FI", "PID eq %s" % pid, "/NH", "/FO", "CSV"],
                                   **_no_window({"capture_output": True, "text": True, "timeout": 6})).stdout
                if '"' in t:
                    name = t.split('"')[1]
            except Exception:
                pass
            return (pid, name)
        out = subprocess.run(["lsof", "-nP", "-iTCP:%d" % port, "-sTCP:LISTEN"],
                             capture_output=True, text=True, timeout=6).stdout
        for line in out.splitlines()[1:]:
            f = line.split()
            if len(f) >= 2:
                return (f[1], f[0])
    except Exception:
        pass
    return None


def _front_existing_window(title):
    """v4.24: restore and raise the window of the instance that is already up.
    Returns True when one was found. Windows will not simply let any process
    steal focus, so the usual trick is used: briefly attach to the input queue of
    the thread that owns the window, which makes the request legitimate."""
    if os.name != "nt":
        return False
    try:
        import ctypes
        from ctypes import wintypes
        u32 = ctypes.windll.user32
        k32 = ctypes.windll.kernel32
        u32.FindWindowW.restype = wintypes.HWND
        u32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
        u32.GetWindowThreadProcessId.restype = wintypes.DWORD
        hwnd = u32.FindWindowW(None, title)
        if not hwnd:
            return False
        SW_RESTORE = 9
        if u32.IsIconic(hwnd):
            u32.ShowWindow(hwnd, SW_RESTORE)
        tid = u32.GetWindowThreadProcessId(hwnd, None)
        me = k32.GetCurrentThreadId()
        attached = bool(tid) and bool(u32.AttachThreadInput(me, tid, True))
        try:
            u32.SetForegroundWindow(hwnd)
            u32.BringWindowToTop(hwnd)
        finally:
            if attached:
                u32.AttachThreadInput(me, tid, False)
        return True
    except Exception:
        return False


def _apply_window_icon(title):
    """v4.04: give the window and the taskbar the TrackImage logo instead of the
    generic Python feather. pywebview draws its Windows window with WinForms,
    which inherits the icon of the running executable -- pythonw.exe -- and offers
    no way to override it, so the icon is pushed in through the Win32 API once the
    window exists. A distinct AppUserModelID stops Windows from filing the window
    under the Python entry in the taskbar. Everything here is best effort: on any
    failure the window simply keeps the old icon."""
    if os.name != "nt":
        return
    ico = os.path.join(STATIC_DIR, "trackimage.ico")
    if not os.path.exists(ico):
        return
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Moritz.TrackImage")
    except Exception:
        pass

    def _push():
        import ctypes
        from ctypes import wintypes
        u32 = ctypes.windll.user32
        # v4.38: declare every signature. Without argtypes ctypes marshals each
        # argument as a 32-bit int, and LoadImageW hands back a 64-bit handle --
        # which arrived at SendMessageW as
        #     ctypes.ArgumentError: argument 4: OverflowError: int too long to convert
        # and the icon was never set. Same fault the clipboard had in v4.11; this
        # call was missed at the time.
        u32.FindWindowW.restype = wintypes.HWND
        u32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
        u32.LoadImageW.restype = wintypes.HANDLE
        u32.LoadImageW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR, wintypes.UINT,
                                   ctypes.c_int, ctypes.c_int, wintypes.UINT]
        u32.SendMessageW.restype = ctypes.c_ssize_t
        u32.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT,
                                     ctypes.c_size_t, ctypes.c_ssize_t]
        IMAGE_ICON, LR_LOADFROMFILE, LR_DEFAULTSIZE = 1, 0x10, 0x40
        WM_SETICON, ICON_SMALL, ICON_BIG = 0x0080, 0, 1
        for _ in range(60):                      # the window is not up instantly
            hwnd = u32.FindWindowW(None, title)
            if hwnd:
                for which, cx in ((ICON_SMALL, 16), (ICON_BIG, 32)):
                    h = u32.LoadImageW(None, ico, IMAGE_ICON, cx, cx,
                                       LR_LOADFROMFILE | LR_DEFAULTSIZE)
                    if h:
                        u32.SendMessageW(hwnd, WM_SETICON, which, h)
                return
            _time.sleep(0.25)

    try:
        threading.Thread(target=_push, daemon=True).start()
    except Exception:
        pass


def _no_window(kwargs=None):
    """v4.03: every child process on Windows opens its own console window unless
    it is told not to. With pythonw there is no parent console to inherit, so each
    ffmpeg call for a video thumbnail flashed a black box across the desktop --
    one per file. CREATE_NO_WINDOW suppresses that; on Linux and macOS the flag
    does not exist and the dict is returned untouched."""
    kwargs = dict(kwargs or {})
    if os.name == "nt":
        kwargs["creationflags"] = kwargs.get("creationflags", 0) | subprocess.CREATE_NO_WINDOW
    return kwargs


class _Unreachable(OSError):
    """v4.43: the file could not be read -- the drive, not the picture."""


def _is_network_path(path):
    """True for a path that lives on another machine.

    A UNC path says so in its first two characters. A mapped drive letter does
    not, so Windows is asked what kind of drive it is -- that call is answered
    from the drive table and does not go near the network, unlike isdir().
    """
    try:
        if path.startswith("\\\\") or path.startswith("//"):
            return True
        if os.name != "nt":
            return False
        drive = os.path.splitdrive(path)[0]
        if not drive:
            return False
        import ctypes
        DRIVE_REMOTE = 4
        return ctypes.windll.kernel32.GetDriveTypeW(drive + "\\") == DRIVE_REMOTE
    except Exception:
        return False


def _same_volume(a, b):
    try:
        if os.name == "nt":
            return os.path.splitdrive(os.path.abspath(a))[0].lower() == \
                   os.path.splitdrive(os.path.abspath(b))[0].lower()
        return os.stat(a).st_dev == os.stat(os.path.dirname(b) or ".").st_dev
    except Exception:
        return False


def _move_file_safely(src, dest):
    """Move src to dest without ever being able to lose it.

    Same drive: a rename, which either happens or does not -- there is no moment
    where the file exists in neither place. Different drives: copy first, check
    the copy is the same size, and only then remove the original. If the check
    fails the copy is thrown away and the original is left exactly where it was.
    """
    if _same_volume(src, dest):
        try:
            os.replace(src, dest)
            return True, "rename"
        except OSError:
            pass                       # fall through to copy+verify
    shutil.copy2(src, dest)
    try:
        s_size, d_size = os.path.getsize(src), os.path.getsize(dest)
    except OSError as e:
        try: os.remove(dest)
        except Exception: pass
        raise IOError(f"could not verify the copy ({type(e).__name__})")
    if s_size != d_size:
        try: os.remove(dest)
        except Exception: pass
        raise IOError(f"the copy came out {d_size} bytes instead of {s_size}")
    os.remove(src)
    return True, "copy+verify"


def _boost_process_priority(worker=False):
    """v3.14: stop Windows 11 from parking the worker threads on the slow E-cores.
    On a hybrid CPU (13700KF = 8 P-cores + 8 E-cores) the OS classifies a long
    background workload as 'efficiency' (EcoQoS) and pins it to the 8 E-cores —
    exactly the '~8 of 24' symptom. Three nudges, strongest first:
      1) Opt OUT of power throttling (SetProcessInformation / ProcessPowerThrottling,
         StateMask=0) -> tells the scheduler to run this process at full speed on the
         performance cores. This is the actual EcoQoS opt-out, not just a priority bump.
      2) Set the affinity mask to ALL logical processors (in case anything shrank it).
      3) Set the priority class. v4.14: a compute worker asks for BELOW_NORMAL,
         not ABOVE_NORMAL. Twenty-four workers above the interface is why the
         window stopped answering while a folder was being taken in -- the
         Settings button could not even be clicked. Below normal costs nothing
         while the machine is idle, because there is no one to yield to, and
         hands the machine straight back the moment the interface wants it. The
         EcoQoS opt-out above is what keeps the workers on the fast cores, and
         that is untouched.
    Windows-only, dependency-free, every step best-effort."""
    if os.name != "nt":
        return
    try:
        import ctypes
        from ctypes import wintypes
        k32 = ctypes.windll.kernel32
        # v3.75: declare the signatures. Without argtypes/restype ctypes treats a
        # HANDLE as a C int, so on 64-bit Windows the pseudo-handle from
        # GetCurrentProcess() is truncated and SetProcessInformation just returns
        # FALSE -- which is exactly the "EcoQoS opt-out not accepted (older
        # Windows?)" line in the log. The OS was never the problem.
        try:
            k32.GetCurrentProcess.restype = wintypes.HANDLE
            k32.GetCurrentProcess.argtypes = []
            k32.SetProcessInformation.restype = wintypes.BOOL
            k32.SetProcessInformation.argtypes = [wintypes.HANDLE, ctypes.c_int,
                                                  ctypes.c_void_p, wintypes.DWORD]
            k32.SetProcessAffinityMask.restype = wintypes.BOOL
            k32.SetProcessAffinityMask.argtypes = [wintypes.HANDLE, ctypes.c_size_t]
            k32.SetPriorityClass.restype = wintypes.BOOL
            k32.SetPriorityClass.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        except Exception:
            pass
        h = k32.GetCurrentProcess()

        # 1) EcoQoS opt-out: disable execution-speed throttling -> use P-cores.
        class _PPTS(ctypes.Structure):
            _fields_ = [("Version", wintypes.ULONG),
                        ("ControlMask", wintypes.ULONG),
                        ("StateMask", wintypes.ULONG)]
        PROCESS_POWER_THROTTLING_EXECUTION_SPEED = 0x1
        ProcessPowerThrottling = 4  # PROCESS_INFORMATION_CLASS
        st = _PPTS(Version=1, ControlMask=PROCESS_POWER_THROTTLING_EXECUTION_SPEED, StateMask=0)
        try:
            ok = k32.SetProcessInformation(h, ProcessPowerThrottling, ctypes.byref(st), ctypes.sizeof(st))
            print("  ✓ EcoQoS opt-out applied — scheduler will use performance (P) cores" if ok
                  else "  ℹ EcoQoS opt-out not accepted (older Windows?) — continuing")
        except Exception as e:
            print(f"  ℹ EcoQoS opt-out unavailable: {e}")

        # 2) Allow ALL logical processors.
        try:
            mask = (1 << _CPU_COUNT) - 1
            k32.SetProcessAffinityMask(h, ctypes.c_size_t(mask))
        except Exception:
            pass

        # 3) Priority class -- see the note at the top of this function.
        try:
            ABOVE_NORMAL_PRIORITY_CLASS = 0x00008000
            BELOW_NORMAL_PRIORITY_CLASS = 0x00004000
            k32.SetPriorityClass(h, BELOW_NORMAL_PRIORITY_CLASS if worker
                                 else ABOVE_NORMAL_PRIORITY_CLASS)
        except Exception:
            pass
    except Exception as e:
        print(f"  ℹ CPU scheduling tweak failed: {e}")


state._qos_per_thread_logged = False


def _boost_thread_qos():
    """v3.16: per-THREAD EcoQoS opt-out. _boost_process_priority() only sets the
    opt-out at process level, but Windows 11 assigns power-throttling QoS per
    thread -- a long-running background thread is still classified 'efficiency'
    and pinned to the E-cores regardless of the process setting (the '~8 of 24'
    symptom). Calling this from each worker thread forces THAT thread to HighQoS
    so the scheduler runs it on the performance (P) cores. Windows-only, ctypes,
    dependency-free, best-effort. Cheap to call once per long-lived worker."""
    if os.name != "nt":
        return
    try:
        import ctypes
        from ctypes import wintypes
        k32 = ctypes.windll.kernel32
        # Make the pseudo-handle pointer-sized so it isn't truncated on Win64.
        k32.GetCurrentThread.restype = wintypes.HANDLE
        hT = k32.GetCurrentThread()   # pseudo-handle, valid only in this thread

        # 1) Opt this thread out of execution-speed throttling -> HighQoS -> P-cores.
        class _TPTS(ctypes.Structure):
            _fields_ = [("Version", wintypes.ULONG),
                        ("ControlMask", wintypes.ULONG),
                        ("StateMask", wintypes.ULONG)]
        THREAD_POWER_THROTTLING_EXECUTION_SPEED = 0x1
        ThreadPowerThrottling = 3   # THREAD_INFORMATION_CLASS
        st = _TPTS(Version=1, ControlMask=THREAD_POWER_THROTTLING_EXECUTION_SPEED, StateMask=0)
        ok = False
        try:
            k32.SetThreadInformation.argtypes = [wintypes.HANDLE, ctypes.c_int,
                                                 ctypes.c_void_p, wintypes.DWORD]
            ok = bool(k32.SetThreadInformation(hT, ThreadPowerThrottling,
                                               ctypes.byref(st), ctypes.sizeof(st)))
        except Exception:
            pass

        # 2) Above-normal thread priority so it is preferred on the fast cores.
        try:
            THREAD_PRIORITY_ABOVE_NORMAL = 1
            k32.SetThreadPriority(hT, THREAD_PRIORITY_ABOVE_NORMAL)
        except Exception:
            pass

        if ok and not state._qos_per_thread_logged:
            state._qos_per_thread_logged = True
            print("  ✓ per-thread EcoQoS opt-out active — workers run on performance (P) cores")
    except Exception:
        pass


def _system_ram_gb():
    try:
        if platform.system() == "Windows":
            import ctypes
            class _MS(ctypes.Structure):
                _fields_ = [("l", ctypes.c_ulong), ("ld", ctypes.c_ulong),
                            ("tot", ctypes.c_ulonglong), ("av", ctypes.c_ulonglong),
                            ("tpf", ctypes.c_ulonglong), ("apf", ctypes.c_ulonglong),
                            ("tv", ctypes.c_ulonglong), ("avv", ctypes.c_ulonglong),
                            ("ae", ctypes.c_ulonglong)]
            m = _MS(); m.l = ctypes.sizeof(_MS)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
            return m.tot / (1024**3)
        with open("/proc/meminfo") as f:
            for ln in f:
                if ln.startswith("MemTotal"): return int(ln.split()[1]) / (1024**2)
    except Exception: pass
    return None


def _log_system_info():
    log(f"OS         {platform.platform()}")
    log(f"Python     {platform.python_version()} ({platform.architecture()[0]})")
    # v4.43: every release is checked against 3.10, 3.11 and 3.12. Anything else
    # may well work -- a user has been running 3.14 -- but if something behaves
    # oddly this is worth knowing before anything else is investigated.
    if not (3, 10) <= sys.version_info[:2] <= (3, 13):
        log(f"Python {platform.python_version()} is outside the tested range "
            f"(3.10 to 3.13). TrackImage should still run; mention this version "
            f"first if anything behaves strangely.", "warning")
    hw = f"{_CPU_COUNT} logical processors"
    ram = _system_ram_gb()
    if ram: hw += f"  ·  {ram:.0f} GB RAM"
    log(f"Hardware   {hw}")
    libs = []
    try:
        import PIL; libs.append(f"Pillow {PIL.__version__}")
    except Exception: pass
    if HAS_NUMPY:
        try:
            import numpy as _np; libs.append(f"numpy {_np.__version__}")
        except Exception: pass
    log("Libraries  " + (", ".join(libs) if libs else "none"))
    try: log(f"Database   {app.config['DATABASE']}")
    except Exception: pass
    log(f"Logfile    {_LOG_PATH}")
