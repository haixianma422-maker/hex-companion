"""Create the share package for the folder build, bound to its actual acceptance report."""
import argparse
import hashlib
import json
import zipfile
from pathlib import Path
from PyInstaller.archive.readers import CArchiveReader

ROOT=Path(__file__).resolve().parents[1]
def sha(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()

def package(exe,check_path):
    exe,check_path=Path(exe).resolve(),Path(check_path).resolve()
    check=json.loads(check_path.read_text(encoding='utf-8'))
    assert check['status']=='passed' and check['frozen'] and check['clean_exit']
    assert check['exe_sha256']==sha(exe),'Acceptance report belongs to another EXE'
    assert Path(check['executable']).resolve()==exe,'Acceptance executable path differs'
    app_dir=exe.parent
    internal=app_dir/'_internal'
    names={path.relative_to(internal).as_posix():path for path in internal.rglob('*') if path.is_file()}
    assert not any('settings.json' in name or 'lockfile' in name or name.startswith('data/logs/') for name in names)
    assert not any(path.suffix in ('.log','.tmp') for path in app_dir.rglob('*')),'Runtime files inside the build folder'
    models=[name for name in names if name.endswith('.onnx')]
    assert models==['models/PP-OCRv6_rec_small.onnx'],models
    assert not any(name.startswith(('cv2/','rapidocr/','shapely/')) for name in names),'RapidOCR pipeline bundled'
    for source,prefix in (('opgg','data/heroes/'),('qq101','data/sources/qq101/heroes/')):
        snapshots=[name for name in names if name.startswith(prefix) and name.endswith('.json')]
        assert snapshots,f'No verified seed for {source}'
        for name in snapshots:
            row=json.loads(names[name].read_text(encoding='utf-8'))
            assert row.get('build_mode_verified') is True and row.get('build_mode')=='aram-mayhem'
            assert row.get('source_id','opgg')==source
    assert 'data/sources/qq101/champions.json' in names
    assert {'aram_demo/qml/Overlay.qml','aram_demo/qml/Panel.qml','aram_demo/qml/Settings.qml'} <= set(names)
    pyz=CArchiveReader(str(exe)).open_embedded_archive('PYZ.pyz')
    assert all(name in pyz.toc for name in ('aram_demo.qq101','aram_demo.opgg','aram_demo.qt_overlay','aram_demo.qt_settings',
                                            'aram_demo.ocr','winrt.windows.media.ocr'))
    assert 'tkinter' not in pyz.toc
    inventory=json.loads(names['data/visual-assets/resource-cache-manifest.json'].read_text(encoding='utf-8'))
    for asset in inventory['assets']:
        name='data/'+Path(asset['path']).as_posix()
        assert name in names,f'Resource not bundled: {name}'
        assert sha(names[name])==asset['sha256']
    output=app_dir.parent/'HexCompanion-Windows-x64.zip'
    with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as bundle:
        for path in sorted(app_dir.rglob('*')):
            if path.is_file():
                bundle.write(path,'HexCompanion/'+path.relative_to(app_dir).as_posix())
        bundle.write(ROOT/'LICENSE','HexCompanion/LICENSE')
        for name in ('使用说明.txt','THIRD_PARTY.txt'):
            bundle.write(ROOT/'packaging'/name,'HexCompanion/'+name)
        for path in (ROOT/'packaging/licenses').rglob('*'):
            if path.is_file() and '__pycache__' not in path.parts:
                bundle.write(path,'HexCompanion/licenses/'+path.relative_to(ROOT/'packaging/licenses').as_posix())
        bundle.write(check_path,'HexCompanion/verification.json')
    with zipfile.ZipFile(output) as bundle:
        assert bundle.testzip() is None
        assert hashlib.sha256(bundle.read('HexCompanion/HexCompanion.exe')).hexdigest()==check['exe_sha256']
    files=[path for path in app_dir.rglob('*') if path.is_file()]
    result={'status':'passed','exe':str(exe),'exe_sha256':check['exe_sha256'],
            'folder':str(app_dir),'folder_files':len(files),'folder_bytes':sum(path.stat().st_size for path in files),
            'zip':str(output),'zip_sha256':sha(output),'zip_bytes':output.stat().st_size,
            'ocr_models':models,'cached_resources':len(inventory['assets']),
            'private_files_excluded':True,'offline_acceptance':str(check_path),'live_game_tested':False}
    # Written beside the app folder, so a later package never zips them.
    (app_dir.parent/'HexCompanion.exe.sha256.txt').write_text(check['exe_sha256']+'  HexCompanion/HexCompanion.exe\n',encoding='ascii')
    (app_dir.parent/'release_manifest.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return result

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--exe',type=Path,required=True)
    parser.add_argument('--check',type=Path,required=True)
    args=parser.parse_args();package(args.exe,args.check)
