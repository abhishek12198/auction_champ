# -*- coding: utf-8 -*-
"""Country calling codes shared with the player registration form."""
import json
import logging
import re
from urllib.request import Request, urlopen

_logger = logging.getLogger(__name__)

# code, iso, flag, name, min digits, max digits, placeholder
SIGNUP_PHONE_COUNTRIES = (
    ('+91', 'IN', '🇮🇳', 'India', 10, 10, '98765 43210'),
    ('+92', 'PK', '🇵🇰', 'Pakistan', 10, 10, '300 1234567'),
    ('+94', 'LK', '🇱🇰', 'Sri Lanka', 9, 9, '71 234 5678'),
    ('+880', 'BD', '🇧🇩', 'Bangladesh', 10, 10, '1712 345678'),
    ('+971', 'AE', '🇦🇪', 'United Arab Emirates', 9, 9, '50 123 4567'),
    ('+966', 'SA', '🇸🇦', 'Saudi Arabia', 9, 9, '50 123 4567'),
    ('+974', 'QA', '🇶🇦', 'Qatar', 8, 8, '3312 3456'),
    ('+968', 'OM', '🇴🇲', 'Oman', 8, 8, '9123 4567'),
    ('+965', 'KW', '🇰🇼', 'Kuwait', 8, 8, '5001 2345'),
    ('+973', 'BH', '🇧🇭', 'Bahrain', 8, 8, '3600 1234'),
    ('+1', 'US', '🇺🇸', 'United States', 10, 10, '202 555 0123'),
    ('+44', 'GB', '🇬🇧', 'United Kingdom', 10, 10, '7400 123456'),
    ('+61', 'AU', '🇦🇺', 'Australia', 9, 9, '412 345 678'),
)

_BY_CODE = {row[0]: row for row in SIGNUP_PHONE_COUNTRIES}
_BY_ISO = {row[1]: row[0] for row in SIGNUP_PHONE_COUNTRIES}
_BY_ISO['CA'] = '+1'
_CODES_LONGEST_FIRST = tuple(sorted(_BY_CODE, key=len, reverse=True))
DEFAULT_SIGNUP_CODE = '+91'


def phone_spec_for_iso(iso):
    """Calling-code rules for a detected country. Unknown countries stay on +91."""
    code = _BY_ISO.get((iso or '').upper()) or DEFAULT_SIGNUP_CODE
    spec = _BY_CODE[code]
    return {
        'code': spec[0],
        'label': '%s %s' % (spec[2], spec[0]),
        'min': spec[4],
        'max': spec[5],
        'placeholder': spec[6],
    }


def signup_phone_rows(selected_code=None):
    selected = selected_code if selected_code in _BY_CODE else DEFAULT_SIGNUP_CODE
    rows = []
    for code, _iso, flag, _name, min_len, max_len, placeholder in SIGNUP_PHONE_COUNTRIES:
        rows.append({
            'code': code,
            'label': '%s %s' % (flag, code),
            'min': min_len,
            'max': max_len,
            'placeholder': placeholder,
            'selected': code == selected,
        })
    return rows


def compose_signup_phone(country_code, national):
    """Return +code plus national digits, or raise ValueError."""
    code = (country_code or '').strip()
    spec = _BY_CODE.get(code)
    digits = re.sub(r'\D', '', national or '')
    if not spec:
        raise ValueError('Select a country code.')
    _code, _iso, _flag, name, min_len, max_len, _placeholder = spec
    if not digits:
        raise ValueError('Please enter your contact number.')
    if min_len == max_len and len(digits) != min_len:
        raise ValueError('Enter %s digits for %s (without the country code).' % (min_len, name))
    if not (min_len <= len(digits) <= max_len):
        raise ValueError(
            'Enter %s to %s digits for %s (without the country code).' % (min_len, max_len, name)
        )
    return '%s%s' % (code, digits)


def split_signup_phone(phone):
    raw = re.sub(r'[\s\-()]', '', (phone or '').strip())
    if raw.startswith('00'):
        raw = '+' + raw[2:]
    if raw and not raw.startswith('+') and raw.isdigit():
        raw = '+' + raw
    for code in _CODES_LONGEST_FIRST:
        if raw.startswith(code):
            return code, re.sub(r'\D', '', raw[len(code):])
    return DEFAULT_SIGNUP_CODE, re.sub(r'\D', '', raw)


def _ip_is_private(ip):
    if not ip:
        return True
    if ip in ('127.0.0.1', '::1', 'localhost'):
        return True
    if ip.startswith('10.') or ip.startswith('192.168.') or ip.startswith('127.'):
        return True
    if ip.startswith('172.'):
        try:
            second = int(ip.split('.')[1])
        except (IndexError, ValueError):
            return False
        return 16 <= second <= 31
    return False


def _fetch_json(url, timeout=1.5):
    try:
        req = Request(url, headers={'User-Agent': 'AuctionChampSignup/1.0', 'Accept': 'application/json'})
        with urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode('utf-8', errors='replace')
        return json.loads(raw or '{}')
    except Exception:
        _logger.debug('signup geo lookup failed for %s', url, exc_info=True)
        return {}


def detect_signup_country_code(ip):
    """Calling code from the visitor IP. Unknown or private addresses stay on +91."""
    if _ip_is_private(ip):
        return DEFAULT_SIGNUP_CODE
    data = _fetch_json(
        'http://ip-api.com/json/%s?fields=status,countryCode' % ip,
    )
    if data.get('status') == 'success':
        code = _BY_ISO.get((data.get('countryCode') or '').upper())
        if code:
            return code
    data = _fetch_json('https://ipwho.is/%s' % ip)
    if data.get('success'):
        code = _BY_ISO.get((data.get('country_code') or '').upper())
        if code:
            return code
    return DEFAULT_SIGNUP_CODE
