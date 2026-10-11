# Build from this directory with: .venv/Scripts/python.exe -m PyInstaller HexCompanion.spec
from pathlib import Path
import os
import json
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

root = Path(SPECPATH)
datas = [(str(root / 'data' / filename), 'data') for filename in (
    'champions.json', 'augment_display_tags.json', 'item_catalog.json', 'tier_mapping_evidence.json')]
seed = Path(os.environ.get('HEX_COMPANION_SEED_DIR', root / 'data'))
for path in (seed / 'heroes').glob('*.json'):
    row = json.loads(path.read_text(encoding='utf-8'))
    if row.get('build_mode_verified') and row.get('build_mode') == 'aram-mayhem':
        datas.append((str(path), 'data/heroes'))
datas += collect_data_files('rapidocr', includes=['*.yaml', 'models/PP-OCRv6_det_small.onnx', 'models/PP-OCRv6_rec_small.onnx'])
datas += [(str(path), 'licenses') for path in (root / 'packaging/licenses').glob('*')]

a = Analysis([str(root / 'app.py')], pathex=[str(root)],
    binaries=collect_dynamic_libs('onnxruntime'), datas=datas,
    hiddenimports=['rapidocr.main', 'rapidocr.inference_engine.onnxruntime', 'pystray._win32'],
    hookspath=[], hooksconfig={}, runtime_hooks=[str(root / 'scripts/frozen_streams.py')],
    excludes=['pytest', 'IPython', 'matplotlib', 'torch', 'paddle', 'tensorflow', 'openvino'],
    noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name='HexCompanion',
    debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
    console=False, disable_windowed_traceback=False,
    icon=str(root / 'packaging/hex-companion.ico'))
