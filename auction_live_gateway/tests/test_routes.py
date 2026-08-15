# -*- coding: utf-8 -*-
"""Route registration smoke tests."""
import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app.main import app


class RouteTests(unittest.TestCase):
    def test_routes_registered(self):
        paths = {getattr(r, 'path', None) for r in app.routes}
        self.assertIn('/health', paths)
        self.assertIn('/ready', paths)
        self.assertIn('/{db}/{slug}/auction/live-board/data', paths)
        self.assertIn('/{db}/auction/projector/{slug}/data', paths)
        self.assertIn('/{db}/{slug}/auction/show/team/balance/json', paths)
        self.assertIn('/{db}/{slug}/auction/live-board/events', paths)
        self.assertIn('/{db}/auction/projector/{slug}/events', paths)
        self.assertIn('/{db}/{slug}/auction/show/team/balance/events', paths)


if __name__ == '__main__':
    unittest.main()
