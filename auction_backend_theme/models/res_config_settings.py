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

from odoo import api, fields, models

PARAM_KEY = 'auction.backend.title'
DEFAULT_TITLE = 'AuctionChamp'


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    auction_backend_title = fields.Char(
        string='Backend App Title',
        help='Name shown in the browser tab instead of "Odoo" (e.g. AuctionChamp).',
        config_parameter=PARAM_KEY,
    )

    @api.model
    def get_values(self):
        res = super().get_values()
        res['auction_backend_title'] = (
            self.env['ir.config_parameter'].sudo().get_param(PARAM_KEY, DEFAULT_TITLE)
        )
        return res
