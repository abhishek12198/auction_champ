# -*- coding: utf-8 -*-
##############################################################################
#
#  AuctionChamp - Professional Sports Auction Management Platform
#
#  Dynamic Open Graph / Twitter Card metadata for public tournament pages.
#  Crawler-safe: values are rendered into the initial QWeb HTML (no JS).
#
##############################################################################

import base64
import hashlib
import logging
from io import BytesIO

_logger = logging.getLogger(__name__)

OG_WIDTH = 1200
OG_HEIGHT = 630
SITE_NAME = 'Auction Champ'
BRAND_TITLE = 'Auction Champ'
BRAND_DESCRIPTION = (
    'Professional cricket tournament management and auction platform.'
)

# page_key -> (title suffix, short description for WhatsApp / OG)
PAGE_COPY = {
    'player_register': (
        'Player Registration',
        'Register to join this tournament.',
    ),
    'live_board': (
        'Live',
        'Watch the live auction.',
    ),
    'live_board_offline': (
        'Live',
        'Live auction board.',
    ),
    'live_board_unlock': (
        'Live',
        'Watch the live auction.',
    ),
    'welcome': (
        'Auction',
        'Auction welcome page.',
    ),
    'thank_you': (
        'Auction Complete',
        'Auction has concluded.',
    ),
    'bid_summary': (
        'Bid Summary',
        'Team purses and bid summary.',
    ),
    'remaining_players': (
        'Players Left',
        'Players still available in the auction.',
    ),
    'squad': (
        'Squad',
        'Team squad list.',
    ),
    'player_card': (
        'Player Card',
        'Player card.',
    ),
    'display_auction': (
        'Live',
        'Watch the live auction.',
    ),
    'tournament_register': (
        'Register Your Tournament',
        'Create and run your cricket auction on Auction Champ.',
    ),
    'website_home': (
        '',
        BRAND_DESCRIPTION,
    ),
    'website_privacy': (
        'Privacy Policy',
        'Privacy Policy for Auction Champ.',
    ),
    'website_terms': (
        'Terms and Conditions',
        'Terms and Conditions for Auction Champ.',
    ),
    'website_manual': (
        'User Manual',
        'User manual for Auction Champ tournament and auction tools.',
    ),
    'home': (
        '',
        BRAND_DESCRIPTION,
    ),
}

_OG_CACHE = {}
_OG_CACHE_MAX = 64


def public_base_url():
    """Absolute public origin (https://host) for OG/canonical tags."""
    from odoo.http import request
    configured = ''
    try:
        configured = (
            request.env['ir.config_parameter'].sudo().get_param('web.base.url') or ''
        ).rstrip('/')
    except Exception:
        configured = ''
    try:
        req = request.httprequest
        host = (req.headers.get('X-Forwarded-Host') or req.host or '').split(',')[0].strip()
        proto = (req.headers.get('X-Forwarded-Proto') or req.scheme or 'http').split(',')[0].strip()
        if host and not host.startswith('localhost') and not host.startswith('127.0.0.1'):
            if proto == 'http' and configured.startswith('https://'):
                proto = 'https'
            return '%s://%s' % (proto, host)
    except Exception:
        pass
    return configured or 'https://www.auctionchamp.live'


def canonical_url():
    base = public_base_url()
    try:
        from odoo.http import request
        path = request.httprequest.path or '/'
        if not path.startswith('/'):
            path = '/' + path
        return base + path
    except Exception:
        return base


def _safe_text(value, fallback=''):
    if value is None:
        return fallback
    if isinstance(value, bytes):
        try:
            value = value.decode('utf-8')
        except Exception:
            return fallback
    text = ' '.join(str(value).split())
    if text in ('False', 'None', 'undefined', '[object Object]'):
        return fallback
    return text


def _clip(text, limit=200):
    text = _safe_text(text)
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + '…'


def tournament_season(tournament):
    """Year/season label from tournament dates, never a hard-coded name."""
    if not tournament:
        return ''
    try:
        label = tournament.format_tournament_dates(fmt='%Y')
        if label:
            years = sorted({part.strip() for part in label.replace('–', '-').split('-') if part.strip().isdigit()})
            if len(years) == 1:
                return years[0]
            if len(years) >= 2:
                return '%s–%s' % (years[0], years[-1])
    except Exception:
        pass
    return ''


TITLE_SEP = ' - '


def _page_copy(page_key, name, season):
    suffix, description = PAGE_COPY.get(page_key) or PAGE_COPY['home']
    name = name or SITE_NAME
    if page_key in ('website_home', 'home', 'tournament_register') and not tournament_bound(page_key):
        title = ('%s%s%s' % (SITE_NAME, TITLE_SEP, suffix)) if suffix else SITE_NAME
        if page_key == 'website_home':
            title = 'Auction Champ - Cricket Auction & Tournament Management'
        return title, description
    if suffix:
        title = '%s%s%s' % (name, TITLE_SEP, suffix)
    else:
        title = name
    return title, description


def tournament_bound(page_key):
    return page_key not in (
        'website_home', 'website_privacy', 'website_terms',
        'website_manual', 'tournament_register', 'home',
    )


def image_version(tournament):
    if tournament and tournament.write_date:
        try:
            return str(int(tournament.write_date.timestamp()))
        except Exception:
            return str(tournament.write_date).replace(' ', '').replace(':', '').replace('-', '')[:14]
    return '1'


def og_image_url(tournament, db_name=None):
    base = public_base_url()
    if tournament and tournament.id and tournament.slug:
        db = db_name or (tournament.env.cr.dbname if tournament.env else '')
        if db and tournament.slug:
            return '%s/%s/%s/auction/social-preview.jpg?v=%s' % (
                base, db, tournament.slug, image_version(tournament),
            )
    return '%s/auction/social-preview.jpg?v=1' % base


def build_preview(tournament, page_key='home', db_name=None):
    """Return a dict of SEO/OG values for QWeb. Never includes private data."""
    page_key = _safe_text(page_key, 'home') or 'home'
    name = ''
    rec = tournament
    if rec and getattr(rec, 'ids', None):
        rec = rec[:1]
        name = _safe_text(rec.name)
        db_name = db_name or rec.env.cr.dbname
    else:
        rec = None

    title, description = _page_copy(page_key, name or SITE_NAME, '')

    url = canonical_url()
    image = og_image_url(rec, db_name=db_name)
    return {
        'title': title,
        'description': _clip(description, 200),
        'og_type': 'website',
        'og_title': title,
        'og_description': _clip(description, 200),
        'og_image': image,
        'og_image_width': str(OG_WIDTH),
        'og_image_height': str(OG_HEIGHT),
        'og_url': url,
        'og_site_name': SITE_NAME,
        'twitter_card': 'summary_large_image',
        'twitter_title': title,
        'twitter_description': _clip(description, 200),
        'twitter_image': image,
        'canonical': url,
        'robots': 'index,follow',
    }


def _decode_binary(binary):
    if not binary:
        return None
    raw = binary
    if isinstance(raw, str):
        try:
            raw = base64.b64decode(raw)
        except Exception:
            return None
    elif isinstance(raw, bytes):
        # Odoo Binary may already be base64 bytes
        head = raw[:8]
        if head[:3] != b'\xff\xd8\xff' and head[:8] != b'\x89PNG\r\n\x1a\n':
            try:
                raw = base64.b64decode(raw)
            except Exception:
                pass
    return raw if raw else None


def _open_image(binary):
    from PIL import Image
    raw = _decode_binary(binary)
    if not raw:
        return None
    try:
        im = Image.open(BytesIO(raw))
        im.load()
        return im
    except Exception:
        return None


def _cover_crop(im, width, height):
    from PIL import Image
    im = im.convert('RGB')
    src_w, src_h = im.size
    if src_w < 1 or src_h < 1:
        return Image.new('RGB', (width, height), (11, 29, 54))
    scale = max(width / float(src_w), height / float(src_h))
    nw, nh = max(1, int(round(src_w * scale))), max(1, int(round(src_h * scale)))
    im = im.resize((nw, nh), Image.LANCZOS)
    left = max(0, (nw - width) // 2)
    top = max(0, (nh - height) // 2)
    return im.crop((left, top, left + width, top + height))


def _load_brand_icon():
    from PIL import Image
    from odoo.modules.module import get_resource_path
    for parts in (
        ('auction_module', 'static', 'description', 'favicon.png'),
        ('auction_module', 'static', 'description', 'icon.png'),
        ('auction_module', 'static', 'src', 'img', 'icon.png'),
    ):
        path = get_resource_path(*parts)
        if not path:
            continue
        try:
            return Image.open(path)
        except Exception:
            continue
    return None


def _font(size):
    from PIL import ImageFont
    from odoo.modules.module import get_resource_path
    candidates = [
        get_resource_path('web', 'static', 'fonts', 'lato', 'Lato-Bold.ttf'),
        get_resource_path('web', 'static', 'fonts', 'lato/Lato-Bold.ttf'),
        '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
        '/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf',
    ]
    for path in candidates:
        if not path:
            continue
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    return ImageFont.load_default()


def _wrap_text(draw, text, font, max_width):
    words = _safe_text(text).split()
    if not words:
        return []
    lines, current = [], words[0]
    for word in words[1:]:
        trial = current + ' ' + word
        try:
            w = draw.textlength(trial, font=font)
        except Exception:
            w = len(trial) * 12
        if w <= max_width:
            current = trial
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines[:3]


def _compose_logo_card(logo_im, title, subtitle):
    from PIL import Image, ImageDraw
    canvas = Image.new('RGB', (OG_WIDTH, OG_HEIGHT), (11, 29, 54))
    draw = ImageDraw.Draw(canvas)
    # Gold top bar
    draw.rectangle([0, 0, OG_WIDTH, 8], fill=(212, 160, 23))
    draw.rectangle([0, OG_HEIGHT - 8, OG_WIDTH, OG_HEIGHT], fill=(212, 160, 23))

    if logo_im:
        logo = logo_im.convert('RGBA')
        max_side = 280
        logo.thumbnail((max_side, max_side), Image.LANCZOS)
        lx = (OG_WIDTH - logo.width) // 2
        ly = 90
        if logo.mode == 'RGBA':
            canvas.paste(logo, (lx, ly), logo)
        else:
            canvas.paste(logo.convert('RGB'), (lx, ly))
        text_y = ly + logo.height + 36
    else:
        text_y = 220

    title_font = _font(48)
    sub_font = _font(26)
    lines = _wrap_text(draw, title or SITE_NAME, title_font, OG_WIDTH - 160)
    for line in lines:
        try:
            tw = draw.textlength(line, font=title_font)
        except Exception:
            tw = len(line) * 20
        draw.text(((OG_WIDTH - tw) / 2, text_y), line, font=title_font, fill=(255, 255, 255))
        text_y += 58
    if subtitle:
        try:
            sw = draw.textlength(subtitle, font=sub_font)
        except Exception:
            sw = 200
        draw.text(((OG_WIDTH - sw) / 2, text_y + 8), subtitle, font=sub_font, fill=(212, 160, 23))
    return canvas


def _compose_logo_only(logo_im):
    """Center tournament logo on brand background — no text overlay."""
    from PIL import Image
    canvas = Image.new('RGB', (OG_WIDTH, OG_HEIGHT), (11, 29, 54))
    if not logo_im:
        return canvas
    logo = logo_im.convert('RGBA')
    max_side = 420
    logo.thumbnail((max_side, max_side), Image.LANCZOS)
    lx = (OG_WIDTH - logo.width) // 2
    ly = (OG_HEIGHT - logo.height) // 2
    if logo.mode == 'RGBA':
        canvas.paste(logo, (lx, ly), logo)
    else:
        canvas.paste(logo.convert('RGB'), (lx, ly))
    return canvas


def compose_og_jpeg(tournament=None):
    """Return JPEG bytes (1200×630) for WhatsApp / Open Graph."""
    if tournament and tournament.id:
        # Optional dedicated share image, then poster, then logo.
        for field in ('social_share_image', 'poster_image', 'logo'):
            if getattr(tournament, field, False):
                im = _open_image(tournament[field])
                if im:
                    if field == 'logo':
                        return _jpeg_bytes(_compose_logo_only(im))
                    return _jpeg_bytes(_cover_crop(im, OG_WIDTH, OG_HEIGHT))
    icon = _load_brand_icon()
    return _jpeg_bytes(_compose_logo_card(icon, SITE_NAME, 'Auction & Tournament Platform'))


def _jpeg_bytes(im):
    from PIL import Image
    buf = BytesIO()
    im.convert('RGB').save(buf, format='JPEG', quality=86, optimize=True)
    return buf.getvalue()


def cached_og_jpeg(tournament=None):
    key = 'brand'
    if tournament and tournament.id:
        key = '%s:%s:%s' % (
            tournament.env.cr.dbname,
            tournament.id,
            image_version(tournament),
        )
    hit = _OG_CACHE.get(key)
    if hit:
        return hit
    data = compose_og_jpeg(tournament)
    if len(_OG_CACHE) >= _OG_CACHE_MAX:
        try:
            _OG_CACHE.pop(next(iter(_OG_CACHE)))
        except Exception:
            _OG_CACHE.clear()
    _OG_CACHE[key] = data
    return data


DEFAULT_FAVICON = '/auction_module/static/description/favicon.png'
# Odoo 15 stock web/static/img/favicon.ico (purple) — never use for public pages.
_ODOO_STOCK_FAVICON_MD5 = 'a342fe863a8e41dff2a55410c7f118c5'


def _company_favicon_bytes(env):
    try:
        company = env['res.company'].sudo().search([], limit=1)
        if company and company.favicon:
            return _decode_binary(company.favicon)
    except Exception:
        pass
    return None


def _is_odoo_stock_favicon(raw):
    if not raw:
        return True
    return hashlib.md5(raw).hexdigest() == _ODOO_STOCK_FAVICON_MD5


def brand_favicon_url(env, db_name=None):
    """Gavel-only favicon for tabs and WhatsApp link previews.

    Prefer the company favicon from Settings when it is a custom upload.
    Fall back to the square gavel mark (not the full wordmark ``icon.png``).
    """
    try:
        raw = _company_favicon_bytes(env)
        if raw and not _is_odoo_stock_favicon(raw):
            db = (db_name or getattr(env.cr, 'dbname', None) or '').strip().strip('/')
            company = env['res.company'].sudo().search([], limit=1)
            if company:
                path = 'auction/public/image/res.company/%d/favicon' % company.id
                return ('/%s/%s' % (db, path)) if db else ('/' + path)
    except Exception:
        _logger.exception('brand favicon url failed')
    return DEFAULT_FAVICON


def brand_favicon_absolute_url(env=None, db_name=None):
    """Absolute favicon URL for crawlers (WhatsApp, Telegram, etc.)."""
    return public_base_url().rstrip('/') + DEFAULT_FAVICON
