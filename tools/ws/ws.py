#!/usr/bin/env python3
"""workstead CLI launcher. Usage: python3 tools/ws/ws.py <command> (see --help)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from workstead.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
