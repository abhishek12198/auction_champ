# -*- coding: utf-8 -*-
"""Resolve the visitor country used for regional SaaS prices.

Order: an explicit choice, then the remembered cookie, then Cloudflare,
then Odoo GeoIP, then a cached IP lookup. Private addresses and a
"standard price" choice return no country, which keeps the plan price.
"""
import ipaddress
import logging
import time
from urllib.parse import quote

from .phone_countries import _fetch_json, _ip_is_private

_logger = logging.getLogger(__name__)

BILLING_COOKIE = 'ac_billing_country'
DEFAULT_TOKEN = '__default__'
AUTO_TOKEN = '__auto__'
COOKIE_MAX_AGE = 90 * 24 * 3600
_ISO_CACHE = {}
_ISO_TTL = 6 * 3600


def _iso(code):
    code = (code or '').strip().upper()
    return code if len(code) == 2 and code.isalpha() else ''


def client_ip(httprequest):
    forwarded = (httprequest.headers.get('X-Forwarded-For') or '').split(',')[0].strip()
    raw = forwarded or (httprequest.remote_addr or '')
    try:
        return str(ipaddress.ip_address(raw))
    except ValueError:
        return ''


def detect_visitor_iso(ip):
    """ISO country from a public IP. Empty when unknown. Cached per worker."""
    ip = (ip or '').strip()
    if not ip or _ip_is_private(ip):
        return ''
    now = time.monotonic()
    hit = _ISO_CACHE.get(ip)
    if hit and now - hit[0] < _ISO_TTL:
        return hit[1]
    iso = ''
    safe_ip = quote(ip, safe='')
    data = _fetch_json(
        'http://ip-api.com/json/%s?fields=status,countryCode' % safe_ip,
    )
    if data.get('status') == 'success':
        iso = _iso(data.get('countryCode'))
    if not iso:
        data = _fetch_json('https://ipwho.is/%s' % safe_ip)
        if data.get('success'):
            iso = _iso(data.get('country_code'))
    if len(_ISO_CACHE) > 4000:
        _ISO_CACHE.clear()
    _ISO_CACHE[ip] = (now, iso)
    return iso


def _detected_iso(httprequest, geoip_code=None):
    for header in ('CF-IPCountry', 'CloudFront-Viewer-Country'):
        code = _iso(httprequest.headers.get(header))
        if code and code not in ('XX', 'T1'):
            return code
    code = _iso(geoip_code)
    if code:
        return code
    return detect_visitor_iso(client_ip(httprequest))


def resolve_country_iso(httprequest, explicit_code=None, geoip_code=None):
    """Return an ISO code, or '' when the standard plan price should be used."""
    explicit = (explicit_code or '').strip()
    if explicit == DEFAULT_TOKEN:
        return ''
    if explicit == AUTO_TOKEN:
        return _detected_iso(httprequest, geoip_code)
    code = _iso(explicit)
    if code:
        return code
    cookie = (httprequest.cookies.get(BILLING_COOKIE) or '').strip()
    if cookie == DEFAULT_TOKEN:
        return ''
    code = _iso(cookie)
    if code:
        return code
    return _detected_iso(httprequest, geoip_code)


def apply_country_cookie(response, token):
    """Remember an ISO code or the standard-price token. Return the response."""
    token = (token or '').strip()
    if token == AUTO_TOKEN:
        response.delete_cookie(BILLING_COOKIE, path='/')
        return response
    if token == DEFAULT_TOKEN:
        value = DEFAULT_TOKEN
    else:
        value = _iso(token)
        if not value:
            response.delete_cookie(BILLING_COOKIE, path='/')
            return response
    response.set_cookie(
        BILLING_COOKIE,
        value,
        max_age=COOKIE_MAX_AGE,
        path='/',
        samesite='Lax',
    )
    return response
