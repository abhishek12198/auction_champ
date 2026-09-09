# -*- coding: utf-8 -*-
##############################################################################
#
#  AuctionChamp - Professional Sports Auction Management Platform
#
#  Copyright (c) 2026 AuctionChamp. All Rights Reserved.
#
##############################################################################
{
    'name': 'AuctionChamp SaaS Manager',
    'version': '1.0.77',
    'summary': 'Single-DB SaaS plans and account limits for AuctionChamp',
    'sequence': 5,
    'description': """
AuctionChamp SaaS Manager
=========================
Overlay module (does not modify auction_module source).

* One SaaS account = one login user
* Plans: Starter, Classic, Pro, Champion
* Enforces tournament / team / player caps and feature gates
* In-app plan upgrade requests (manual approve)
* Navbar tournament switcher (shared or per-browser parallel mode by plan)
* All logic lives in ac_saas_manager via model inheritance
    """,
    'category': 'Auction/SaaS',
    'depends': [
        'auction_module',
        'mail',
    ],
    'data': [
        'security/saas_security.xml',
        'security/ir.model.access.csv',
        'data/saas_plan_data.xml',
        'data/saas_plan_redefine.xml',
        'data/saas_plan_parallel_sessions.xml',
        'data/saas_plan_mystery.xml',
        'data/saas_sync_data.xml',
        'data/saas_upgrade_request_data.xml',
        'data/saas_expire_cron.xml',
        'views/saas_plan_views.xml',
        'views/saas_account_views.xml',
        'views/saas_upgrade_request_views.xml',
        'views/auction_tournament_views.xml',
        'views/auction_player_tier_views.xml',
        'views/menu.xml',
    ],
    'assets': {
        'web.assets_backend': [
            '/ac_saas_manager/static/src/css/tournament_systray.css',
            '/ac_saas_manager/static/src/js/tournament_systray.js',
        ],
        'web.assets_qweb': [
            '/ac_saas_manager/static/src/xml/tournament_systray.xml',
        ],
    },
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
    'post_init_hook': 'post_init_hook',
}
