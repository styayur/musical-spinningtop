import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from app import create_app
from build_contract import source_identity, validate_output
from build_site import build
from deployment import DEFAULT, get_deployment, page_shell, work_key
from sharing import work_html
from scripts.verify_build import verify

ROOT = Path(__file__).resolve().parents[1]
ROW = {'id':'en:42', 'title':'Example', 'intro_en':'Two sisters reunite.', 'year':2000,
       'wiki_url':'https://en.wikipedia.org/wiki/Example'}


class DeploymentTests(unittest.TestCase):
    def test_fixed_targets_and_unchanged_ids(self):
        self.assertEqual(DEFAULT.public_url('en:42'), 'https://styayur.github.io/musical-spinningtop/works/ZW46NDI.html')
        self.assertEqual(get_deployment('personal').public_url('en:42'), 'https://styayur.co.uk/spinningtop/works/ZW46NDI')
        for invalid in ('https://evil.example', '../personal', 'PERSONAL', ''):
            with self.assertRaises(ValueError):
                get_deployment(invalid)

    def test_sources_inside_host_repository_are_not_host_commits(self):
        with patch('build_contract.subprocess.check_output', return_value=str(ROOT.parent)):
            self.assertEqual(source_identity(ROOT), (None, None))
        with tempfile.TemporaryDirectory() as folder, patch('build_site.source_identity', return_value=(None,None)):
            with self.assertRaisesRegex(ValueError,'source-sha'):
                build(folder)

    def test_two_targets_render_identical_payload_and_strict_metadata(self):
        with tempfile.TemporaryDirectory() as folder:
            outputs = []
            for target in ('github', 'personal'):
                output = Path(folder)/target
                with patch('build_site.load_catalog',return_value=([ROW], 'fixed-time')), patch('build_site.read_json',return_value={}):
                    build(output, target)
                config = get_deployment(target)
                data = json.loads((output/'deployment.json').read_text())
                self.assertEqual(data, config.frontend())
                page = (output/'works'/(work_key(ROW['id'])+'.html')).read_text(encoding='utf-8')
                self.assertIn('<base href="'+config.base_path+'">',page)
                self.assertIn('property="og:url" content="'+config.public_url(ROW['id'])+'"',page)
                missing = (output/'404.html').read_text(encoding='utf-8')
                self.assertIn('name="robots" content="noindex"',missing)
                self.assertNotIn('property="og:url"',missing)
                manifest=json.loads((output/'build-manifest.json').read_text(encoding='utf-8'))
                self.assertEqual(manifest['artifact_file_count'],sum(p.is_file() for p in output.rglob('*')))
                self.assertEqual(manifest['artifact_bytes'],sum(p.stat().st_size for p in output.rglob('*') if p.is_file()))
                for name, item in manifest['files'].items():
                    self.assertEqual(hashlib.sha256((output/name).read_bytes()).hexdigest(),item['sha256'])
                self.assertEqual(manifest['catalog']['sha256'], manifest['files']['data/site-catalog.json']['sha256'])
                self.assertFalse(list(output.rglob('*.lock')))
                verify(output, manifest['source_sha'], target, allow_dirty=True)
                with self.assertRaisesRegex(ValueError, 'target'):
                    verify(output, manifest['source_sha'], 'wrong', allow_dirty=True)
                outputs.append(output)
            for relative in ['data/site-catalog.json','static/app.js','static/sharing.js','static/deployment.js','static/style.css']:
                self.assertEqual((outputs[0]/relative).read_bytes(), (outputs[1]/relative).read_bytes())
            for path in (outputs[0]/'static').rglob('*'):
                if path.suffix in ('.png','.svg'):
                    self.assertEqual(path.read_bytes(),(outputs[1]/path.relative_to(outputs[0])).read_bytes())
            changed = outputs[0]/'static/app.js'
            changed.write_text('tampered', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'inventory'):
                verify(outputs[0], manifest['source_sha'], 'github', allow_dirty=True)

    def test_output_refuses_private_or_host_files_without_deleting(self):
        for relative in ('private.sqlite3','_worker.js','_routes.json','_headers','data/private.json','static/custom.js'):
            with tempfile.TemporaryDirectory() as folder:
                path=Path(folder)/relative;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('keep')
                with self.assertRaisesRegex(ValueError,'unowned'):
                    build(folder,'personal')
                self.assertEqual(path.read_text(),'keep')
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(ValueError,'SHA'):
                build(folder,source_sha='bad')

    def test_flask_personal_stays_local_offline_and_aliases_are_readonly(self):
        with tempfile.TemporaryDirectory() as folder:
            app=create_app(folder,background=False,deployment_target='personal')
            try:
                with patch('app.load_catalog', return_value=([ROW],'')), patch('app.read_json',return_value={}), \
                     patch('requests.sessions.Session.request',side_effect=AssertionError('network')), \
                     patch.object(app.extensions['store'],'pick',side_effect=AssertionError('draw')):
                    client=app.test_client()
                    self.assertIn(b'<base href="/">', client.get('/').data)
                    for suffix in ('','.html','/'):
                        response=client.get('/works/'+work_key(ROW['id'])+suffix)
                        self.assertEqual(response.status_code,200)
                        self.assertIn(get_deployment('personal').public_url(ROW['id']).encode(),response.data)
                    info=client.get('/api/share?id=en:42').get_json()
                    self.assertEqual(info['publication'],'unverified')
                    self.assertEqual(info['url'],get_deployment('personal').public_url(ROW['id']))
                    with client.get(info['image']) as image:
                        self.assertEqual(image.status_code,200)
                    self.assertEqual(client.get('/works/unknown').status_code,404)
            finally:
                app.extensions['library'].pool.shutdown()
