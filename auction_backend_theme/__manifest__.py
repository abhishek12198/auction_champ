# -*- coding: utf-8 -*-
##############################################################################
#
#  AuctionChamp - Professional Sports Auction Management Platform
#
#  Copyright (c) 2026 AuctionChamp.
#  All Rights Reserved.
#
#  CONFIDENTIAL & PROPRIETARY
#
#  This source code, including but not limited to its algorithms, business
#  logic, database structures, models, controllers, views, reports, templates,
#  APIs, documentation, and related materials, constitutes proprietary and
#  confidential information owned exclusively by AuctionChamp.
#
#  This software is protected by applicable copyright laws and international
#  intellectual property treaties. Unauthorized copying, reproduction,
#  modification, distribution, publication, sublicensing, reverse engineering,
#  decompilation, disassembly, disclosure, or use of this software, in whole
#  or in part, is strictly prohibited without the prior written permission of
#  AuctionChamp.
#
#  This software is licensed, not sold. Possession of the source code does not
#  grant any right to copy, modify, redistribute, or create derivative works
#  except as expressly permitted under a valid written license agreement with
#  AuctionChamp.
#
#  Any unauthorized use may result in civil and criminal penalties under
#  applicable intellectual property and copyright laws.
#
#  Company  : AuctionChamp
#  Website  : www.auctionchamp.live
#  Email    : auctionchamp.live@gmail.com
#
#  © 2026 AuctionChamp. All Rights Reserved.
#
##############################################################################

{
    'name': 'Auction Sports Backend Theme',
    'version': '15.0.1.0.7',
    'summary': 'Sporty backend theme for the Auction Champ application',
    'icon': '/auction_backend_theme/static/description/icon.png',
    'description': """
        A sports-inspired backend theme built for the Auction Champ platform.
        Features:
        - Navy/gold sports colour palette matching auction_module
        - Full-screen stadium app drawer with gold-accented app cards
        - Fixed left app sidebar with icon navigation
        - Rajdhani sports font throughout
        - Logo-branded navbar
    """,
    'author': 'Auction Champ',
    'category': 'Theme/Backend',
    'depends': ['base_setup', 'web_editor', 'mail', 'auction_module'],
    'data': [
        'data/webclient_templates.xml',
        'views/res_config_settings_view.xml',
    ],
    'assets': {
        # ── 1. Primary SCSS variables (loaded earliest, before Bootstrap) ──────
        'web._assets_primary_variables': [
            'auction_backend_theme/static/src/colors.scss',
        ],
        # ── 2. Backend helpers: component variables + mixins ──────────────────
        'web._assets_backend_helpers': [
            'auction_backend_theme/static/src/variables.scss',
            'auction_backend_theme/static/src/mixins.scss',
        ],
        # ── 3. OWL QWeb templates ─────────────────────────────────────────────
        'web.assets_qweb': [
            'auction_backend_theme/static/src/**/*.xml',
        ],
        # ── 4. Backend assets: SCSS, JS ───────────────────────────────────────
        'web.assets_backend': [
            'auction_backend_theme/static/src/global.scss',
            'auction_backend_theme/static/src/webclient/**/*.scss',
            'auction_backend_theme/static/src/webclient/**/*.js',
            'auction_backend_theme/static/src/search/**/*.scss',
            'auction_backend_theme/static/src/legacy/**/*.scss',
        ],
    },
    'installable': True,
    'auto_install': False,
    'application': False,
    'license': 'Other proprietary',
}
