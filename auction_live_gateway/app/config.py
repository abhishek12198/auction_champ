# -*- coding: utf-8 -*-
"""AuctionChamp Phase 2B Redis read gateway configuration.

No Odoo. No PostgreSQL. Redis URL from env (defaults match Phase 2A).
"""
import os
import re

REDIS_URL = os.environ.get('AUCTION_REDIS_URL') or os.environ.get(
    'REDIS_URL', 'redis://127.0.0.1:6379/1'
)
HOST = os.environ.get('AUCTION_GATEWAY_HOST', '127.0.0.1')
PORT = int(os.environ.get('AUCTION_GATEWAY_PORT', '8090'))
CONNECT_TIMEOUT = float(os.environ.get('AUCTION_REDIS_CONNECT_TIMEOUT', '0.05'))
SOCKET_TIMEOUT = float(os.environ.get('AUCTION_REDIS_SOCKET_TIMEOUT', '0.1'))
SSE_HEARTBEAT_SECONDS = float(os.environ.get('AUCTION_SSE_HEARTBEAT_SECONDS', '15'))

# Conservative path segments: Odoo db names / slugs
DB_RE = re.compile(r'^[A-Za-z0-9_][A-Za-z0-9_.-]{0,62}$')
SLUG_RE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_-]{0,120}$')
MAX_PATH_LEN = 256


def valid_db(db: str) -> bool:
    return bool(db) and len(db) <= 64 and bool(DB_RE.match(db))


def valid_slug(slug: str) -> bool:
    return bool(slug) and len(slug) <= 128 and bool(SLUG_RE.match(slug))
