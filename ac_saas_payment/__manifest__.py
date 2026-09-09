# -*- coding: utf-8 -*-
##############################################################################
#
#  AuctionChamp - Professional Sports Auction Management Platform
#
#  Copyright (c) 2026 AuctionChamp. All Rights Reserved.
#
##############################################################################
{
    'name': 'AuctionChamp SaaS Payment',
    'version': '1.1.3',
    'summary': 'Razorpay for SaaS upgrades and website plan signup',
    'sequence': 17,
    'description': """
AuctionChamp SaaS Payment (connector)
=====================================
Connects ac_saas_manager + ac_payment_gateway (+ website) for:

* Paid in-app plan upgrades (prorated)
* Website Plans & Pricing → Get Started → Razorpay → auto account + email credentials
    """,
    'category': 'Auction/Payment',
    'depends': [
        'ac_saas_manager',
        'ac_payment_gateway',
        'auction_champ_website',
        'mail',
    ],
    'external_dependencies': {
        'python': ['requests'],
    },
    'data': [
        'security/ir.model.access.csv',
        'data/ir_sequence_data.xml',
        'views/res_config_settings_view.xml',
        'views/saas_upgrade_request_views.xml',
        'views/upgrade_payment_templates.xml',
        'views/signup_templates.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
