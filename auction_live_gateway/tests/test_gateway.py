# -*- coding: utf-8 -*-
"""Gateway unit tests — no Odoo, optional fake Redis."""
import json
import sys
import os
import unittest
from unittest import mock

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from fastapi.testclient import TestClient

from app import redis_client
from app.main import app


class FakeRedis(object):
    def __init__(self):
        self.kv = {}
        self.hashes = {}
        self.fail = False
        self.slow = False

    def ping(self):
        if self.fail:
            raise ConnectionError('down')
        return True

    def get(self, key):
        if self.fail:
            raise ConnectionError('down')
        return self.kv.get(key)

    def set(self, key, value, **kw):
        self.kv[key] = str(value)
        return True

    def hgetall(self, key):
        if self.fail:
            raise ConnectionError('down')
        return dict(self.hashes.get(key) or {})

    def delete(self, *keys):
        for k in keys:
            self.kv.pop(k, None)
            self.hashes.pop(k, None)


class GatewayTests(unittest.TestCase):
    def setUp(self):
        self.fake = FakeRedis()
        redis_client.reset()
        self._orig = redis_client.get_client
        redis_client.get_client = lambda: self.fake
        self.client = TestClient(app)
        self.db = 'main_db_1'
        self.slug = 'jas-cricket-league'
        self.tid = 13
        self.fake.kv['ac:%s:slug:%s:tid' % (self.db, self.slug)] = str(self.tid)
        self.fake.hashes['ac:%s:t:%s:meta' % (self.db, self.tid)] = {
            'live_board_active': '1',
            'code_protected': '0',
            'seq': '0',
        }
        self.lb = {'tournament': {'name': 'T'}, 'live_board_active': True, 'seq': 0}
        self.pj = {'player': {'id': 1, 'name': 'P'}, 'seq': 0}
        self.bal = {'teams': [{'id': 1, 'max_call': 100}], 'seq': 0}
        self.fake.kv['ac:%s:t:%s:lb' % (self.db, self.tid)] = json.dumps(self.lb)
        self.fake.kv['ac:%s:t:%s:pj' % (self.db, self.tid)] = json.dumps(self.pj)
        self.fake.kv['ac:%s:t:%s:bal' % (self.db, self.tid)] = json.dumps(self.bal)
        self.fake.kv['ac:%s:t:%s:seq' % (self.db, self.tid)] = '0'

    def tearDown(self):
        redis_client.get_client = self._orig
        redis_client.reset()

    def test_health(self):
        r = self.client.get('/health')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.text, 'ok')

    def test_ready_ok(self):
        r = self.client.get('/ready')
        self.assertEqual(r.status_code, 200)

    def test_live_hit(self):
        r = self.client.get('/%s/%s/auction/live-board/data' % (self.db, self.slug))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['seq'], 0)
        self.assertEqual(r.headers.get('cache-control'), 'no-store')

    def test_seq_zero_is_hit(self):
        r = self.client.get('/%s/%s/auction/live-board/data' % (self.db, self.slug))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['seq'], 0)

    def test_balance_hit(self):
        r = self.client.get(
            '/%s/%s/auction/show/team/balance/json' % (self.db, self.slug)
        )
        self.assertEqual(r.status_code, 200)
        self.assertIn('teams', r.json())

    def test_projector_post_jsonrpc_wrap(self):
        r = self.client.post(
            '/%s/auction/projector/%s/data' % (self.db, self.slug),
            json={'jsonrpc': '2.0', 'method': 'call', 'params': {}, 'id': 1},
        )
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body['jsonrpc'], '2.0')
        self.assertIn('result', body)
        self.assertEqual(body['result']['player']['id'], 1)

    def test_unknown_slug_404(self):
        r = self.client.get('/%s/no-such-slug/auction/live-board/data' % self.db)
        self.assertEqual(r.status_code, 404)

    def test_missing_key_404(self):
        del self.fake.kv['ac:%s:t:%s:lb' % (self.db, self.tid)]
        r = self.client.get('/%s/%s/auction/live-board/data' % (self.db, self.slug))
        self.assertEqual(r.status_code, 404)

    def test_redis_down_503(self):
        self.fake.fail = True
        r = self.client.get('/%s/%s/auction/live-board/data' % (self.db, self.slug))
        self.assertEqual(r.status_code, 503)

    def test_bad_json_503(self):
        self.fake.kv['ac:%s:t:%s:lb' % (self.db, self.tid)] = '{not-json'
        r = self.client.get('/%s/%s/auction/live-board/data' % (self.db, self.slug))
        self.assertEqual(r.status_code, 503)

    def test_db_isolation(self):
        other = 'other_db'
        self.fake.kv['ac:%s:slug:%s:tid' % (other, self.slug)] = '99'
        self.fake.hashes['ac:other_db:t:99:meta'] = {
            'live_board_active': '1', 'code_protected': '0',
        }
        self.fake.kv['ac:other_db:t:99:lb'] = json.dumps({'db': 'other', 'seq': 1})
        r1 = self.client.get('/%s/%s/auction/live-board/data' % (self.db, self.slug))
        r2 = self.client.get('/%s/%s/auction/live-board/data' % (other, self.slug))
        self.assertEqual(r1.json()['seq'], 0)
        self.assertEqual(r2.json()['db'], 'other')

    def test_live_inactive(self):
        self.fake.hashes['ac:%s:t:%s:meta' % (self.db, self.tid)] = {
            'live_board_active': '0', 'code_protected': '0',
        }
        r = self.client.get('/%s/%s/auction/live-board/data' % (self.db, self.slug))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), {'live_board_active': False})

    def test_code_protected_falls_back(self):
        self.fake.hashes['ac:%s:t:%s:meta' % (self.db, self.tid)] = {
            'live_board_active': '1', 'code_protected': '1',
        }
        r = self.client.get('/%s/%s/auction/live-board/data' % (self.db, self.slug))
        self.assertEqual(r.status_code, 404)

    def test_invalid_db_404(self):
        r = self.client.get('/bad db!/x/auction/live-board/data')
        self.assertEqual(r.status_code, 404)

    def test_missing_meta_falls_back(self):
        self.fake.hashes.pop('ac:%s:t:%s:meta' % (self.db, self.tid), None)
        r = self.client.get('/%s/%s/auction/live-board/data' % (self.db, self.slug))
        self.assertEqual(r.status_code, 404)


if __name__ == '__main__':
    unittest.main()
