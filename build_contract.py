"""Portable artifact inventory; all relative paths are scoped to the output root."""
import hashlib
import json
from pathlib import Path
import re
import subprocess

from artwork.versions import ART_VERSION, EXTRACTOR_VERSION
from deployment import APP_VERSION
from sharing import CARD_VERSION

ROOT_FILES = {'index.html', '404.html', 'LICENSE', '.nojekyll', 'build-metrics.json',
              'build-manifest.json', 'deployment.json'}
PATTERNS = (
    r'works/[A-Za-z0-9_-]+\.html',
    r'data/(site-catalog|share-index)\.json',
    r'static/(app|static-api|sharing|deployment)\.js', r'static/style\.css',
    r'static/artwork/(?:base|[a-f0-9]{20}|[0-9A-Za-z]+-[0-9A-Za-z]+-[a-f0-9]{16}-[a-f0-9]{12})\.svg',
    r'static/artwork/(?:manifest\.json|base\.version|\.artwork\.lock)',
    r'static/share/(?:[a-f0-9]{64}\.png|\.share\.lock|\.artwork\.lock)',
)


def validate_output(output):
    """Refuse mixed outputs, never silently delete an integrator's files."""
    output = Path(output)
    for path in [output, *output.parents]:
        if path.is_symlink():
            raise ValueError('Output must not traverse a symlink')
    if output.exists():
        for path in output.rglob('*'):
            if path.is_symlink():
                raise ValueError('Symlink in output: ' + str(path))
            relative = path.relative_to(output).as_posix()
            if path.is_file() and relative not in ROOT_FILES and not any(re.fullmatch(pattern, relative) for pattern in PATTERNS):
                raise ValueError('Output contains an unowned file: ' + relative)


def source_identity(root):
    # A source export may explicitly provide its pinned SHA via --source-sha.
    try:
        top = subprocess.check_output(['git', 'rev-parse', '--show-toplevel'], cwd=root, text=True, stderr=subprocess.DEVNULL).strip()
        if Path(top).resolve() != Path(root).resolve():
            return None, None
        sha = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True, stderr=subprocess.DEVNULL).strip()
        dirty = bool(subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=normal'], cwd=root, text=True))
        return sha, dirty
    except (OSError, subprocess.CalledProcessError):
        return None, None


def write_manifest(output, deployment, catalog_updated, source_sha=None, source_dirty=None):
    output = Path(output)
    # Synchronization files are not resources. Keep the artwork provenance
    # manifest: existing review tools consume it, and it contains public data.
    for relative in ('static/artwork/.artwork.lock', 'static/share/.share.lock', 'static/share/.artwork.lock'):
        (output / relative).unlink(missing_ok=True)
    files = {}
    for path in sorted(output.rglob('*')):
        if path.is_file() and path.name != 'build-manifest.json':
            data = path.read_bytes()
            files[path.relative_to(output).as_posix()] = {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
    manifest = {
        'schema_version': 1, 'app_version': APP_VERSION, 'source_sha': source_sha,
        'source_dirty': source_dirty, 'deployment': deployment.frontend(),
        'catalog': {'updated_at': catalog_updated, 'sha256': files['data/site-catalog.json']['sha256']},
        'versions': {'artwork': ART_VERSION, 'extractor': EXTRACTOR_VERSION, 'share_card': CARD_VERSION},
        'payload_file_count': len(files), 'payload_bytes': sum(item['bytes'] for item in files.values()),
        'inventory_sha256': hashlib.sha256(json.dumps(files, sort_keys=True, separators=(',', ':')).encode()).hexdigest(),
        'files': files,
        'inventory_scope': 'All files except build-manifest.json (self hash excluded).',
        'artifact_file_count': len(files) + 1, 'artifact_bytes': 0,
    }
    while True:
        encoded = (json.dumps(manifest, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
        total = manifest['payload_bytes'] + len(encoded)
        if total == manifest['artifact_bytes']:
            break
        manifest['artifact_bytes'] = total
    (output / 'build-manifest.json').write_bytes(encoded)
    return manifest
