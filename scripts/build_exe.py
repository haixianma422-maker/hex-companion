"""Reproducible Windows bundle; never includes local settings or credentials."""
import importlib.metadata
import json
import subprocess
import sys
import tempfile
import os
import shutil
import argparse
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--dist-dir', type=Path, default=ROOT / 'dist')
options = parser.parse_args()
assets = ROOT / 'packaging'
assets.mkdir(exist_ok=True)
image = Image.new('RGBA', (256, 256), (0, 0, 0, 0))
draw = ImageDraw.Draw(image)
draw.polygon([(128, 8), (232, 68), (232, 188), (128, 248), (24, 188), (24, 68)],
             fill='#091428', outline='#c8aa6e', width=16)
draw.line([(92, 80), (92, 176)], fill='#0ac8b9', width=20)
draw.line([(164, 80), (164, 176)], fill='#0ac8b9', width=20)
draw.line([(92, 128), (164, 128)], fill='#0ac8b9', width=20)
image.save(assets / 'hex-companion.ico', sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])

licenses = assets / 'licenses'
licenses.mkdir(exist_ok=True)
manifest = []
for distribution in importlib.metadata.distributions():
    name = distribution.metadata['Name']
    if name.lower() in ('pip', 'pyinstaller', 'pyinstaller-hooks-contrib', 'altgraph', 'pefile', 'pywin32-ctypes', 'setuptools'):
        continue
    manifest.append(f'{name} {distribution.version}')
    for file in distribution.files or ():
        if any(token in file.name.lower() for token in ('license', 'copying', 'notice')):
            path = Path(distribution.locate_file(file))
            if path.is_file() and path.suffix.lower() not in ('.py', '.pyc', '.pyd'):
                (licenses / f'{name}-{file.name}').write_bytes(path.read_bytes())
(licenses / 'DEPENDENCIES.txt').write_text('\n'.join(sorted(manifest)), encoding='utf-8')
python_license = Path(sys.base_prefix) / 'LICENSE.txt'
if python_license.is_file():
    (licenses / 'Python-LICENSE.txt').write_bytes(python_license.read_bytes())
# The source app may still be running and updating data/. Freeze only verified
# public snapshots so it cannot change release input while PyInstaller runs.
build_cache = ROOT / '.build-cache'
build_cache.mkdir(exist_ok=True)
seed = Path(tempfile.mkdtemp(prefix='release-seed-', dir=build_cache))
(seed / 'heroes').mkdir()
if (ROOT / 'data/item-icons').is_dir():
    shutil.copytree(ROOT / 'data/item-icons', seed / 'item-icons')
for path in (ROOT / 'data/heroes').glob('*.json'):
    row = json.loads(path.read_text(encoding='utf-8'))
    if row.get('build_mode_verified') and row.get('build_mode') == 'aram-mayhem':
        (seed / 'heroes' / path.name).write_text(json.dumps(row, ensure_ascii=False, indent=2), encoding='utf-8')
environment = dict(os.environ, HEX_COMPANION_SEED_DIR=str(seed))
subprocess.run([sys.executable, '-m', 'PyInstaller', '--noconfirm',
                '--workpath', str(ROOT / '.build-cache/pyinstaller'),
                '--distpath', str(options.dist_dir.resolve()), str(ROOT / 'HexCompanion.spec')],
               cwd=ROOT, check=True, env=environment)
