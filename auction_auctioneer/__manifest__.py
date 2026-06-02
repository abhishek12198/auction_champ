# -*- coding: utf-8 -*-
{
    'name': 'Auction Auctioneer Console',
    'version': '1.0',
    'summary': 'Live bidding console for the Auctioneer',
    'description': """
        Provides a dedicated Auctioneer Console – a full-screen web app (no Odoo
        layout) where the auctioneer can:
          • See all participating teams with their purse balance
          • See the current player on stage
          • Click a team button to open a bid modal
          • Place/increment bids that are reflected on the public live board
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
