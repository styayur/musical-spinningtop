"""Verify a pinned mount artifact using only the Python standard library."""
import argparse
import hashlib
import json
import sys
from pathlib import Path, PurePosixPath


def verify(output, source_sha, target, allow_dirty=False):
    output = Path(output)
    if any(path.is_symlink() for path in [output, *output.parents, output / 'build-manifest.json']):
        raise ValueError('Symlink in artifact path')
    manifest = json.loads((output / 'build-manifest.json').read_text(encoding='utf-8'))
    if manifest['schema_version'] != 1 or manifest['source_sha'] != source_sha:
        raise ValueError('Manifest schema/source SHA mismatch')
    if manifest['deployment']['target'] != target:
        raise ValueError('Deployment target mismatch')
    if manifest['source_dirty'] is True and not allow_dirty:
        raise ValueError('Dirty source build; use a clean pinned checkout')
    files = manifest['files']
    for name in files:
        parts = PurePosixPath(name)
        if not parts.parts or parts.is_absolute() or '..' in parts.parts or '\\' in name or ':' in name or parts.as_posix() != name:
            raise ValueError('Unsafe manifest path')
    actual = {}
    for path in output.rglob('*'):
        if path.is_symlink():
            raise ValueError('Symlink in artifact')
        if path.is_file() and path != output / 'build-manifest.json':
            data = path.read_bytes()
            actual[path.relative_to(output).as_posix()] = {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
    if actual != files:
        raise ValueError('Artifact files differ from inventory')
    inventory_hash = hashlib.sha256(json.dumps(files, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    if inventory_hash != manifest['inventory_sha256']:
        raise ValueError('Inventory digest mismatch')
    size = sum(item['bytes'] for item in actual.values())
    if (len(actual), size, len(actual) + 1, size + (output / 'build-manifest.json').stat().st_size) != (
        manifest['payload_file_count'], manifest['payload_bytes'], manifest['artifact_file_count'], manifest['artifact_bytes']
    ):
        raise ValueError('Artifact totals mismatch')
    if json.loads((output / 'deployment.json').read_text(encoding='utf-8')) != manifest['deployment']:
        raise ValueError('Deployment configuration mismatch')
    if manifest['catalog']['sha256'] != actual['data/site-catalog.json']['sha256']:
        raise ValueError('Catalogue digest mismatch')
    return {key: manifest[key] for key in ('source_sha', 'source_dirty', 'artifact_file_count', 'artifact_bytes', 'inventory_sha256')}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--source-sha', required=True)
    parser.add_argument('--target', required=True)
    parser.add_argument('--allow-dirty', action='store_true', help='Development evidence only; not for integration')
    args = parser.parse_args()
    json.dump(verify(args.output, args.source_sha, args.target, args.allow_dirty), sys.stdout, indent=2)
    sys.stdout.write('\n')
