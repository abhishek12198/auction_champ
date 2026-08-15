#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Phase 3 SSE load probe — N concurrent EventSource-like streams.

Measures connect success, first snapshot latency, and updates received.
Does NOT claim a supported viewer count from localhost alone.

Examples:
  python3 scripts/load_test_sse.py --run --viewers 50 --duration 20 \\
    --base http://127.0.0.1:8090 --db main_db_1 --slug jas-cricket-league \\
    --kind lb

Requires: httpx
"""
from __future__ import print_function

import argparse
import asyncio
import statistics
import sys
import time

try:
    import httpx
except ImportError:
    print('Install httpx: pip install httpx', file=sys.stderr)
    sys.exit(2)


def event_url(base, db, slug, kind):
    base = base.rstrip('/')
    if kind == 'lb':
        return '%s/%s/%s/auction/live-board/events' % (base, db, slug)
    if kind == 'pj':
        return '%s/%s/auction/projector/%s/events' % (base, db, slug)
    if kind == 'bal':
        return '%s/%s/%s/auction/show/team/balance/events' % (base, db, slug)
    raise ValueError('kind must be lb|pj|bal')


def percentile(values, p):
    if not values:
        return 0.0
    s = sorted(values)
    k = (len(s) - 1) * (p / 100.0)
    f = int(k)
    c = min(f + 1, len(s) - 1)
    if f == c:
        return float(s[f])
    return float(s[f] + (s[c] - s[f]) * (k - f))


async def one_client(client, url, duration, results):
    t0 = time.monotonic()
    status = 0
    first_ms = None
    events = 0
    err = None
    try:
        async with client.stream(
            'GET', url, headers={'Accept': 'text/event-stream'}, timeout=None
        ) as resp:
            status = resp.status_code
            if status != 200:
                err = 'HTTP %s' % status
                results.append({
                    'ok': False, 'status': status, 'first_ms': None,
                    'events': 0, 'err': err,
                })
                return
            end = time.monotonic() + duration
            buf = ''
            async for chunk in resp.aiter_text():
                if time.monotonic() >= end:
                    break
                buf += chunk
                while '\n\n' in buf:
                    block, buf = buf.split('\n\n', 1)
                    if not block.strip() or block.startswith(':'):
                        continue
                    events += 1
                    if first_ms is None:
                        first_ms = (time.monotonic() - t0) * 1000.0
                if events >= 1 and time.monotonic() >= end:
                    break
    except Exception as exc:
        err = str(exc)
    results.append({
        'ok': status == 200 and first_ms is not None,
        'status': status,
        'first_ms': first_ms,
        'events': events,
        'err': err,
    })


async def run(args):
    url = event_url(args.base, args.db, args.slug, args.kind)
    results = []
    limits = httpx.Limits(max_connections=args.viewers + 10, max_keepalive_connections=args.viewers)
    async with httpx.AsyncClient(limits=limits) as client:
        tasks = [
            asyncio.create_task(one_client(client, url, args.duration, results))
            for _ in range(args.viewers)
        ]
        await asyncio.gather(*tasks)

    ok = [r for r in results if r['ok']]
    firsts = [r['first_ms'] for r in ok if r['first_ms'] is not None]
    events = [r['events'] for r in results]
    print('SSE load probe')
    print('  url=%s' % url)
    print('  viewers=%s duration=%ss' % (args.viewers, args.duration))
    print('  ok=%s/%s' % (len(ok), len(results)))
    if firsts:
        print('  first_snapshot_ms: p50=%.1f p95=%.1f max=%.1f' % (
            percentile(firsts, 50), percentile(firsts, 95), max(firsts),
        ))
    print('  events_total=%s mean_per_client=%.2f' % (
        sum(events), statistics.mean(events) if events else 0.0,
    ))
    fails = [r for r in results if not r['ok']]
    if fails[:5]:
        print('  sample_errors:')
        for r in fails[:5]:
            print('    status=%s err=%s' % (r['status'], r['err']))


def main():
    ap = argparse.ArgumentParser(description='Phase 3 SSE load probe')
    ap.add_argument('--run', action='store_true', required=True)
    ap.add_argument('--viewers', type=int, default=50)
    ap.add_argument('--duration', type=float, default=15.0)
    ap.add_argument('--base', default='http://127.0.0.1:8090')
    ap.add_argument('--db', required=True)
    ap.add_argument('--slug', required=True)
    ap.add_argument('--kind', choices=('lb', 'pj', 'bal'), default='lb')
    args = ap.parse_args()
    asyncio.run(run(args))


if __name__ == '__main__':
    main()
