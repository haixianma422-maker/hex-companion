"""Freeze public build inputs without settings, logs or incomplete downloads."""
import json
import shutil
from pathlib import Path

STATIC_FILES=('champions.json','augment_display_tags.json','item_catalog.json',
              'tier_mapping_evidence.json','visual_catalog.json','augment_catalog.json')

def snapshot_seed(data,target):
    data,target=Path(data),Path(target)
    target.mkdir(parents=True,exist_ok=True)
    for name in STATIC_FILES:
        shutil.copyfile(data/name,target/name)
    for folder in ('item-icons','visual-assets','advice-icons'):
        for path in (data/folder).rglob('*'):
            if (path.is_file() and path.suffix.lower() in ('.png','.jpg','.jpeg','.json')
                    and path.name != 'settings.json' and 'lockfile' not in path.name.lower()):
                output=target/path.relative_to(data);output.parent.mkdir(parents=True,exist_ok=True)
                shutil.copyfile(path,output)
    for source,prefix in (('opgg',Path()),('qq101',Path('sources/qq101'))):
        if source=='qq101' and (data/prefix/'champions.json').is_file():
            value=json.loads((data/prefix/'champions.json').read_text(encoding='utf-8'))
            if value.get('source_id')==source:
                output=target/prefix/'champions.json';output.parent.mkdir(parents=True,exist_ok=True)
                output.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
        for path in (data/prefix/'heroes').glob('*.json'):
            try:row=json.loads(path.read_text(encoding='utf-8'))
            except (OSError,ValueError):continue
            if (row.get('build_mode_verified') is True and row.get('build_mode')=='aram-mayhem'
                    and row.get('champion_id')==int(path.stem)
                    and row.get('source_id', 'opgg')==source):
                output=target/prefix/'heroes'/path.name;output.parent.mkdir(parents=True,exist_ok=True)
                output.write_text(json.dumps(row,ensure_ascii=False,indent=2),encoding='utf-8')
    return target
