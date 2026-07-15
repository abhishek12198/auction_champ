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
    'name': 'Auction Auctioneer Console',
    'version': '1.4.6',
    'summary': 'Live bidding console for the Auctioneer',
    'description': """
        Provides a dedicated Auctioneer Console – a full-screen web app (no Odoo
        layout) where the auctioneer can:
          • Drive showcase flow from the console (Manual: dice + numbers,
            Random: Next Player) — synced to the projector via is_on_stage / dice
          • See all participating teams with their purse balance
          • See the current player on stage
          • Click a team button to open a bid modal
          • Place/increment bids that are reflected on the public live board
            and the projector screen
          • Finalize the sale directly from the console
    """,
    'category': 'Auction/Auction',
    'sequence': 11,
    'depends': ['auction_module'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'views/auctioneer_console_template.xml',
        'views/live_board_ext.xml',
        'views/projector_ext.xml',
        'views/sell_modal_ext.xml',
        'views/menu.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            '/auction_auctioneer/static/src/css/auctioneer_console.css',
            '/auction_auctioneer/static/src/js/auctioneer_console.js',
        ],
    },
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
