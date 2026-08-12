#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Phase 2B paced load test — N concurrent clients with real poll intervals.

--viewers 100 means 100 concurrent clients (NOT viewers//4 threads).

Examples:
  # Against Odoo directly (Phase 2A path)
  python3 scripts/load_test_live_polls.py --run --viewers 100 \\
    --base http://127.0.0.1:8069 --db main_db_1 --slug jas-cricket-league

  # Against gateway directly (Phase 2B Redis HIT path)
  python3 scripts/load_test_live_polls.py --run --viewers 100 \\
    --base http://127.0.0.1:8090 --db main_db_1 --slug jas-cricket-league

Requires: httpx (pip install httpx)
Do not claim a supported viewer count from localhost alone.
"""
from __future__ import print_function

import argparse
import asyncio
import json
import statistics
import sys
import time

try:
    import httpx
except ImportError:
    print('Install httpx: pip install httpx', file=sys.stderr)
    sys.exit(2)

VIEWER_STEPS = (100, 250, 500, 1000, 2000)


def urls(base, db, slug):
    base = base.rstrip('/')
    return {
        'lb': '%s/%s/%s/auction/live-board/data' % (base, db, slug),
        'pj': '%s/%s/auction/projector/%s/data' % (base, db, slug),
        'bal': '%s/%s/%s/auction/show/team/balance/json' % (base, db, slug),
    }


def percentile(values, p):
    if not values:
        return 0.0
    s = sorted(values)
    k = (len(s) - 1) * (p / 100.0)
    f = int(k)
    c = min(f + 1, len(s) - 1)
    if f == c:
        return s[f]
    return s[f] + (s[c] - s[f]) * (k - f)


async def client_loop(name, client, url, interval, duration, jsonrpc, results):
    """One paced viewer: poll every `interval` seconds for `duration`."""
    end = time.monotonic() + duration
    body = None
    headers = {'Accept': 'application/json'}
    if jsonrpc:
        body = json.dumps({
            'jsonrpc': '2.0', 'method': 'call', 'params': {}, 'id': 1,
        })
        headers['Content-Type'] = 'application/json'
    while time.monotonic() < end:
        t0 = time.monotonic()
        err = None
        status = 0
        try:
            if jsonrpc:
                resp = await client.post(url, content=body, headers=headers)
            else:
                resp = await client.get(url, headers=headers)
            status = resp.status_code
            await resp.aread()
        except Exception as exc:
            err = str(exc)
        ms = (time.monotonic() - t0) * 1000.0
        results.append((status, ms, err))
        # Pace: sleep remaining interval (burst uses short interval)
        elapsed = time.monotonic() - t0
        wait = interval - elapsed
        if wait > 0 and time.monotonic() + wait < end:
            await asyncio.sleep(wait)


async def run_wave(name, url, viewers, duration, interval, jsonrpc=False):
    print('  %s: %s concurrent clients, interval=%.2fs, duration=%.0fs' % (
        name, viewers, interval, duration,
    ))
    results = []
    limits = httpx.Limits(max_connections=max(64, viewers + 16),
                          max_keepalive_connections=max(32, viewers))
    timeout = httpx.Timeout(10.0, connect=2.0)
    t_start = time.monotonic()
    async with httpx.AsyncClient(limits=limits, timeout=timeout, http2=False) as client:
        tasks = [
            asyncio.create_task(client_loop(
                name, client, url, interval, duration, jsonrpc, results,
            ))
            for _ in range(viewers)
        ]
        await asyncio.gather(*tasks)
    elapsed = time.monotonic() - t_start
    lat = [ms for _s, ms, _e in results]
    errors = sum(1 for s, _ms, e in results if e or s >= 400 or s == 0)
    ok = len(results) - errors
    rps = (ok / elapsed) if elapsed else 0
    print('    elapsed=%.1fs requests=%s achieved=%.1f rps errors=%s/%s' % (
        elapsed, len(results), rps, errors, len(results),
    ))
    print('    P50=%.1fms P95=%.1fms P99=%.1fms' % (
        percentile(lat, 50), percentile(lat, 95), percentile(lat, 99),
    ))
    return {
        'name': name,
        'viewers': viewers,
        'interval': interval,
        'rps_achieved': rps,
        'p50': percentile(lat, 50),
        'p95': percentile(lat, 95),
        'p99': percentile(lat, 99),
        'errors': errors,
        'n': len(results),
    }


def print_plan(base, db, slug):
    u = urls(base, db, slug)
    print('Phase 2B paced live-poll load test')
    print('==================================')
    print('Base:', base)
    print('Live Board :', u['lb'], ' every 2s')
    print('Projector  :', u['pj'], ' idle 2s / burst 400ms x 6s')
    print('Bid Summary:', u['bal'], ' every 8s')
    print()
    print('--viewers N = N concurrent paced clients (keep-alive).')
    print('Do not publish a supported viewer count until VPS testing.')


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--base', default='http://127.0.0.1:8069')
    p.add_argument('--db', default='DB')
    p.add_argument('--slug', default='SLUG')
    p.add_argument('--viewers', type=int, default=0)
    p.add_argument('--duration', type=float, default=10.0)
    p.add_argument('--run', action='store_true')
    p.add_argument('--burst', action='store_true')
    p.add_argument('--only', choices=('lb', 'pj', 'bal', 'all'), default='all')
    args = p.parse_args(argv)
    print_plan(args.base, args.db, args.slug)
    if not args.run:
        print('\nRe-run with --run to execute.')
        return 0
    u = urls(args.base, args.db, args.slug)
    steps = (args.viewers,) if args.viewers else VIEWER_STEPS
    results = []

    async def _all():
        out = []
        for v in steps:
            print('\n=== %s concurrent clients ===' % v)
            if args.only in ('all', 'lb'):
                out.append(await run_wave(
                    'live-board', u['lb'], v, args.duration, 2.0,
                ))
            if args.only in ('all', 'pj'):
                out.append(await run_wave(
                    'projector-idle', u['pj'], v, args.duration, 2.0, jsonrpc=True,
                ))
                if args.burst:
                    out.append(await run_wave(
                        'projector-burst', u['pj'], v,
                        min(6.0, args.duration), 0.4, jsonrpc=True,
                    ))
            if args.only in ('all', 'bal'):
                out.append(await run_wave(
                    'bid-summary', u['bal'], v, args.duration, 8.0,
                ))
        return out

    results = asyncio.run(_all())
    print('\nJSON summary:')
    print(json.dumps(results, indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main())
