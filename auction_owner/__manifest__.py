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
    'name': 'Auction Owner Console',
    'version': '1.0',
    'summary': 'Mobile-friendly owner dashboard for live auction tracking and bidding',
    'depends': ['auction_module', 'auction_auctioneer'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'views/res_users_views.xml',
        'views/auction_team_view_ext.xml',
        'views/auction_tournament_counter_ext.xml',
        'views/display_auction_counter_ext.xml',
        'views/display_auction_bid_ext.xml',
        'views/owner_console_template.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'auction_owner/static/src/css/owner_console.css',
            'auction_owner/static/src/js/owner_console.js',
        ],
    },
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
