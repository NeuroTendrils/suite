"""PyInstaller entrypoint for the NeuroTendrils desktop app."""

from __future__ import annotations

from neurotendrils.main import main

if __name__ == "__main__":
    raise SystemExit(main())
