# -*- coding: utf-8 -*-
"""Standalone Redis service tests (no Odoo / no live Redis required)."""
import json
import sys
import threading
import unittest
from unittest import mock

from odoo.addons.auction_module.services import auction_redis_service as redis_svc


class FakeRedis(object):
    """Minimal Redis stand-in: GET/SET/DELETE/PING/EVAL (CAS Lua)."""

    def __init__(self):
        self.store = {}
        self.hashes = {}
        self.fail_next = None
        self.calls = []

    def ping(self):
        self.calls.append('ping')
        if self.fail_next == 'ping':
            self.fail_next = None
            raise ConnectionError('redis down')
        return True

    def get(self, key):
        self.calls.append(('get', key))
        if self.fail_next == 'get':
            self.fail_next = None
            raise ConnectionError('redis down')
        return self.store.get(key)

    def set(self, key, value, nx=False, ex=None):
        self.calls.append(('set', key, value, nx, ex))
        if self.fail_next == 'set':
            self.fail_next = None
            raise ConnectionError('redis down')
        if nx and key in self.store:
            return False
        self.store[key] = value if isinstance(value, (bytes, str, int)) else str(value)
        return True

    def delete(self, key):
        self.store.pop(key, None)
        self.hashes.pop(key, None)
        return 1

    def eval(self, script, numkeys, *args):
        if self.fail_next == 'eval':
            self.fail_next = None
            raise ConnectionError('redis down')
        keys = args[:numkeys]
        argv = args[numkeys:]
        seq_key, lb_key, pj_key, bal_key, meta_key = keys
        incoming = int(argv[0])
        current = int(self.store.get(seq_key, -1))
        if incoming < current:
            return 0
        if argv[1]:
            self.store[lb_key] = argv[1]
        if argv[2]:
            self.store[pj_key] = argv[2]
        if argv[3]:
            self.store[bal_key] = argv[3]
        nmeta = int(argv[4] or 0)
        if nmeta:
            self.hashes[meta_key] = {}
            for i in range(nmeta):
                self.hashes[meta_key][str(argv[5 + i * 2])] = str(argv[6 + i * 2])
        self.store[seq_key] = incoming
        return 1


class FakeEnv(object):
    def __init__(self, enabled=True, uri='redis://127.0.0.1:6379/1', dbname='db_a'):
        self._enabled = enabled
        self._uri = uri
        self.cr = mock.Mock()
        self.cr.dbname = dbname
        params = {
            redis_svc.PARAM_ENABLED: 'True' if enabled else 'False',
            redis_svc.PARAM_URI: uri,
        }

        class ICP(object):
            def get_param(self, key, default=None):
                return params.get(key, default)

        icp = ICP()
        self._icp = icp

    def __getitem__(self, name):
        if name != 'ir.config_parameter':
            raise KeyError(name)
        box = mock.Mock()
        box.sudo.return_value = self._icp
        return box


class TestParseUri(unittest.TestCase):
    def test_tcp_uri(self):
        kw = redis_svc.parse_redis_uri('redis://127.0.0.1:6379/1')
        self.assertEqual(kw['host'], '127.0.0.1')
        self.assertEqual(kw['port'], 6379)
        self.assertEqual(kw['db'], 1)

    def test_unix_uri(self):
        kw = redis_svc.parse_redis_uri('unix:///var/run/redis/redis.sock?db=1')
        self.assertEqual(kw['unix_socket_path'], '/var/run/redis/redis.sock')
        self.assertEqual(kw['db'], 1)


class TestRedisService(unittest.TestCase):
    def setUp(self):
        redis_svc.reset_client()
        redis_svc._redis_import_failed = False
        redis_svc._redis_mod = mock.Mock()
        self.fake = FakeRedis()
        redis_svc._redis_mod.Redis = mock.Mock(return_value=self.fake)

    def tearDown(self):
        redis_svc.reset_client()
        redis_svc._redis_mod = None
        redis_svc._redis_import_failed = False

    def test_disabled(self):
        env = FakeEnv(enabled=False)
        self.assertFalse(redis_svc.is_enabled(env))
        self.assertIsNone(redis_svc.get_client(env))

    def test_unavailable(self):
        env = FakeEnv(enabled=True)
        self.fake.fail_next = 'ping'
        self.assertIsNone(redis_svc.get_client(env))

    def test_reconnect_after_ping_fail(self):
        env = FakeEnv(enabled=True)
        self.assertIsNotNone(redis_svc.get_client(env))
        redis_svc.reset_client()
        self.fake.fail_next = 'ping'
        self.assertIsNone(redis_svc.get_client(env))
        redis_svc._last_fail_at = 0.0
        self.assertIsNotNone(redis_svc.get_client(env))

    def test_get_set_atomic(self):
        env = FakeEnv(enabled=True)
        ok = redis_svc.write_snapshots(
            env, 7, 10,
            {'lb': {'seq': 10, 'k': 'lb'}, 'pj': {'seq': 10}, 'bal': {'seq': 10}},
            meta={'seq': 10},
        )
        self.assertTrue(ok)
        self.assertEqual(redis_svc.get_seq(env, 7), 10)
        lb = redis_svc.get_snapshot(env, 7, 'lb')
        self.assertEqual(lb['k'], 'lb')
        self.assertEqual(lb['seq'], 10)

    def test_stale_sequence_rejected(self):
        env = FakeEnv(enabled=True)
        redis_svc.write_snapshots(env, 7, 11, {'lb': {'seq': 11}})
        ok = redis_svc.write_snapshots(env, 7, 10, {'lb': {'seq': 10, 'stale': True}})
        self.assertFalse(ok)
        self.assertEqual(redis_svc.get_snapshot(env, 7, 'lb')['seq'], 11)

    def test_newer_sequence_accepted(self):
        env = FakeEnv(enabled=True)
        redis_svc.write_snapshots(env, 7, 10, {'lb': {'seq': 10}})
        ok = redis_svc.write_snapshots(env, 7, 12, {'lb': {'seq': 12}})
        self.assertTrue(ok)
        self.assertEqual(redis_svc.get_seq(env, 7), 12)

    def test_equal_sequence_accepted(self):
        env = FakeEnv(enabled=True)
        redis_svc.write_snapshots(env, 7, 10, {'lb': {'seq': 10, 'a': 1}})
        ok = redis_svc.write_snapshots(env, 7, 10, {'lb': {'seq': 10, 'a': 2}})
        self.assertTrue(ok)
        self.assertEqual(redis_svc.get_snapshot(env, 7, 'lb')['a'], 2)

    def test_multi_database_key_isolation(self):
        env_a = FakeEnv(enabled=True, dbname='db_a')
        env_b = FakeEnv(enabled=True, dbname='db_b')
        redis_svc.write_snapshots(env_a, 1, 5, {'lb': {'db': 'a', 'seq': 5}})
        redis_svc.write_snapshots(env_b, 1, 5, {'lb': {'db': 'b', 'seq': 5}})
        self.assertEqual(redis_svc.get_snapshot(env_a, 1, 'lb')['db'], 'a')
        self.assertEqual(redis_svc.get_snapshot(env_b, 1, 'lb')['db'], 'b')
        self.assertNotEqual(
            redis_svc.keys_for('db_a', 1)['lb'],
            redis_svc.keys_for('db_b', 1)['lb'],
        )

    def test_write_failure_returns_false(self):
        env = FakeEnv(enabled=True)
        self.fake.fail_next = 'eval'
        ok = redis_svc.write_snapshots(env, 7, 1, {'lb': {'seq': 1}})
        self.assertFalse(ok)

    def test_rebuild_lock(self):
        env = FakeEnv(enabled=True)
        self.assertTrue(redis_svc.acquire_rebuild_lock(env, 3))
        self.assertFalse(redis_svc.acquire_rebuild_lock(env, 3))
        redis_svc.release_rebuild_lock(env, 3)
        self.assertTrue(redis_svc.acquire_rebuild_lock(env, 3))

    def test_redis_restart_flush_then_rebuild(self):
        env = FakeEnv(enabled=True)
        redis_svc.write_snapshots(env, 7, 8, {'lb': {'seq': 8}})
        self.assertEqual(redis_svc.get_seq(env, 7), 8)
        self.fake.store.clear()
        self.fake.hashes.clear()
        self.assertIsNone(redis_svc.get_seq(env, 7))
        self.assertIsNone(redis_svc.get_snapshot(env, 7, 'lb'))
        ok = redis_svc.write_snapshots(env, 7, 8, {'lb': {'seq': 8, 'rebuilt': True}})
        self.assertTrue(ok)
        self.assertEqual(redis_svc.get_snapshot(env, 7, 'lb')['rebuilt'], True)


class TestOutOfOrderCallbacks(unittest.TestCase):
    def setUp(self):
        redis_svc.reset_client()
        redis_svc._redis_import_failed = False
        redis_svc._redis_mod = mock.Mock()
        self.fake = FakeRedis()
        redis_svc._redis_mod.Redis = mock.Mock(return_value=self.fake)

    def tearDown(self):
        redis_svc.reset_client()
        redis_svc._redis_mod = None

    def test_older_callback_cannot_overwrite_newer(self):
        env = FakeEnv(enabled=True)
        # Transaction B (seq 11) lands first
        redis_svc.write_snapshots(env, 9, 11, {'pj': {'seq': 11, 'bid': 200}})
        # Transaction A (seq 10) postcommit runs late
        ok = redis_svc.write_snapshots(env, 9, 10, {'pj': {'seq': 10, 'bid': 100}})
        self.assertFalse(ok)
        self.assertEqual(redis_svc.get_snapshot(env, 9, 'pj')['bid'], 200)
        self.assertEqual(redis_svc.get_seq(env, 9), 11)


if __name__ == '__main__':
    unittest.main()
