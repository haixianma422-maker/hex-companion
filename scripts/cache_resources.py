"""Prepare a reusable offline cache of base art and core game icons.

Run explicitly during maintenance; gameplay never downloads the whole catalog.
Existing valid images are reused. No skins or account data are requested.
"""
import argparse
import hashlib
import json
import sys
import tempfile
import threading
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from aram_demo.visual_assets import VisualAssetCache
from aram_demo.advice_icons import AdviceIconCache
from aram_demo.item_icons import ITEM_PATCH

def read_json(url):
    request=urllib.request.Request(url,headers={'User-Agent':'HexCompanion/1.0'})
    with urllib.request.urlopen(request,timeout=12) as response:
        raw=response.read(8_000_001)
    if len(raw)>8_000_000:raise ValueError('Metadata too large')
    return json.loads(raw.decode('utf-8-sig'))

def write_json(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',dir=path.parent,suffix='.tmp',delete=False) as output:
        temporary=Path(output.name)
        json.dump(value,output,ensure_ascii=False,indent=2)
    try:temporary.replace(path)
    finally:temporary.unlink(missing_ok=True)

def prepare_catalog(catalog,champions,augments):
    # Map numeric champion identity to Riot's exact canonical asset basename.
    rows={str(row['key']):row for row in champions['data'].values()}
    skills=[];changed=0
    for cid,entry in catalog['champions'].items():
        row=rows.get(cid)
        if not row:continue
        alias=row['id']
        previous=entry.get('splash','')
        if previous.startswith('https://game.gtimg.cn/'):
            entry['splash_fallback']=previous
        entry['splash']=f'https://ddragon.leagueoflegends.com/cdn/img/champion/splash/{alias}_0.jpg'
        entry['splash_source']=f'https://ddragon.leagueoflegends.com/cdn/{ITEM_PATCH}/data/en_US/championFull.json'
        entry['skill_icons']={}
        for key,spell in zip(('Q','W','E'),row.get('spells',[])[:3]):
            filename=spell.get('image',{}).get('full','')
            url=f'https://ddragon.leagueoflegends.com/cdn/{ITEM_PATCH}/img/spell/{filename}'
            if AdviceIconCache.valid_url(url):
                entry['skill_icons'][key]=url;skills.append(url)
        changed+=1
    if not changed:raise ValueError('No verified champion identities in Riot metadata')
    for row in augments:
        aid=str(row.get('augmentID',''))
        if aid not in catalog['augments']:continue
        entry=catalog['augments'][aid]
        fallback=row.get('small_Icon')
        if VisualAssetCache._key('augment',aid) and isinstance(fallback,str):
            entry['augment_fallback']=fallback
    catalog['sources']['splash']='https://ddragon.leagueoflegends.com/cdn/img/champion/splash/{canonical_id}_0.jpg'
    catalog['sources']['skills']=f'https://ddragon.leagueoflegends.com/cdn/{ITEM_PATCH}/data/en_US/championFull.json'
    catalog['generated_at']=datetime.now(timezone.utc).isoformat()
    return list(dict.fromkeys(skills))

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=ROOT/'data')
    parser.add_argument('--augment-metadata',type=Path)
    parser.add_argument('--workers',type=int,default=6,choices=range(1,9))
    parser.add_argument('--only',choices=('all','reported'),default='all')
    args=parser.parse_args()
    root=args.root;catalog=json.loads((root/'visual_catalog.json').read_text(encoding='utf-8'))
    hero_url=f'https://ddragon.leagueoflegends.com/cdn/{ITEM_PATCH}/data/en_US/championFull.json'
    spell_url=f'https://ddragon.leagueoflegends.com/cdn/{ITEM_PATCH}/data/en_US/summoner.json'
    augment_url='https://game.gtimg.cn/images/lol/act/img/js/kiwi/kiwi_augments.json'
    heroes=read_json(hero_url)
    augments=json.loads(args.augment_metadata.read_text(encoding='utf-8')) if args.augment_metadata else read_json(augment_url)
    skills=prepare_catalog(catalog,heroes,augments)
    summoners=read_json(spell_url)
    for row in summoners['data'].values():
        url=f"https://ddragon.leagueoflegends.com/cdn/{ITEM_PATCH}/img/spell/{row['image']['full']}"
        if AdviceIconCache.valid_url(url):skills.append(url)
    write_json(root/'visual_catalog.json',catalog)
    jobs=[('splash',101),('augment',1029),('augment',1097)]
    reported=list(catalog['champions']['101'].get('skill_icons',{}).values())
    jobs += [('advice',url) for url in reported]
    if args.only=='all':
        jobs += [(kind,int(cid)) for cid in catalog['champions'] for kind in ('splash','portrait')]
        jobs += [('augment',int(aid)) for aid in catalog['augments']]
        jobs += [('advice',url) for url in reported+skills]
    else:jobs += [('advice',url) for url in reported]
    jobs=list(dict.fromkeys(jobs));local=threading.local()
    def cache_one(job):
        if not hasattr(local,'visual'):
            local.visual=VisualAssetCache(root,download_timeout=12)
            local.advice=AdviceIconCache(root)
        kind,key=job
        try:
            if kind=='advice':
                local.advice.ensure([key]);path=local.advice.path(key)
            else:
                local.visual.ensure([job]);path=local.visual.path(kind,key)
            if path is None:return {'kind':kind,'key':key,'cached':False}
            raw=path.read_bytes()
            return {'kind':kind,'key':key,'cached':True,'path':str(path.relative_to(root)),
                    'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
        except Exception as error:return {'kind':kind,'key':key,'cached':False,'error':str(error)}
    manifest={'generated_at':datetime.now(timezone.utc).isoformat(),'patch':ITEM_PATCH,
              'metadata_sources':[hero_url,spell_url,augment_url],'requested':len(jobs),'assets':[]}
    path=root/'visual-assets/resource-cache-manifest.json'
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for future in as_completed([pool.submit(cache_one,job) for job in jobs]):
            manifest['assets'].append(future.result())
            count=len(manifest['assets'])
            if count%40==0 or count==len(jobs):
                write_json(path,manifest)
                print(json.dumps({'done':count,'total':len(jobs),'cached':sum(row['cached'] for row in manifest['assets'])}),flush=True)
    failed=[row for row in manifest['assets'] if not row['cached']]
    print(json.dumps({'manifest':str(path),'failed':failed},ensure_ascii=False),flush=True)
    return 1 if failed else 0

if __name__=='__main__':sys.exit(main())
