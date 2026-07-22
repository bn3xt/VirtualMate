from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

product_root = Path(SPECPATH)
web_root = product_root / "frontend" / "dist"

hiddenimports = (
    [
        "chromadb.api.rust",
        "chromadb.segment.impl.manager.local",
        "chromadb.telemetry.product.posthog",
        "tiktoken_ext.openai_public",
    ]
    + collect_submodules("uvicorn.protocols")
    + collect_submodules("uvicorn.lifespan")
)
datas = collect_data_files("chromadb") + [(str(web_root), "web")]

a = Analysis(
    [str(product_root / "backend" / "virtual_mate" / "launcher.py")],
    pathex=[str(product_root / "backend")],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "torch", "torchvision", "torchaudio", "tensorflow", "sentence_transformers",
        "transformers", "rerankers", "matplotlib", "IPython", "notebook",
        "scipy", "sklearn", "tkinter", "chromadb.test",
    ],
    noarchive=False,
    optimize=1,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="VirtualMate",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="VirtualMate",
)

