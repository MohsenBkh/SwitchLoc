# -*- coding: utf-8 -*-
"""PyInstaller entry point for the SwitchLoc CLI (BUILD.bat step 7).

Kept in build_tools/ (not src/). The equivalent dev-mode launch is:
    python -m switchloc <import|inspect|topology> ...
"""
import sys

from switchloc.cli import main

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
