# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
{
    'name' : 'One2many Widget',
    'version' : '1.2',
    'summary': 'Widget for One2many',
    'sequence': 10,
    'description': """

    """,
    'category': 'Extras/Extras',
    'website': 'xhttps://www.odoo.com/app/invoicing',
    'images': [],
    'depends': ['web'],
    'data': [
        'security/ir.model.access.csv',
        'views/question_view.xml',
        'views/survey_view.xml',
        'views/menu.xml',
    ],
    "assets": {
            "web.assets_backend": [
                "odoo_one2many_hierarchy/static/src/js/qa_matrix.js",
                "odoo_one2many_hierarchy/static/src/xml/qa_matrix.xml",
                "odoo_one2many_hierarchy/static/src/scss/qa_matrix.scss",
            ],
        },

    'demo': [
    ],
    'installable': True,
    'application': True,

    'license': 'LGPL-3',
}
