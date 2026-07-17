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
    'version': '1.0.2',
    'summary': 'Responsive marketing website for AuctionChamp cricket auction platform',
    'sequence': 15,
    'description': """
AuctionChamp Website
====================
A fully responsive standalone marketing website for the AuctionChamp cricket
auction and tournament management platform. Includes a configurable landing page
with hero, features, testimonials, pricing, FAQ, and footer sections.

The website configurator is accessible under Auction Settings > Configuration.
    """,
    'category': 'Auction/Website',
    'depends': ['auction_module'],
    'data': [
        'security/ir.model.access.csv',
        'data/website_default_data.xml',
        'views/website_homepage_template.xml',
        'views/web_favicon.xml',
        'views/auction_website_config_view.xml',
        'views/auction_website_faq_view.xml',
        'views/auction_website_pricing_view.xml',
        'views/menu.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
