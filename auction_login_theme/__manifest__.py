# -*- coding: utf-8 -*-
{
    'name': 'Auction Champ — Login Theme',
    'version': '1.0',
    'summary': 'Beautiful sports-themed login screen for Auction Champ',
    'icon': '/auction_login_theme/static/description/icon.png',
    'description': """
        Replaces the default Odoo login screen with a fully custom,
        cricket/football/premier-league styled login page.
        On logout the user is redirected back to this screen automatically.
    """,
    'category': 'Theme',
    'depends': ['web', 'website'],
    'data': [
        'views/login_template.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
