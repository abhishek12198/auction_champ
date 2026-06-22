# -*- coding: utf-8 -*-
{
    'name': 'AuctionChamp Website',
    'version': '1.0',
    'summary': 'Responsive marketing website for AuctionChamp cricket auction platform',
    'sequence': 15,
    'description': """
AuctionChamp Website
====================
A fully responsive standalone marketing website for the AuctionChamp cricket
auction and tournament management platform. Includes a configurable landing page
with hero, features, testimonials, pricing, FAQ, and footer sections.

The website configurator is accessible under Auction Settings > Configuration.
    """,
    'category': 'Auction/Website',
    'depends': ['auction_module'],
    'data': [
        'security/ir.model.access.csv',
        'data/website_default_data.xml',
        'views/website_homepage_template.xml',
        'views/web_favicon.xml',
        'views/auction_website_config_view.xml',
        'views/auction_website_faq_view.xml',
        'views/auction_website_pricing_view.xml',
        'views/menu.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
