"""Create shareable EXE/source archives after acceptance has passed."""
import hashlib
import json
import shutil
import zipfile
import argparse
from pathlib import Path

from PyInstaller.archive.readers import CArchiveReader

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--exe', type=Path, default=ROOT / 'dist/HexCompanion.exe')
exe = parser.parse_args().exe.resolve()
check = json.loads((ROOT / 'artifacts/packaged_desktop_check.json').read_text(encoding='utf-8'))
assert check['status'] == 'passed' and check['frozen'] and check['clean_exit']
assert (ROOT / 'artifacts/packaged_desktop_check.json').stat().st_mtime >= exe.stat().st_mtime, 'Run acceptance on the latest EXE first'
inventory = list(CArchiveReader(str(exe)).toc)
assert not any('settings.json' in name or 'lockfile' in name for name in inventory)
assert sum(name.endswith('.onnx') for name in inventory) == 2
archive_reader = CArchiveReader(str(exe))
hero_names = [name for name in inventory if name.replace(chr(92), '/').startswith('data/heroes/')]
for name in hero_names:
    row = json.loads(archive_reader.extract(name))
    assert row.get('build_mode_verified') and row.get('build_mode') == 'aram-mayhem'

release = ROOT.parent / 'HexCompanion-Windows-x64.zip'
with zipfile.ZipFile(release, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
    archive.write(exe, 'HexCompanion/HexCompanion.exe')
    for filename in ('使用说明.txt', 'THIRD_PARTY.txt'):
        archive.write(ROOT / 'packaging' / filename, 'HexCompanion/' + filename)
    for path in (ROOT / 'packaging/licenses').rglob('*'):
        if path.is_file() and '__pycache__' not in path.parts:
            archive.write(path, 'HexCompanion/licenses/' + path.relative_to(ROOT / 'packaging/licenses').as_posix())
    archive.write(ROOT / 'artifacts/packaged_desktop_check.json', 'HexCompanion/verification.json')

evidence = {'packaged_desktop_check.json', 'unit_tests_release.log', 'mayhem_build_refresh_result.json',
            'companion_interaction_result.json', 'panel_ui_result.json'}
source = ROOT.parent / 'hex-companion-source.zip'
with zipfile.ZipFile(source, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
    for path in ROOT.rglob('*'):
        relative = path.relative_to(ROOT)
        if not path.is_file() or any(part in {'.venv', '.build-cache', '__pycache__', '.git', '.superpowers', 'dist'} for part in relative.parts):
            continue
        if relative.as_posix() == 'data/settings.json' or path.suffix in ('.pyc', '.tmp'):
            continue
        if relative.as_posix().startswith('data/heroes/') and not json.loads(path.read_text(encoding='utf-8')).get('build_mode_verified'):
            continue
        if relative.parts[0] == 'artifacts' and path.name not in evidence:
            continue
        if len(relative.parts) > 1 and relative.parts[0] not in {'aram_demo', 'tests', 'scripts', 'data', 'packaging', 'artifacts', 'docs'}:
            continue
        archive.write(path, 'opgg-aram-demo/' + relative.as_posix())
shutil.copyfile(source, ROOT.parent / 'opgg-aram-demo-source.zip')

result = {'status': 'passed', 'exe_bytes': exe.stat().st_size,
          'sha256': hashlib.file_digest(exe.open('rb'), 'sha256').hexdigest(),
          'private_settings_excluded': True, 'ocr_models': [name for name in inventory if name.endswith('.onnx')],
          'packaged_check': check, 'archives': []}
for path in (release, source):
    with zipfile.ZipFile(path) as archive:
        assert archive.testzip() is None
        assert not any(name.endswith('settings.json') for name in archive.namelist())
        if path == release:
            assert hashlib.sha256(archive.read('HexCompanion/HexCompanion.exe')).hexdigest() == result['sha256']
        result['archives'].append({'path': str(path), 'bytes': path.stat().st_size, 'entries': len(archive.namelist())})
(ROOT / 'artifacts/exe_release_result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
(ROOT.parent / 'HexCompanion.exe.sha256.txt').write_text(result['sha256'] + '  HexCompanion.exe\n', encoding='ascii')
print(json.dumps(result, ensure_ascii=False, indent=2))
