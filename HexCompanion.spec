# Build from this directory with: .venv/Scripts/python.exe -m PyInstaller HexCompanion.spec
# Output is a folder (dist/HexCompanion): a one-file EXE would unpack Qt on every start.
from pathlib import Path
import os
import json
import re
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

root = Path(SPECPATH)
seed = Path(os.environ.get('HEX_COMPANION_SEED_DIR', root / 'data'))
datas = [(str(seed / filename), 'data') for filename in (
    'champions.json', 'augment_display_tags.json', 'item_catalog.json', 'tier_mapping_evidence.json',
    'visual_catalog.json', 'augment_catalog.json')]
for folder in ('item-icons', 'visual-assets', 'advice-icons'):
    for path in (seed / folder).rglob('*'):
        if path.is_file() and path.suffix in ('.png', '.jpg', '.jpeg', '.json'):
            datas.append((str(path), 'data/' + path.parent.relative_to(seed).as_posix()))
for prefix in (Path(), Path('sources/qq101')):
    index = seed / prefix / 'champions.json'
    if prefix.parts and index.is_file():
        datas.append((str(index), 'data/' + prefix.as_posix()))
    for path in (seed / prefix / 'heroes').glob('*.json'):
        row = json.loads(path.read_text(encoding='utf-8'))
        if row.get('build_mode_verified') and row.get('build_mode') == 'aram-mayhem':
            datas.append((str(path), 'data/' + (prefix / 'heroes').as_posix()))
datas += collect_data_files('rapidocr', includes=['*.yaml', 'models/PP-OCRv6_det_small.onnx', 'models/PP-OCRv6_rec_small.onnx'])
datas += [(str(path), 'licenses') for path in (root / 'packaging/licenses').glob('*')]
datas += [(str(path), 'aram_demo/qml') for path in (root / 'aram_demo/qml').iterdir() if path.is_file()]
datas.append((str(root / 'packaging/hex-companion.ico'), 'packaging'))

# Qt parts the overlay never loads. QtQuick.Dialogs (the install-folder picker) and the Basic
# Controls style it builds on stay.
UNUSED_QT = re.compile(r'(opengl32sw|Qt6Pdf|Qt6VirtualKeyboard|Qt6QuickTest|Qt6Test|translations[\\/]|'
                       r'qml[\\/]QtQuick[\\/](Pdf|VirtualKeyboard|Particles|Timeline|LocalStorage|Scene2D|Scene3D|tooling)|'
                       r'qml[\\/]QtQuick[\\/]Controls[\\/](Imagine|Material|Universal|FluentWinUI3|Fusion|macOS|iOS)|'
                       r'Qt6QuickControls2(Imagine|Material|Universal|FluentWinUI3|Fusion)|qml[\\/]QtTest)', re.I)

a = Analysis([str(root / 'app.py')], pathex=[str(root)],
    binaries=collect_dynamic_libs('onnxruntime'), datas=datas,
    hiddenimports=['rapidocr.main', 'rapidocr.inference_engine.onnxruntime', 'pystray._win32',
                   'PySide6.QtQuick', 'PySide6.QtQml'],
    hookspath=[], hooksconfig={}, runtime_hooks=[str(root / 'scripts/frozen_streams.py')],
    excludes=['pytest', 'IPython', 'matplotlib', 'torch', 'paddle', 'tensorflow', 'openvino', 'tkinter'],
    noarchive=False)
a.binaries = [entry for entry in a.binaries if not UNUSED_QT.search(entry[0])]
a.datas = [entry for entry in a.datas if not UNUSED_QT.search(entry[0])]
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='HexCompanion',
    debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
    console=False, disable_windowed_traceback=False,
    icon=str(root / 'packaging/hex-companion.ico'))
coll = COLLECT(exe, a.binaries, a.datas, name='HexCompanion', strip=False, upx=False)
