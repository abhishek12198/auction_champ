# -*- coding: utf-8 -*-
##############################################################################
#
#  AuctionChamp - Professional Sports Auction Management Platform
#
#  Copyright (c) 2026 AuctionChamp.
#  All Rights Reserved.
#
#  Company  : AuctionChamp
#  Website  : www.auctionchamp.live
#  Email    : auctionchamp.live@gmail.com
#
#  © 2026 AuctionChamp. All Rights Reserved.
#
##############################################################################

from odoo import api, fields, models


class AuctionUserTemplate(models.Model):
    _name = 'auction.user.template'
    _description = 'Auction User Template'
    _order = 'name'

    name = fields.Char(string='Template Name', required=True)
    active = fields.Boolean(default=True)
    group_ids = fields.Many2many(
        'res.groups',
        'auction_user_template_group_rel',
        'template_id',
        'group_id',
        string='Auction Access',
        domain=lambda self: self.env['res.users']._auction_access_group_domain(),
        help='Roles granted when this template is selected on a user.',
    )

    @api.model
    def _get_auction_group_domain(self):
        return self.env['res.users']._auction_access_group_domain()
