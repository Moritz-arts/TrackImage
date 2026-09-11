"""TrackImage, in the order it loads.

Each module may lean on the ones above it. Where something lower needs
something higher -- always at run time, never while importing -- the import
sits inside the function that uses it and says so.
"""

MODULES = [
    "config",
    "state",
    "logging_setup",
    "platform_bits",
    "appconfig",
    "db",
    "events",
    "media",
    "metadata",
    "hashing",
    "thumbnails",
    "processing",
    "tagger",
    "duplicates",
    "scanning",
    "network",
    "runtime",
    "picker",
    "importing",
    "updater",
    "api_system",
    "api_folders",
    "api_images",
    "api_tags",
    "api_duplicates",
    "api_media",
    "desktop",
]

from . import config  # noqa: F401,E402
from . import state  # noqa: F401,E402
from . import logging_setup  # noqa: F401,E402
from . import platform_bits  # noqa: F401,E402
from . import appconfig  # noqa: F401,E402
from . import db  # noqa: F401,E402
from . import events  # noqa: F401,E402
from . import media  # noqa: F401,E402
from . import metadata  # noqa: F401,E402
from . import hashing  # noqa: F401,E402
from . import thumbnails  # noqa: F401,E402
from . import processing  # noqa: F401,E402
from . import tagger  # noqa: F401,E402
from . import duplicates  # noqa: F401,E402
from . import scanning  # noqa: F401,E402
from . import network  # noqa: F401,E402
from . import runtime  # noqa: F401,E402
from . import picker  # noqa: F401,E402
from . import importing  # noqa: F401,E402
from . import updater  # noqa: F401,E402
from . import api_system  # noqa: F401,E402
from . import api_folders  # noqa: F401,E402
from . import api_images  # noqa: F401,E402
from . import api_tags  # noqa: F401,E402
from . import api_duplicates  # noqa: F401,E402
from . import api_media  # noqa: F401,E402
from . import desktop  # noqa: F401,E402

from .config import VERSION, app  # noqa: F401,E402
from .desktop import main  # noqa: F401,E402
