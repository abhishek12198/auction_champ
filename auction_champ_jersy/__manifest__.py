# -*- coding: utf-8 -*-
{
    'name': 'AuctionChamp Jersey Collection',
    'version': '1.3.7',
    'summary': 'Team jersey survey collection (admin + public form)',
    'description': """
        Admin-managed jersey collection per team.

        • Create a team record with logos and jersey design
        • Auto-generate a shareable public survey URL (team slug)
        • Collect player jersey name, number, size and sleeve
        • Public form shows team branding and submitted entries table
        • Acknowledgement screen after submit (screenshot-friendly)
        • Print PDF (with logos) or Export Excel (data only) from backend
    """,
    'category': 'Auction/Auction',
    'sequence': 25,
    'depends': ['auction_module'],
    'external_dependencies': {
        'python': ['openpyxl'],
    },
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'report/jersey_report.xml',
        'report/jersey_report_template.xml',
        'views/jersey_team_views.xml',
        'views/jersey_survey_template.xml',
        'views/menu.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            '/auction_champ_jersy/static/src/css/jersey_survey.css',
        ],
    },
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
