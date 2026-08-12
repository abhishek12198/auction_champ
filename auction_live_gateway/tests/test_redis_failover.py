# -*- coding: utf-8 -*-
"""Failover / route shape tests."""
import json
import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from fastapi.testclient import TestClient
from app import redis_client
from app.main import app
from tests.test_gateway import FakeRedis


class FailoverTests(unittest.TestCase):
    def setUp(self):
        self.fake = FakeRedis()
        redis_client.reset()
        redis_client.get_client = lambda: self.fake
        self.client = TestClient(app)

    def test_ready_when_redis_down(self):
        self.fake.fail = True
        r = self.client.get('/ready')
        self.assertEqual(r.status_code, 503)

    def test_balance_missing_slug(self):
        r = self.client.get('/main_db_1/missing/auction/show/team/balance/json')
        self.assertEqual(r.status_code, 404)

    def test_projector_get_not_allowed(self):
        # Frontend uses POST; GET should 405
        r = self.client.get('/main_db_1/auction/projector/x/data')
        self.assertEqual(r.status_code, 405)


if __name__ == '__main__':
    unittest.main()
