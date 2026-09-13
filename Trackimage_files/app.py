"""
TrackImage v4.74

A local danbooru-style image library that never leaves your machine.

This file only starts the program; everything it is made of lives in the
trackimage package beside it, and trackimage/__init__.py names the order those
layers load in.

The version above is raised automatically on every push to main -- see
.github/bump_version.py. The history that used to sit here in full is now in
docs/CHANGELOG.md beside this file, written by the same workflow: one place, so the two can never
drift apart. Each entry is also that version's release notes on GitHub.
"""

from trackimage import VERSION, app, main  # noqa: F401


if __name__ == "__main__":
    main()
