# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for NeuroTendrils (macOS / Windows / Linux onedir)."""

from pathlib import Path

from PyInstaller.compat import is_darwin
from PyInstaller.utils.hooks import collect_all, collect_submodules

ROOT = Path(SPECPATH).resolve().parents[0]
DESKTOP = ROOT / "desktop"
FLOW = ROOT / "workers" / "neuroflow"
STUDIO = ROOT / "workers" / "neurostudio"

datas = []
binaries = []
hiddenimports = []

# Qt / science stack — collect plugins, data files, and binary extensions.
for pkg in (
    "PySide6",
    "shiboken6",
    "numpy",
    "scipy",
    "sklearn",
    "mne",
    "torch",
    "safetensors",
    "onnx",
):
    try:
        pkg_datas, pkg_binaries, pkg_hidden = collect_all(pkg)
        datas += pkg_datas
        binaries += pkg_binaries
        hiddenimports += pkg_hidden
    except Exception as exc:  # noqa: BLE001 — optional heavy deps
        print(f"[spec] skip collect_all({pkg}): {exc}")

# App + worker packages (lazy-imported at runtime).
hiddenimports += collect_submodules("neurotendrils")
hiddenimports += collect_submodules("neuroflow")
hiddenimports += collect_submodules("neurostudio")
hiddenimports += [
    "neuroflow.fingerprint",
    "neuroflow.run",
    "neuroflow.steps",
    "neuroflow.apply",
    "neuroflow.repro",
    "neurostudio.train",
    "neurostudio.export",
    "neurostudio.templates",
    "neurostudio.devices",
]

# Keep worker trees on disk so runtime.ensure_sys_path() finds them when frozen.
datas += [
    (str(FLOW / "neuroflow"), "workers/neuroflow/neuroflow"),
    (str(STUDIO / "neurostudio"), "workers/neurostudio/neurostudio"),
]

a = Analysis(
    [str(ROOT / "packaging" / "entry.py")],
    pathex=[str(DESKTOP), str(FLOW), str(STUDIO)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter",
        "matplotlib.tests",
        "pytest",
        "IPython",
        "jupyter",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="NeuroTendrils",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=bool(is_darwin),
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="NeuroTendrils",
)

if is_darwin:
    app = BUNDLE(
        coll,
        name="NeuroTendrils.app",
        icon=None,
        bundle_identifier="com.neurotendrils.app",
        version="0.1.0",
        info_plist={
            "CFBundleName": "NeuroTendrils",
            "CFBundleDisplayName": "NeuroTendrils",
            "CFBundleShortVersionString": "0.1.0",
            "CFBundleVersion": "0.1.0",
            "NSHighResolutionCapable": True,
            "NSPrincipalClass": "NSApplication",
            "LSMinimumSystemVersion": "12.0",
        },
    )
