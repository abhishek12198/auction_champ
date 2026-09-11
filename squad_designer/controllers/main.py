# -*- coding: utf-8 -*-
##############################################################################
#
#  AuctionChamp - Professional Sports Auction Management Platform
#
#  Copyright (c) 2026 AuctionChamp.
#  All Rights Reserved.
#
#  CONFIDENTIAL & PROPRIETARY
#
#  This source code, including but not limited to its algorithms, business
#  logic, database structures, models, controllers, views, reports, templates,
#  APIs, documentation, and related materials, constitutes proprietary and
#  confidential information owned exclusively by AuctionChamp.
#
#  This software is protected by applicable copyright laws and international
#  intellectual property treaties. Unauthorized copying, reproduction,
#  modification, distribution, publication, sublicensing, reverse engineering,
#  decompilation, disassembly, disclosure, or use of this software, in whole
#  or in part, is strictly prohibited without the prior written permission of
#  AuctionChamp.
#
#  This software is licensed, not sold. Possession of the source code does not
#  grant any right to copy, modify, redistribute, or create derivative works
#  except as expressly permitted under a valid written license agreement with
#  AuctionChamp.
#
#  Any unauthorized use may result in civil and criminal penalties under
#  applicable intellectual property and copyright laws.
#
#  Company  : AuctionChamp
#  Website  : www.auctionchamp.live
#  Email    : auctionchamp.live@gmail.com
#
#  © 2026 AuctionChamp. All Rights Reserved.
#
##############################################################################

from odoo import http
from odoo.http import request

_TEMPLATE_MAP = {
    'ipl_classic':     'squad_designer.squad_tmpl_ipl_classic',
    'modern_gradient': 'squad_designer.squad_tmpl_modern_gradient',
    'bbl_bold':        'squad_designer.squad_tmpl_bbl_bold',
    'test_classic':    'squad_designer.squad_tmpl_test_classic',
    'minimalist_pro':  'squad_designer.squad_tmpl_minimalist_pro',
}


class SquadDesignerController(http.Controller):

    @http.route('/squad/preview/<int:squad_id>', type='http', auth='user',
                website=False, methods=['GET'])
    def preview(self, squad_id, **kw):
        squad = request.env['squad.print'].browse(squad_id)
        if not squad.exists():
            return request.not_found()
        template_id = _TEMPLATE_MAP.get(squad.template, _TEMPLATE_MAP['ipl_classic'])
        company = request.env.user.company_id
        favicon_url = '/web/image/res.company/%d/favicon' % company.id
        return request.render(template_id, {'squad': squad, 'favicon_url': favicon_url},
                              headers=[('Content-Type', 'text/html; charset=utf-8')])
