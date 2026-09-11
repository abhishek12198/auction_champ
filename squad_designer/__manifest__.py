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
    'name': 'Squad Print Designer',
    'version': '1.0.0',
    'summary': 'Design & export professional cricket squad cards',
    'description': (
        'Create IPL / Big Bash style squad print cards with 5 professional templates. '
        'Select a template, preview it, then download as PNG or JPEG. '
        'Extendable to 10-20 templates. Standalone – no auction module dependency.'
    ),
    'category': 'Productivity',
    'author': '',
    'depends': ['base', 'web'],
    'data': [
        'security/ir.model.access.csv',
        'views/squad_player_category_view.xml',
        'views/squad_templates.xml',
        'views/squad_print_view.xml',
        'views/menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'squad_designer/static/src/css/squad_form.css',
        ],
    },
    'installable': True,
    'application': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
