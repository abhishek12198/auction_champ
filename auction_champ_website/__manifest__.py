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
    'name': 'AuctionChamp Website',
    'version': '1.0.49',
    'summary': 'Responsive marketing website for AuctionChamp premier sports auction platform',
    'sequence': 15,
    'description': """
AuctionChamp Website
====================
A fully responsive standalone marketing website for the AuctionChamp cricket
auction and tournament management platform. Includes a configurable landing page
with hero, features, testimonials, pricing, FAQ, and footer sections.

Also restyles /web/login (via inherit of auction_login_theme) to match the
website navy / blue / gold palette, and sets the backend primary accent
to the website blue (#1565c0) without restyling navbar navy.

The website configurator is accessible under Auction Settings > Configuration.
    """,
    'category': 'Auction/Website',
    'depends': [
        'auction_module',
        'ac_saas_manager',
        'web',
        'website',
        'auction_login_theme',
        'auction_backend_theme',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/website_default_data.xml',
        'views/website_nav_auth.xml',
        'views/website_homepage_template.xml',
        'views/calendar_template.xml',
        'views/auction_tournament_views.xml',
        'views/website_login_template.xml',
        'views/privacy_policy_template.xml',
        'views/terms_conditions_template.xml',
        'views/user_manual_template.xml',
        'views/web_favicon.xml',
        'views/backend_brand_unify.xml',
        'views/auction_website_config_view.xml',
        'views/auction_website_faq_view.xml',
        'views/menu.xml',
    ],
    'assets': {
        'web._assets_primary_variables': [
            'auction_champ_website/static/src/scss/backend_primary_variables.scss',
        ],
        'web._assets_backend_helpers': [
            'auction_champ_website/static/src/scss/backend_helpers.scss',
        ],
        'web.assets_backend': [
            'auction_champ_website/static/src/css/backend_brand.css',
        ],
    },
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
