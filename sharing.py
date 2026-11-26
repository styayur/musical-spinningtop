"""Public work identities, read-only HTML and offline original share cards."""
import base64
import hashlib
import html
import io
import json
import re
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
import resvg_py

from artwork.generate import _file_lock
from catalog import BASE

PUBLIC_BASE = 'https://styayur.github.io/musical-spinningtop/'
CARD_VERSION = '1'
FONT = BASE / 'assets/fonts/NotoSerifCJKsc-Regular.otf'


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


def public_url(identity):
    return PUBLIC_BASE + 'works/' + work_key(identity) + '.html'


@lru_cache(maxsize=24)
def font(size):
    return ImageFont.truetype(str(FONT), size)


def title_lines(title, size, width=660):
    """Wrap words where possible; CJK and long single tokens remain bounded."""
    lines, line = [], ''
    for char in ' '.join(str(title).split()):
        if line and font(size).getlength(line + char) > width:
            split = line.rfind(' ')
            if split > len(line) // 2:
                lines.append(line[:split])
                line = line[split + 1:] + char
            else:
                lines.append(line)
                line = char
        else:
            line += char
    if line:
        lines.append(line)
    return lines


def card_layout(title):
    for size in range(54, 19, -2):
        lines = title_lines(title, size)
        if len(lines) * (size + 15) <= 350:
            return size, lines
    lines = title_lines(title, 20)[:10]
    if len(title_lines(title, 20)) > 10:
        lines[-1] = lines[-1].rstrip()[:-1] + '…'
    return 20, lines


@lru_cache(maxsize=256)
def plate_png(svg):
    # Generated plates contain no text. Scanning host fonts here is unnecessary,
    # expensive and makes an offline build depend on the host's installed fonts.
    return resvg_py.svg_to_bytes(svg_string=svg, skip_system_fonts=True)


def card_bytes(row, svg):
    image = Image.new('RGBA', (1200, 630), '#161e2b')
    plate = Image.open(io.BytesIO(plate_png(svg))).convert('RGBA')
    plate.thumbnail((360, 480), Image.Resampling.LANCZOS)
    image.alpha_composite(plate, (790, 70))
    draw = ImageDraw.Draw(image)
    draw.text((64, 44), 'Spinning Top', font=font(28), fill='#c4a574')
    title = row.get('title_zh') or row.get('title') or 'Untitled'
    size, lines = card_layout(title)
    top = 145 + (350 - len(lines) * (size + 15)) // 2
    for line in lines:
        draw.text((64, top), line, font=font(size), fill='#f5f0e8')
        top += size + 15
    year = row.get('year')
    if isinstance(year, int) and not isinstance(year, bool) and 1 <= year <= 9999:
        draw.text((66, 535), str(year), font=font(25), fill='#c4a574')
    stream = io.BytesIO()
    image.convert('RGB').save(stream, format='PNG', compress_level=6)
    return stream.getvalue()


@lru_cache(maxsize=1)
def font_hash():
    return hashlib.sha256(FONT.read_bytes()).hexdigest()


def ensure_card(row, svg, directory):
    title = row.get('title_zh') or row.get('title') or 'Untitled'
    digest = hashlib.sha256(json.dumps([CARD_VERSION, title, row.get('year'), svg, font_hash()],
                                     ensure_ascii=False).encode('utf-8')).hexdigest()
    directory = Path(directory)
    name = digest + '.png'
    path = directory / name
    # Same lock protocol as artwork; atomically publish a complete image.
    if path.is_file():
        return name
    data = card_bytes(row, svg)
    with _file_lock(directory / '.share.lock'):
        if not path.is_file():
            temporary = directory / ('.card-' + digest + '.tmp')
            try:
                temporary.write_bytes(data)
                temporary.replace(path)
            finally:
                temporary.unlink(missing_ok=True)
    return name


def work_html(template, row=None, image_url=None, static=False, home='../'):
    """Crawler-visible metadata and content; JSON data never executes as code."""
    row = dict(row or {})
    valid = bool(row.get('id')) and not row.get('unavailable')
    title = row.get('title_zh') or row.get('title') or 'Work unavailable · 作品不可用'
    e = lambda value: html.escape(str(value), quote=True)
    head = '<base href="' + e(home) + '">\n<meta name="robots" content="' + ('index,follow' if valid else 'noindex') + '">'
    if valid:
        url = public_url(row['id'])
        description = title + ' · Spinning Top'
        head += '\n<link rel="canonical" href="' + e(url) + '">'
        fields = {'og:type': 'website', 'og:site_name': 'Spinning Top', 'og:title': title,
                  'og:description': description, 'og:url': url, 'og:image': image_url,
                  'og:image:width': '1200', 'og:image:height': '630', 'og:image:type': 'image/png',
                  'og:image:alt': description, 'twitter:card': 'summary_large_image',
                  'twitter:title': title, 'twitter:description': description, 'twitter:image': image_url,
                  'twitter:image:alt': description}
        for key, value in fields.items():
            if value:
                attr = 'name' if key.startswith('twitter:') else 'property'
                head += f'\n<meta {attr}="{key}" content="{e(value)}">'
    else:
        row.update(unavailable=True, title=title, intro_en='This work is unavailable. Return to today or explore explicitly. / 作品已移除或链接无效，请主动返回今日或自由探索。')
    row.update(mode='shared', date=None, detail_status='ready')
    encoded = json.dumps(row, ensure_ascii=False).replace('<', '\\u003c').replace('&', '\\u0026')
    head += '\n<script type="application/json" id="sharedWork">' + encoded + '</script>'
    result = template.replace('<!-- SHARE_HEAD -->', head).replace('<title>Spinning Top</title>', '<title>' + e(title) + ' · Spinning Top</title>')
    result = result.replace('>即将开场</h2>', '>' + e(title) + '</h2>')
    result = result.replace('>请稍候。</p>', '>' + e(row.get('intro_zh') or row.get('intro_en') or '') + '</p>')
    result = result.replace('id="artwork" alt=', 'id="artwork" src="' + e(row.get('artwork_url') or ('./static/artwork/base.svg' if static else '/artwork/base.svg')) + '" alt=')
    return result
