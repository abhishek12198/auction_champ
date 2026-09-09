# -*- coding: utf-8 -*-
##############################################################################
#
#  AuctionChamp - Professional Sports Auction Management Platform
#
#  Copyright (c) 2026 AuctionChamp. All Rights Reserved.
#
##############################################################################
{
    'name': 'AuctionChamp Payment Gateway',
    'version': '1.0.12',
    'summary': 'Razorpay integration for player registration payments',
    'sequence': 16,
    'description': """
AuctionChamp Payment Gateway (Razorpay)
=======================================
Tournament-level registration payment via Razorpay.

* Include Registration Payment — master switch
* Optional — register without paying; pay later via Razorpay
* Mandatory — player is created only after successful payment
* When disabled — existing QR / proof upload flow is unchanged
    """,
    'category': 'Auction/Payment',
    'depends': ['auction_module'],
    'external_dependencies': {
        'python': ['requests'],
    },
    'data': [
        'security/ir.model.access.csv',
        'data/ir_sequence_data.xml',
        'views/res_config_settings_view.xml',
        'views/auction_tournament_view.xml',
        'views/payment_templates.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
