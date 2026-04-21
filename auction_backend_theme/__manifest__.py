{
    'name': 'Auction Sports Backend Theme',
    'version': '15.0.1.0.0',
    'summary': 'Sporty backend theme for the Auction Champ application',
    'icon': '/auction_backend_theme/static/description/icon.png',
    'description': """
        A sports-inspired backend theme built for the Auction Champ platform.
        Features:
        - Navy/gold sports colour palette matching auction_module
        - Full-screen stadium app drawer with gold-accented app cards
        - Fixed left app sidebar with icon navigation
        - Rajdhani sports font throughout
        - Logo-branded navbar
    """,
    'author': 'Auction Champ',
    'category': 'Theme/Backend',
    'depends': ['base_setup', 'web_editor', 'mail', 'auction_module'],
    'data': ['data/webclient_templates.xml'],
    'assets': {
        # ── 1. Primary SCSS variables (loaded earliest, before Bootstrap) ──────
        'web._assets_primary_variables': [
            'auction_backend_theme/static/src/colors.scss',
        ],
        # ── 2. Backend helpers: component variables + mixins ──────────────────
        'web._assets_backend_helpers': [
            'auction_backend_theme/static/src/variables.scss',
            'auction_backend_theme/static/src/mixins.scss',
        ],
        # ── 3. OWL QWeb templates ─────────────────────────────────────────────
        'web.assets_qweb': [
            'auction_backend_theme/static/src/**/*.xml',
        ],
        # ── 4. Backend assets: SCSS, JS ───────────────────────────────────────
        'web.assets_backend': [
            'auction_backend_theme/static/src/global.scss',
            'auction_backend_theme/static/src/webclient/**/*.scss',
            'auction_backend_theme/static/src/webclient/**/*.js',
            'auction_backend_theme/static/src/search/**/*.scss',
            'auction_backend_theme/static/src/legacy/**/*.scss',
        ],
    },
    'installable': True,
    'auto_install': False,
    'application': False,
    'license': 'LGPL-3',
}
