# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
{
    'name' : 'Auction',
    'version' : '1.2',
    'summary': 'Sports Auction module',
    'sequence': 10,
    'description': """

    """,
    'category': 'Auction/Auction',
    'website': 'xhttps://www.odoo.com/app/invoicing',
    'images': [],
    'depends': ['website', 'web_notify'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/report_paper_format_landscape.xml',
        'views/auction_tournament_view.xml',
        'views/auction_team_player_type_view.xml',

        'wizard/action_sell_player_view.xml',
        'wizard/action_set_key_player_view.xml',
        'views/auction_team_player.xml',
        'views/auction_team_players_template.xml',
        'views/auction_player_card_print_list.xml',
        'views/auction_player_template_new.xml',
        'views/auction_blank_templates.xml',
        'views/auction_show_balance_template1.xml',
        'report/auction_report_template.xml',
        'views/auction_history_template.xml',
        'report/players_card.xml',
        'report/auction_report.xml',
        'views/auction_team_view.xml',
        'wizard/edit_player_points_view.xml',
        'views/auction_player_card_print.xml',
        'wizard/action_view_team_details_view.xml',
        'views/auction_auction_view.xml',
        'wizard/action_start_auction_view.xml',

        'wizard/action_set_to_auction_view.xml',

        'views/menu.xml',
    ],
    'assets': {
            'web.assets_backend': [
                    '/auction_module/static/src/css/wizard_style.css',

                ],
            'web.assets_frontend': [
                'auction_module/static/src/js/auction.js',

            ],
        },
    'demo': [
    ],
    'installable': True,
    'application': True,

    'license': 'LGPL-3',
}
