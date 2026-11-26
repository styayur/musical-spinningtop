"""Record v5 visual evidence separately from the immutable v4 acceptance pack."""
import hashlib
import io
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path
from xml.etree import ElementTree as ET

from PIL import Image
import resvg_py

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from artwork.generate import plan_artwork
from sharing import card_bytes


def main():
    output = ROOT / 'docs/ui-sharing-review'
    output.mkdir(parents=True, exist_ok=True)
    site = ROOT / '_site'
    catalogue = json.loads((site/'data/site-catalog.json').read_text(encoding='utf-8'))
    manifest = json.loads((site/'static/artwork/manifest.json').read_text(encoding='utf-8'))
    rows = {row['id']:row for row in catalogue['musicals']}
    rendered = {}
    unchanged = 0
    for row in rows.values():
        path = site/'static/artwork'/manifest['items'][row['id']]['filename']
        svg = path.read_text(encoding='utf-8')
        root = ET.fromstring(svg)
        assert not any(node.attrib.get('width') == '360' and node.attrib.get('height') == '480' for node in root)
        digest = hashlib.sha256(svg.encode()).hexdigest()
        if digest not in rendered:
            rendered[digest] = Image.open(io.BytesIO(resvg_py.svg_to_bytes(svg_string=svg, skip_system_fonts=True))).convert('RGBA')
            assert rendered[digest].getpixel((0,0))[3] == 0
        old, new = plan_artwork(row,art_version='4'),plan_artwork(row)
        assert old['basis'] == new['basis']
        for key in ('family','subjects','count','arrangement','modifiers','palette','mirror','detail','abstract_layout'):
            assert old['recipe'][key] == new['recipe'][key]
        unchanged += 1
    sample = json.loads((ROOT/'docs/artwork-review/sample-ids.json').read_text(encoding='utf-8'))
    sheet = Image.new('RGB',(6*200,6*260),'#161e2b')
    trace=[]
    for index,identity in enumerate(sample):
        row=rows[identity]
        plan=plan_artwork(row)
        art=Image.open(io.BytesIO(resvg_py.svg_to_bytes(svg_string=plan['svg'], skip_system_fonts=True))).convert('RGBA')
        art.thumbnail((180,240))
        sheet.paste(art,((index%6)*200+10,(index//6)*260+10),art)
        trace.append({key:plan[key] for key in ('id','basis','recipe','source_digest')})
    sheet.save(output/'artwork-v5-sheet.png')
    (output/'sample-trace.json').write_text(json.dumps(trace,ensure_ascii=False,indent=2),encoding='utf-8')
    longest=max(rows.values(),key=lambda row:len(row.get('title_zh') or row['title']))
    (output/'share-long-title.png').write_bytes(card_bytes(longest,plan_artwork(longest)['svg']))
    example={'id':'review:cjk','title':'夜幕與舞台・日本語の物語・한국어 뮤지컬','year':None,'intro_en':''}
    (output/'share-cjk-unknown-year.png').write_bytes(card_bytes(example,plan_artwork(example)['svg']))
    baseline_changed=subprocess.check_output(['git','diff','ca66e02','--','docs/artwork-review','artwork/extract.py','artwork/lexicon.py','data'],cwd=ROOT)
    assert not baseline_changed,'v4 evidence, extraction or catalogue changed'
    report={'total':len(rows),'all_svg_generated':True,'transparent_variant_count':len(rendered),
            'same_v4_composition_and_basis':unchanged,'art_version':5,'extractor_version':4,
            'families':dict(Counter(item['family'] for item in manifest['items'].values())),
            'sample_seed':'spinningtop-artwork-sample-2026-11-25','sample_ids':sample,
            'build':json.loads((site/'build-metrics.json').read_text(encoding='utf-8')),
            'cjk_card':'Synthetic typography/unknown-year fixture, not a catalogue entry.',
            'limits':'Transparency and invariant geometry are tested; this is not a new semantic accuracy evaluation.'}
    live=ROOT/'artifacts/ui-sharing-live-catalog.json'
    if live.exists():
        old=json.loads(live.read_text(encoding='utf-8'))
        fields=('id','title','title_zh','intro_en','intro_zh','year','intro_source','wiki_url')
        old_rows={row['id']:{key:row.get(key) for key in fields} for row in old['musicals']}
        new_rows={row['id']:{key:row.get(key) for key in fields} for row in rows.values()}
        assert old_rows==new_rows,'Published snapshot would change'
        assert old['updated_at']==catalogue['updated_at']
        report['live_snapshot_content_unchanged']=True
        report['live_snapshot_updated_at']=old['updated_at']
    (output/'stats.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')


if __name__=='__main__':
    main()
