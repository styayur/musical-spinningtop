import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from xml.etree import ElementTree as ET

from PIL import Image
from app import create_app
from build_site import build
from artwork.generate import ensure_base, plan_artwork
from artwork.draw import render_base
from artwork.versions import ART_VERSION, EXTRACTOR_VERSION
from sharing import card_bytes, card_layout, ensure_card, font, public_url, work_html, work_id, work_key


class SharingTests(unittest.TestCase):
    def test_rebuild_removed_work_becomes_unavailable_not_another_draw(self):
        first = {'id':'en:one','title':'First','intro_en':'A letter arrives.'}
        second = {'id':'en:two','title':'Second','intro_en':''}
        with tempfile.TemporaryDirectory() as folder:
            with patch('build_site.load_catalog',return_value=([first,second],'')), patch('build_site.read_json',return_value={}):
                build(folder)
            with patch('build_site.load_catalog',return_value=([second],'')), patch('build_site.read_json',return_value={}):
                build(folder)
            path = Path(folder)/'works'/(work_key(first['id'])+'.html')
            removed = path.read_text(encoding='utf-8')
            self.assertIn('Work unavailable',removed)
            self.assertNotIn('property="og:url"',removed)
            index = json.loads((Path(folder)/'data/share-index.json').read_text(encoding='utf-8'))
            self.assertEqual(set(index),{'en:two'})

    def test_ids_roundtrip_and_untrusted_keys(self):
        for identity in ('en:123', '中文:日本語/한국어', '../weird?x=1', '</script>'):
            key = work_key(identity)
            self.assertEqual(work_id(key), identity)
            self.assertNotIn('/', key)
            self.assertTrue(public_url(identity).startswith('https://styayur.github.io/musical-spinningtop/works/'))
        for key in ('../../foo', '%2e', '!', 'a', 'a' * 401, ''):
            self.assertIsNone(work_id(key))

    def test_palette_only_version_preserves_composition(self):
        self.assertEqual((ART_VERSION, EXTRACTOR_VERSION), ('5', '4'))
        for identity, intro in [('a','Two sisters are reunited.'), ('b',''), ('c','A train crosses the city.')]:
            row = {'id': identity, 'title':'Example', 'intro_en':intro}
            old = plan_artwork(row, art_version='4')
            new = plan_artwork(row)
            self.assertEqual(old['basis'], new['basis'])
            for field in ('family','subjects','arrangement','count','modifiers','palette','mirror','detail','abstract_layout'):
                self.assertEqual(old['recipe'][field], new['recipe'][field])
        svg = render_base()
        root = ET.fromstring(svg)
        self.assertFalse(any(node.attrib.get('width') == '360' and node.attrib.get('height') == '480' for node in root))
        self.assertNotIn('x="18" y="18"', svg)
        self.assertIn('#f5f0e8', svg)
        self.assertNotIn('#f4efe6', svg)

    def test_old_base_migrates_and_cache_stays_stable(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'base.svg'
            path.write_text('old ivory base', encoding='utf-8')
            ensure_base(folder)
            self.assertEqual(path.read_text(encoding='utf-8'), render_base())
            with patch('artwork.generate.render_base', side_effect=AssertionError('cache')):
                ensure_base(folder)

    def test_cards_cjk_long_title_unknown_year_and_cache(self):
        title = '长标题與繁體中文・日本語の舞台・한국어 뮤지컬 ' * 6
        size, lines = card_layout(title)
        self.assertTrue(all(font(size).getlength(line) <= 660 for line in lines))
        row = {'title':title, 'year':None}
        data = card_bytes(row, render_base())
        image = Image.open(io.BytesIO(data))
        self.assertEqual(image.size, (1200,630))
        self.assertEqual(image.getpixel((0,0)), (22,30,43))
        with tempfile.TemporaryDirectory() as folder:
            first = ensure_card(row, render_base(), folder)
            with patch('sharing.card_bytes', side_effect=AssertionError('cache miss')):
                self.assertEqual(ensure_card(row, render_base(), folder), first)
            self.assertNotEqual(ensure_card({**row,'year':2020}, render_base(), folder), first)

    def test_metadata_is_server_rendered_and_escaped(self):
        template = (Path(__file__).resolve().parents[1] / 'templates/index.html').read_text(encoding='utf-8')
        row = {'id':'en:42','title':'A </script><script>alert(1)</script> & B','intro_en':'Synopsis'}
        result = work_html(template,row,'https://example.com/image.png',static=True)
        self.assertIn('property="og:image" content="https://example.com/image.png"',result)
        self.assertIn('name="twitter:card" content="summary_large_image"',result)
        self.assertNotIn('<script>alert(1)</script>',result)
        encoded = result.split('id="sharedWork">')[1].split('</script>')[0]
        self.assertEqual(json.loads(encoded)['id'],row['id'])
        self.assertIn('Synopsis',result)

    def test_flask_work_and_share_never_draw_or_archive(self):
        row = {'id':'en:42','title':'Shared title','intro_en':'Two sisters are reunited.'}
        with tempfile.TemporaryDirectory() as folder:
            application = create_app(folder,background=False)
            library = application.extensions['library']
            try:
                with patch('app.load_catalog',return_value=([row],'')), patch('app.read_json',return_value={}), \
                     patch.object(application.extensions['store'],'pick',side_effect=AssertionError('draw')), \
                     patch.object(application.extensions['store'],'archive_daily',side_effect=AssertionError('archive')):
                    client = application.test_client()
                    response = client.get('/works/' + work_key(row['id']) + '.html')
                    self.assertEqual(response.status_code,200)
                    self.assertIn(b'property="og:image" content="https://',response.data)
                    info = client.get('/api/share?id=en:42').get_json()
                    self.assertTrue(info['available'])
                    self.assertNotIn('localhost',info['url'])
                    with client.get(info['image']) as image:
                        self.assertEqual(image.status_code,200)
                    self.assertFalse(client.get('/api/share?id=local:only').get_json()['available'])
                    self.assertEqual(client.get('/works/unknown.html').status_code,404)
                with application.extensions['store'].connect() as db:
                    self.assertEqual(db.execute('SELECT count(*) FROM daily').fetchone()[0],0)
            finally:
                library.pool.shutdown()
