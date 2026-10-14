import copy
import unittest
from scripts.cache_resources import prepare_catalog

class ResourceCatalogTests(unittest.TestCase):
    def test_asset_mapping_uses_numeric_identity_and_exact_riot_basename(self):
        catalog={'champions':{'9':{'alias':'FiddleSticks','splash':'https://game.gtimg.cn/original.jpg'}},
                 'augments':{'1029':{'augment':'https://game.gtimg.cn/large.png'}},'sources':{}}
        riot={'data':{'different_key':{'key':'9','id':'Fiddlesticks','spells':[{'image':{'full':'FiddlesticksQ.png'}}]}}}
        skills=prepare_catalog(catalog,riot,[{'augmentID':1029,'small_Icon':'https://game.gtimg.cn/small.png'}])
        self.assertTrue(catalog['champions']['9']['splash'].endswith('/Fiddlesticks_0.jpg'))
        self.assertEqual(catalog['champions']['9']['splash_fallback'],'https://game.gtimg.cn/original.jpg')
        self.assertTrue(skills[0].endswith('/FiddlesticksQ.png'))
        self.assertEqual(catalog['augments']['1029']['augment_fallback'],'https://game.gtimg.cn/small.png')

    def test_unmatched_champion_metadata_cannot_reassign_art(self):
        catalog={'champions':{'101':{'splash':'https://game.gtimg.cn/xerath.jpg'}},'augments':{},'sources':{}}
        before=copy.deepcopy(catalog)
        with self.assertRaises(ValueError):
            prepare_catalog(catalog,{'data':{'x':{'key':'222','id':'Jinx','spells':[]}}},[])
        self.assertEqual(catalog,before)
