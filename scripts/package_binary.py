"""Create a local EXE share package bound to its actual acceptance report."""
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
    archive=CArchiveReader(str(exe))
    names={name.replace('\\','/'):name for name in archive.toc}
    assert not any('settings.json' in name or 'lockfile' in name or '/logs/' in name for name in names)
    models=[name for name in names if name.endswith('.onnx')]
    assert len(models)==2
    for source,prefix in (('opgg','data/heroes/'),('qq101','data/sources/qq101/heroes/')):
        snapshots=[name for name in names if name.startswith(prefix) and name.endswith('.json')]
        assert snapshots,f'No verified seed for {source}'
        for name in snapshots:
            row=json.loads(archive.extract(names[name]))
            assert row.get('build_mode_verified') is True and row.get('build_mode')=='aram-mayhem'
            assert row.get('source_id','opgg')==source
    assert 'data/sources/qq101/champions.json' in names
    pyz=archive.open_embedded_archive('PYZ.pyz')
    assert all(name in pyz.toc for name in ('aram_demo.qq101','aram_demo.opgg','aram_demo.tk_images'))
    inventory=json.loads(archive.extract(names['data/visual-assets/resource-cache-manifest.json']))
    for asset in inventory['assets']:
        name='data/'+Path(asset['path']).as_posix()
        assert name in names,f'Resource not bundled: {name}'
        assert hashlib.sha256(archive.extract(names[name])).hexdigest()==asset['sha256']
    output=exe.parent/'HexCompanion-Windows-x64.zip'
    with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as bundle:
        bundle.write(exe,'HexCompanion/HexCompanion.exe')
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
    result={'status':'passed','exe':str(exe),'exe_sha256':check['exe_sha256'],'exe_bytes':exe.stat().st_size,
            'zip':str(output),'zip_sha256':sha(output),'zip_bytes':output.stat().st_size,
            'ocr_models':models,'cached_resources':len(inventory['assets']),
            'private_files_excluded':True,'offline_acceptance':str(check_path),'live_game_tested':False}
    (exe.parent/'HexCompanion.exe.sha256.txt').write_text(check['exe_sha256']+'  HexCompanion.exe\n',encoding='ascii')
    (exe.parent/'release_manifest.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return result

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--exe',type=Path,required=True)
    parser.add_argument('--check',type=Path,required=True)
    args=parser.parse_args();package(args.exe,args.check)
