# Onedir build of the QML spike: .venv-qml/Scripts/python.exe -m PyInstaller qml_spike/HexCompanionQml.spec
# OCR packages are included (unused by the spike UI) so the folder size matches a full release.
import re
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

root = Path(SPECPATH).parent
seed = root / 'data'
datas = [(str(seed / name), 'data') for name in ('champions.json', 'augment_display_tags.json', 'item_catalog.json',
                                               'tier_mapping_evidence.json', 'visual_catalog.json')]
for folder in ('item-icons', 'visual-assets', 'advice-icons'):
    for path in (seed / folder).rglob('*'):
        if path.is_file() and path.suffix in ('.png', '.jpg', '.jpeg', '.json'):
            datas.append((str(path), 'data/' + path.parent.relative_to(seed).as_posix()))
datas += [(str(path), 'qml_spike/qml') for path in (root / 'qml_spike/qml').iterdir()]
datas += collect_data_files('rapidocr', includes=['*.yaml', 'models/PP-OCRv6_det_small.onnx', 'models/PP-OCRv6_rec_small.onnx'])
datas.append((str(root / 'packaging/hex-companion.ico'), 'packaging'))

# Qt pieces the overlay never loads: software GL fallback, widgets, controls styles, PDF, translations.
DROP = re.compile(r'(opengl32sw|Qt6Pdf|Qt6Labs|QuickControls2|QuickDialogs|QuickTemplates2|Qt6Widgets|QtWidgets|'
                  r'Qt6VirtualKeyboard|Qt6Svg|Qt6QuickTest|Qt6Test|translations|qtvirtualkeyboard|'
                  r'qml[\/]QtQuick[\/](Controls|Dialogs|Templates|NativeStyle|VirtualKeyboard|Pdf|Particles|Timeline|'
                  r'LocalStorage|Scene2D|Scene3D|VectorImage|tooling)|qml[\/](Qt[\/]labs|QtTest|QtCore))', re.I)

a = Analysis([str(root / 'qml_spike/main.py')], pathex=[str(root)],
    binaries=collect_dynamic_libs('onnxruntime'), datas=datas,
    hiddenimports=['rapidocr.main', 'rapidocr.inference_engine.onnxruntime', 'aram_demo.recognition',
                   'PySide6.QtQuick', 'PySide6.QtQml'],
    excludes=['tkinter', 'PySide6.QtWidgets', 'pytest', 'IPython', 'matplotlib', 'torch', 'paddle', 'tensorflow', 'openvino'],
    noarchive=False)
a.binaries = [b for b in a.binaries if not DROP.search(b[0])]
a.datas = [d for d in a.datas if not DROP.search(d[0])]
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='HexCompanionQml', console=False, upx=False,
          icon=str(root / 'packaging/hex-companion.ico'))
coll = COLLECT(exe, a.binaries, a.datas, name='HexCompanionQml', upx=False)
