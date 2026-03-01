# -*- mode: python ; coding: utf-8 -*-
"""
Leomail v4.1 — PyInstaller Spec
Builds a one-folder EXE with Playwright Chromium as native window.
"""
import os

block_cipher = None

ROOT = os.path.dirname(os.path.abspath(SPEC))

# Collect all backend Python files
backend_datas = []
for root_dir, dirs, files in os.walk(os.path.join(ROOT, 'backend')):
    dirs[:] = [d for d in dirs if d != '__pycache__']
    for f in files:
        if f.endswith(('.py', '.json', '.txt')):
            src = os.path.join(root_dir, f)
            rel = os.path.relpath(src, ROOT)
            dest = os.path.dirname(rel)
            backend_datas.append((src, dest))

# Frontend dist (pre-built)
frontend_datas = []
dist_path = os.path.join(ROOT, 'frontend', 'dist')
if os.path.exists(dist_path):
    for root_dir, dirs, files in os.walk(dist_path):
        for f in files:
            src = os.path.join(root_dir, f)
            rel = os.path.relpath(src, ROOT)
            dest = os.path.dirname(rel)
            frontend_datas.append((src, dest))

# Root files
extra_datas = [
    (os.path.join(ROOT, 'version.json'), '.'),
]

all_datas = backend_datas + frontend_datas + extra_datas

a = Analysis(
    [os.path.join(ROOT, 'launcher.py')],
    pathex=[ROOT],
    binaries=[],
    datas=all_datas,
    hiddenimports=[
        'uvicorn', 'uvicorn.logging', 'uvicorn.loops', 'uvicorn.loops.auto',
        'uvicorn.protocols', 'uvicorn.protocols.http', 'uvicorn.protocols.http.auto',
        'uvicorn.protocols.websockets', 'uvicorn.protocols.websockets.auto',
        'uvicorn.lifespan', 'uvicorn.lifespan.on',
        'fastapi', 'starlette', 'starlette.routing', 'starlette.responses',
        'starlette.middleware', 'starlette.middleware.cors',
        'pydantic', 'sqlalchemy', 'sqlalchemy.sql.default_comparator',
        'loguru', 'requests', 'aiohttp', 'psutil', 'PIL', 'cv2',
        'playwright', 'playwright.async_api',
        'backend', 'backend.main', 'backend.database', 'backend.models', 'backend.config',
        'backend.routers', 'backend.services', 'backend.modules',
        'backend.modules.birth', 'backend.modules.browser_manager', 'backend.modules.human_behavior',
    ],
    excludes=['tkinter', 'matplotlib', 'scipy', 'numpy.testing'],
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# Find icon
icon_path = os.path.join(ROOT, 'frontend', 'public', 'favicon.ico')

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Leomail',
    debug=False,
    strip=False,
    upx=True,
    console=False,  # No console — native app window only
    icon=icon_path if os.path.exists(icon_path) else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    name='Leomail',
)
