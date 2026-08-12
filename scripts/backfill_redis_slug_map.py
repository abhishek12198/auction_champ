#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Backfill Redis slug→tid maps + live-board meta via redis-cli (older Redis OK).

Prefer Odoo for slug map:
  env['auction.tournament'].action_backfill_redis_slug_map()

Meta (live_board_active / code_protected) is normally written on every
snapshot MULTI/EXEC. This script heals existing tournaments whose meta was
written before Phase 2B gateway fields existed.

Usage:
  python3 scripts/backfill_redis_slug_map.py --db main_db_1
"""
import argparse
import subprocess
import sys


def redis_cli(redis_db, *args):
    cmd = ['redis-cli', '-n', str(redis_db)] + list(args)
    return subprocess.check_output(cmd, text=True).strip()


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--db', required=True)
    p.add_argument('--redis-db', type=int, default=1)
    args = p.parse_args()
    rows = subprocess.check_output([
        'psql', '-d', args.db, '-tAc',
        "SELECT id, COALESCE(slug,''), "
        "COALESCE(live_board_active,false), "
        "COALESCE(live_board_code_protected,false), "
        "COALESCE(live_snapshot_seq,0) "
        "FROM auction_tournament WHERE slug IS NOT NULL AND slug <> ''",
    ], text=True)
    n_slug = 0
    n_meta = 0
    for line in rows.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split('|')
        if len(parts) < 5:
            continue
        tid, slug, active, protected, seq = parts[:5]
        tid = int(tid)
        slug_key = 'ac:%s:slug:%s:tid' % (args.db, slug)
        redis_cli(args.redis_db, 'SET', slug_key, str(tid))
        print(slug_key, '→', tid)
        n_slug += 1

        meta_key = 'ac:%s:t:%s:meta' % (args.db, tid)
        # Only heal gateway protection fields; do not invent snapshot bodies.
        redis_cli(
            args.redis_db, 'HSET', meta_key,
            'live_board_active', '1' if active in ('t', 'true', '1') else '0',
            'code_protected', '1' if protected in ('t', 'true', '1') else '0',
            'slug', slug,
            'seq', str(int(seq or 0)),
        )
        print('  meta', meta_key, 'active=', active, 'protected=', protected)
        n_meta += 1
    print('wrote', n_slug, 'slug mappings and', n_meta, 'meta hashes')
    return 0


if __name__ == '__main__':
    sys.exit(main())
