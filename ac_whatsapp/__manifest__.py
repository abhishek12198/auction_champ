# -*- coding: utf-8 -*-
##############################################################################
#
#  AuctionChamp WhatsApp Integration
#
##############################################################################
{
    'name': 'AuctionChamp WhatsApp',
    'version': '1.4.1',
    'summary': 'Twilio / Meta WhatsApp for invites and registration confirmation',
    'sequence': 17,
    'description': """
AuctionChamp WhatsApp
=====================
* Twilio WhatsApp (Content Templates) for player registration confirmation
* Optional Meta Cloud API provider
* Tournament Share on WhatsApp wizard
* Inbound Twilio webhook: /ac_whatsapp/twilio/reply
* Optional email with player-card PDF
    """,
    'category': 'Auction/WhatsApp',
    'depends': ['auction_module', 'mail'],
    'external_dependencies': {
        'python': ['requests', 'twilio'],
    },
    'data': [
        'security/ir.model.access.csv',
        'views/res_config_settings_view.xml',
        'views/tournament_invite_wizard_views.xml',
        'views/player_registration_inherit.xml',
        'views/auction_team_player_views.xml',
        'views/auction_tournament_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            '/ac_whatsapp/static/src/js/tournament_share.js',
        ],
    },
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
