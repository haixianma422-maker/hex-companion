import json
import tempfile
import unittest
from pathlib import Path

class ReleaseSeedTests(unittest.TestCase):
    def test_both_verified_sources_and_images_are_frozen_without_local_files(self):
        from scripts.release_seed import snapshot_seed
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)/'data';target=Path(directory)/'seed'
            def put(relative,value):
                path=root/relative;path.parent.mkdir(parents=True,exist_ok=True)
                path.write_text(json.dumps(value),encoding='utf-8')
            for name in ('champions.json','augment_display_tags.json','item_catalog.json','tier_mapping_evidence.json','visual_catalog.json'):
                put(name,{'source':'public'})
            put('heroes/101.json',{'champion_id':101,'source_id':'opgg','build_mode_verified':True,'build_mode':'aram-mayhem'})
            put('heroes/222.json',{'champion_id':222,'build_mode_verified':False})
            put('sources/qq101/champions.json',{'source_id':'qq101','champions':[]})
            put('sources/qq101/heroes/101.json',{'champion_id':101,'source_id':'qq101','build_mode_verified':True,'build_mode':'aram-mayhem'})
            put('settings.json',{'install_path':'private'})
            put('logs/runtime.log',{'local':'private'})
            put('visual-assets/example.png',{'image':'fixture'})
            put('visual-assets/incomplete.tmp',{'temporary':True})
            snapshot_seed(root,target)
            self.assertTrue((target/'heroes/101.json').is_file())
            self.assertTrue((target/'sources/qq101/heroes/101.json').is_file())
            self.assertTrue((target/'sources/qq101/champions.json').is_file())
            self.assertTrue((target/'visual-assets/example.png').is_file())
            self.assertFalse((target/'heroes/222.json').exists())
            self.assertFalse((target/'settings.json').exists())
            self.assertFalse((target/'logs').exists())
            self.assertFalse((target/'visual-assets/incomplete.tmp').exists())
            put('sources/qq101/heroes/101.json',{'changed':True})
            self.assertTrue(json.loads((target/'sources/qq101/heroes/101.json').read_text())['build_mode_verified'])
