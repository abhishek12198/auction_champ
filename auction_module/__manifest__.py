# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
{
    'name' : 'Auction Champ',
    'version' : '1.2',
    'summary': 'Sports Auction module',
    'sequence': 10,
    'description': """

    """,
    'category': 'Auction/Auction',
    'website': 'xhttps://www.odoo.com/app/invoicing',
    'images': [],
    'depends': ['bus','website', 'web_notify'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/report_paper_format_landscape.xml',
        'views/auction_tournament_view.xml',
        'views/auction_player_tier_view.xml',
        'wizard/action_sell_player_view.xml',
        'wizard/action_set_key_player_view.xml',
        'views/auction_player_modal_template.xml',
        'views/auction_team_player.xml',
        'views/auction_team_players_template.xml',
        'views/auction_team_players_template_pistah.xml',
        'views/player_sequence_selector.xml',
        'views/auction_player_card_print_list.xml',
        'views/auction_player_card_print_list_butterscotch.xml',
        'views/auction_player_card_print_list_strawberry.xml',
        'views/auction_player_card_print_list_cherry.xml',
        'views/auction_player_card_print_list_pistah.xml',
        'views/auction_history_view.xml',
        'views/auction_player_sell_modal.xml',
        'views/auction_player_template_new.xml',
        'views/auction_player_template_butterscotch.xml',
        'views/auction_player_template_strawberry.xml',
        'views/auction_player_template_cherry.xml',
        'views/auction_player_template_pistah.xml',
        'views/auction_blank_templates.xml',
        'views/auction_show_balance_template1.xml',
        'views/auction_show_balance_template1_pistah.xml',
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
        'wizard/action_bring_to_auction_view.xml',
        'wizard/action_set_to_auction_view.xml',
        'wizard/action_set_to_draft_view.xml',
        'wizard/team_pool_wizard_view.xml',
        'wizard/auction_pdf_to_png_view.xml',
        'views/auction_status_template.xml',
        'views/menu.xml',
    ],
    'assets': {
            'web.assets_backend': [
                    '/auction_module/static/src/js/dropdown_fix.js',
                    '/auction_module/static/src/js/center_toast.js',
                    '/auction_module/static/src/css/wizard_style.css',
                    '/auction_module/static/src/css/sticky_header.css',
                    '/auction_module/static/src/lib/html2canvas.min.js',
                    '/auction_module/static/src/js/sold_sound.js',
                    '/auction_module/static/src/js/sold_toast.js',
                    '/auction_module/static/src/js/screenshot.js',
                    '/auction_module/static/src/js/pool_snapshot.js',
                    # auction_live_queue.css is intentionally excluded from backend assets
                    # because it overrides html/body height and overflow which breaks
                    # Odoo's backend layout (including the Import File feature).
                    # It is only needed for the frontend live-queue page.
                    '/auction_module/static/src/js/auction_live_queue.js',
                    '/auction_module/static/src/css/sold_toast.css',
                    '/auction_module/static/src/css/kanban.css',
                    '/auction_module/static/src/css/auction_status.css',
                    '/auction_module/static/src/js/auction_status.js',

                ],
            'web.assets_frontend': [
                '/auction_module/static/src/lib/html2canvas.min.js',
                '/auction_module/static/src/css/auction_live_queue.css',
                '/auction_module/static/src/js/auction_live_queue.js',
                '/auction_module/static/src/js/screenshot.js',
                '/auction_module/static/src/js/auction.js',


            ],
        },
    'demo': [
    ],
    'installable': True,
    'application': True,

    'license': 'LGPL-3',
}
