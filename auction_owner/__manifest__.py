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
