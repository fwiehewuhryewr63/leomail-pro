# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['C:\\Users\\admin\\.gemini\\antigravity\\playground\\Leomail\\leomail_entry.py'],
    pathex=[],
    binaries=[],
    datas=[('C:\\Users\\admin\\.gemini\\antigravity\\playground\\Leomail\\frontend\\dist', 'frontend/dist')],
    hiddenimports=['uvicorn', 'uvicorn.logging', 'uvicorn.loops', 'uvicorn.loops.auto', 'uvicorn.protocols', 'uvicorn.protocols.http', 'uvicorn.protocols.http.auto', 'uvicorn.protocols.websockets', 'uvicorn.protocols.websockets.auto', 'uvicorn.lifespan', 'uvicorn.lifespan.on', 'uvicorn.lifespan.off', 'fastapi', 'sqlalchemy', 'sqlalchemy.dialects.sqlite', 'pydantic', 'loguru', 'backend', 'backend.main', 'backend.database', 'backend.models', 'backend.config', 'backend.schemas', 'backend.utils', 'backend.routers', 'backend.routers.proxies', 'backend.routers.services', 'backend.routers.birth', 'backend.routers.dashboard', 'backend.routers.settings', 'backend.services', 'backend.services.sms_provider', 'backend.services.captcha_provider', 'backend.modules', 'backend.modules.birth', 'backend.modules.birth.outlook', 'backend.modules.birth.gmail', 'backend.modules.browser_manager', 'backend.routers.ai', 'backend.services.ai_provider'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Leomail',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Leomail',
)
