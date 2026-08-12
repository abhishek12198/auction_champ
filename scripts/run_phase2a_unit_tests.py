#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Run Phase 2A unit tests without a full Odoo server.

Loads auction_module services/mixin via importlib after installing a
minimal ``odoo`` stub so tests can run on a laptop.
"""
import importlib.util
import os
import sys
import types
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
MOD = os.path.join(ROOT, 'auction_module')


def _install_odoo_stub():
    if 'odoo' in sys.modules and hasattr(sys.modules['odoo'], 'api'):
        return
    odoo = types.ModuleType('odoo')
    api = types.ModuleType('odoo.api')

    def _deco(fn):
        return fn

    api.model_create_multi = _deco
    api.model = _deco
    models = types.ModuleType('odoo.models')

    class AbstractModel(object):
        _name = None
        _description = None

    models.AbstractModel = AbstractModel
    models.Model = AbstractModel
    fields = types.ModuleType('odoo.fields')

    class Datetime(object):
        @staticmethod
        def to_string(value):
            return str(value) if value else None

        @staticmethod
        def now():
            return None

    fields.Datetime = Datetime
    odoo.api = api
    odoo.models = models
    odoo.fields = fields
    addons = types.ModuleType('odoo.addons')
    odoo.addons = addons
    sys.modules['odoo'] = odoo
    sys.modules['odoo.api'] = api
    sys.modules['odoo.models'] = models
    sys.modules['odoo.fields'] = fields
    sys.modules['odoo.addons'] = addons


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def main():
    _install_odoo_stub()
    pkg = types.ModuleType('odoo.addons.auction_module')
    pkg.__path__ = [MOD]
    sys.modules['odoo.addons.auction_module'] = pkg
    svc_pkg = types.ModuleType('odoo.addons.auction_module.services')
    svc_pkg.__path__ = [os.path.join(MOD, 'services')]
    sys.modules['odoo.addons.auction_module.services'] = svc_pkg
    models_pkg = types.ModuleType('odoo.addons.auction_module.models')
    models_pkg.__path__ = [os.path.join(MOD, 'models')]
    sys.modules['odoo.addons.auction_module.models'] = models_pkg

    _load(
        'odoo.addons.auction_module.services.auction_redis_service',
        os.path.join(MOD, 'services', 'auction_redis_service.py'),
    )
    _load(
        'odoo.addons.auction_module.services.auction_live_payload',
        os.path.join(MOD, 'services', 'auction_live_payload.py'),
    )
    _load(
        'odoo.addons.auction_module.models.auction_live_snapshot_mixin',
        os.path.join(MOD, 'models', 'auction_live_snapshot_mixin.py'),
    )

    tests_dir = os.path.join(MOD, 'tests')
    redis_tests = _load(
        'test_auction_redis_service',
        os.path.join(tests_dir, 'test_auction_redis_service.py'),
    )
    hook_tests = _load(
        'test_auction_live_snapshot_hooks',
        os.path.join(tests_dir, 'test_auction_live_snapshot_hooks.py'),
    )
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    suite.addTests(loader.loadTestsFromModule(redis_tests))
    suite.addTests(loader.loadTestsFromModule(hook_tests))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    sys.exit(main())
