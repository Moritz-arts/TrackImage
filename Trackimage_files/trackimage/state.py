"""The names that get rebound while the program runs.

Everything else can be imported directly, because it is only ever read or
mutated in place. These are not: rebinding one inside a module would leave
every other module holding the value it had at import time. They live here
and are read and written as state.NAME so there is one copy.

Layer 2 of 27 -- see trackimage/__init__.py for the order these load in."""
NATIVE_DROP_OK = False
WINDOW_MODE = False
_BIND_HOST = "127.0.0.1"
_CUDA_DIRS_DONE = False
_CUDA_DLL_DIRS = []
_CUDA_FOREIGN_DIRS = []
_MP_POOL = None
_MP_TRIED = False
_NET_ON = False
_TAG_PROVIDERS = ""
_TAG_PROV_USED = ""
_TAG_RUNTIME_BROKEN = ""
_TAG_WARMUP = 0.0
_THUMB_CFG = None
_UI_HANDOVER = False
_UI_WINDOW = None
_auto_shutdown = True
_console_seq = 0
_drag_last_error = ""
_drag_q = None
_drag_thread = None
_qos_per_thread_logged = False
_shutdown_timer = None
_tag_runtime_state = 'unknown'   # _RT_UNKNOWN in config
_tagger = None
_tagger_failed = False
_trash_janitor_started = False
_watcher_observer = None
_watcher_running = False
scan_progress = {"active": False, "folders": []}
