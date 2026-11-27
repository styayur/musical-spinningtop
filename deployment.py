"""Single source of truth for supported public deployments (no network access)."""
import base64
from dataclasses import dataclass
import html
import json
import re

APP_VERSION = '2.1.1-dev'
TARGETS = {
    'github': ('https://styayur.github.io', '/musical-spinningtop/', '.html'),
    'personal': ('https://styayur.co.uk', '/spinningtop/', ''),
}


def work_key(identity):
    return base64.urlsafe_b64encode(str(identity).encode('utf-8')).decode('ascii').rstrip('=')


def work_id(key):
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,400}', key or ''):
        return None
    try:
        identity = base64.urlsafe_b64decode(key + '=' * (-len(key) % 4)).decode('utf-8')
        return identity if identity and work_key(identity) == key else None
    except (ValueError, UnicodeError):
        return None


@dataclass(frozen=True)
class Deployment:
    target: str

    def __post_init__(self):
        if self.target not in TARGETS:
            raise ValueError('Unknown deployment target: ' + self.target)

    @property
    def public_origin(self):
        return TARGETS[self.target][0]

    @property
    def base_path(self):
        return TARGETS[self.target][1]

    @property
    def work_suffix(self):
        return TARGETS[self.target][2]

    @property
    def public_base(self):
        return self.public_origin + self.base_path

    def public_url(self, identity):
        return self.public_base + 'works/' + work_key(identity) + self.work_suffix

    def frontend(self, static=True):
        return {'schema_version': 1, 'target': self.target, 'public_origin': self.public_origin,
                'base_path': self.base_path, 'public_base': self.public_base,
                'work_prefix': 'works/', 'work_suffix': self.work_suffix,
                'assets_path': './static/' if static else '/static/', 'catalog_path': './data/site-catalog.json',
                'share_index_path': './data/share-index.json',
                'local_card_path': './static/share/' if static else '/share-cards/',
                'artwork_path': './static/artwork/' if static else '/artwork/',
                'mode': 'static' if static else 'flask',
                'index_robots': 'index,follow', 'missing_robots': 'noindex'}


def get_deployment(target='github'):
    return Deployment(target)


DEFAULT = get_deployment()
PUBLIC_ORIGIN, BASE_PATH, PUBLIC_BASE = DEFAULT.public_origin, DEFAULT.base_path, DEFAULT.public_base


def page_shell(template, deployment=DEFAULT, static=False, home=None):
    if 'id="deploymentConfig"' in template:
        return template
    base = home if home is not None else ('./' if static else '/')
    config = deployment.frontend(static)
    template = template.replace('href="/static/', 'href="' + config['assets_path']).replace('src="/static/', 'src="' + config['assets_path'])
    if static:
        script = '<script src="' + config['assets_path']
        template = template.replace(script + 'app.js">', script + 'static-api.js"></script>\n  ' + script + 'app.js">')
    encoded = json.dumps(config, ensure_ascii=False).replace('<', '\\u003c').replace('&', '\\u0026')
    head = '<base href="' + html.escape(base, quote=True) + '">\n'
    head += '<script type="application/json" id="deploymentConfig">' + encoded + '</script>'
    return template.replace('<!-- DEPLOYMENT_HEAD -->', head)


def home_metadata(deployment=DEFAULT):
    return ('<link rel="canonical" href="' + deployment.public_base + '">\n'
            '<meta name="robots" content="' + deployment.frontend()['index_robots'] + '">')
