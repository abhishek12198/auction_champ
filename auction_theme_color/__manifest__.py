{
    'name': 'Primary Color Theme',
    'version': '15.0.1.0.0',
    'summary': 'Lightweight theme to change Odoo primary color',
    'author': 'You',
    'category': 'Theme',
    'depends': ['web'],
    'data': [
             # 'views/assets.xml'
             ],
    'assets': {
        'web.assets_backend': [
            # 'auction_theme_color/static/src/css/custom_primary.scss',
        ],
        'web.assets_frontend': [
            # 'auction_theme_color/static/src/css/custom_primary.scss',
        ],
    },
    'installable': True,
    'application': False,
}
