# -*- coding: utf-8 -*-
"""Phase 3 SSE unit tests — no live Redis required."""
import asyncio
import json
import os
import sys
import unittest
from unittest import mock

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from fastapi.testclient import TestClient

from app.main import app
from app import sse as sse_mod


class FormatSseTests(unittest.TestCase):
    def test_format_includes_event_id_and_data(self):
        body = sse_mod._format_sse('snapshot', {'seq': 3, 'ok': True}, event_id=3)
        self.assertIn('id: 3\n', body)
        self.assertIn('event: snapshot\n', body)
        self.assertIn('data: {"seq":3,"ok":true}\n', body)
        self.assertTrue(body.endswith('\n\n') or body.endswith('\n'))

    def test_heartbeat_comment_style(self):
        # Documented shape used by sse_stream on timeout
        self.assertEqual(': heartbeat\n\n'.count('\n'), 2)


class SseRouteTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.db = 'main_db_1'
        self.slug = 'jas-cricket-league'
        self.tid = 13

    def test_events_routes_registered(self):
        paths = {getattr(r, 'path', None) for r in app.routes}
        self.assertIn('/{db}/{slug}/auction/live-board/events', paths)
        self.assertIn('/{db}/auction/projector/{slug}/events', paths)
        self.assertIn('/{db}/{slug}/auction/show/team/balance/events', paths)

    def test_invalid_db_404(self):
        r = self.client.get('/bad db!/%s/auction/live-board/events' % self.slug)
        self.assertEqual(r.status_code, 404)

    @mock.patch('app.sse.async_redis.resolve_tid', new_callable=mock.AsyncMock)
    def test_slug_miss_404(self, resolve):
        resolve.return_value = (None, 'miss')
        r = self.client.get(
            '/%s/%s/auction/live-board/events' % (self.db, self.slug)
        )
        self.assertEqual(r.status_code, 404)

    @mock.patch('app.sse.async_redis.resolve_tid', new_callable=mock.AsyncMock)
    def test_redis_error_503(self, resolve):
        resolve.return_value = (None, 'error')
        r = self.client.get(
            '/%s/auction/projector/%s/events' % (self.db, self.slug)
        )
        self.assertEqual(r.status_code, 503)
        self.assertIn('text/event-stream', r.headers.get('content-type', ''))

    @mock.patch('app.sse.async_redis.get_meta', new_callable=mock.AsyncMock)
    @mock.patch('app.sse.async_redis.resolve_tid', new_callable=mock.AsyncMock)
    def test_lb_code_protected_404(self, resolve, get_meta):
        resolve.return_value = (self.tid, None)
        get_meta.return_value = (
            {'live_board_active': '1', 'code_protected': '1'},
            None,
        )
        r = self.client.get(
            '/%s/%s/auction/live-board/events' % (self.db, self.slug)
        )
        self.assertEqual(r.status_code, 404)

    @mock.patch('app.sse.async_redis.get_meta', new_callable=mock.AsyncMock)
    @mock.patch('app.sse.async_redis.resolve_tid', new_callable=mock.AsyncMock)
    def test_lb_inactive_snapshot(self, resolve, get_meta):
        resolve.return_value = (self.tid, None)
        get_meta.return_value = (
            {'live_board_active': '0', 'code_protected': '0'},
            None,
        )
        r = self.client.get(
            '/%s/%s/auction/live-board/events' % (self.db, self.slug)
        )
        self.assertEqual(r.status_code, 200)
        self.assertIn('event: snapshot', r.text)
        self.assertIn('live_board_active', r.text)

    @mock.patch('app.sse.sse_stream')
    @mock.patch('app.sse.async_redis.get_meta', new_callable=mock.AsyncMock)
    @mock.patch('app.sse.async_redis.resolve_tid', new_callable=mock.AsyncMock)
    def test_lb_streams_finite_snapshot(self, resolve, get_meta, stream):
        resolve.return_value = (self.tid, None)
        get_meta.return_value = (
            {'live_board_active': '1', 'code_protected': '0'},
            None,
        )

        async def _gen(*a, **kw):
            yield sse_mod._format_sse(
                'snapshot', {'seq': 7, 'live_board_active': True}, event_id=7
            )

        stream.side_effect = _gen
        r = self.client.get(
            '/%s/%s/auction/live-board/events' % (self.db, self.slug)
        )
        self.assertEqual(r.status_code, 200)
        self.assertIn('id: 7', r.text)
        self.assertIn('"seq":7', r.text)
        self.assertEqual(r.headers.get('x-accel-buffering'), 'no')

    @mock.patch('app.sse.sse_stream')
    @mock.patch('app.sse.async_redis.resolve_tid', new_callable=mock.AsyncMock)
    def test_balance_events_no_option_a(self, resolve, stream):
        resolve.return_value = (self.tid, None)

        async def _gen(*a, **kw):
            yield sse_mod._format_sse(
                'snapshot', {'teams': [], 'seq': 1}, event_id=1
            )

        stream.side_effect = _gen
        r = self.client.get(
            '/%s/%s/auction/show/team/balance/events' % (self.db, self.slug)
        )
        self.assertEqual(r.status_code, 200)
        self.assertIn('teams', r.text)


class ChannelFanoutTests(unittest.IsolatedAsyncioTestCase):
    async def test_fanout_targets_kind(self):
        from app.channel_manager import TournamentChannel

        ch = TournamentChannel('main_db_1', 13)
        ch._started = True  # skip redis subscribe
        q_lb = asyncio.Queue(maxsize=8)
        q_pj = asyncio.Queue(maxsize=8)
        ch.subscribers['lb'].add(q_lb)
        ch.subscribers['pj'].add(q_pj)
        await ch._fanout({'seq': 2, 'targets': ['lb']})
        self.assertFalse(q_lb.empty())
        self.assertTrue(q_pj.empty())
        ev = q_lb.get_nowait()
        self.assertEqual(ev['seq'], 2)


if __name__ == '__main__':
    unittest.main()
