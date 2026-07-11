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

from odoo import api, models, fields


class ResUsers(models.Model):
    _inherit = 'res.users'

    tournament_ids = fields.Many2many(
        'auction.tournament',
        'auction_tournament_user_rel',
        'user_id', 'tournament_id',
        'Tournaments',
    )
    # The single tournament this user operates in.
    # Non-admin users get this auto-injected into every record they create.
    tournament_id = fields.Many2one(
        'auction.tournament',
        string='Active Tournament',
        help='The tournament this user belongs to. '
             'Used to automatically scope records and QWeb templates. '
             'Visible and assignable only by Administrators.',
    )
    # For Team Owner users — their assigned team within the tournament.
    team_id = fields.Many2one(
        'auction.team',
        string='Team',
        help='The team this user manages (Owner role only).',
    )

    @api.model
    def _auction_sync_tournament_assignments(self):
        """Keep Active Tournament on Organizers M2M (for ir.rule domains)."""
        users = self.sudo().search([('tournament_id', '!=', False)])
        for user in users:
            if user.tournament_id not in user.tournament_ids:
                user.with_context(skip_tournament_sync=True).write({
                    'tournament_ids': [(4, user.tournament_id.id)],
                })

    def write(self, vals):
        res = super().write(vals)
        if self.env.context.get('skip_tournament_sync'):
            return res
        # Keep Active Tournament and Organizers M2M in sync so record rules
        # that use tournament_ids + tournament_id always see the assignment.
        sync_ctx = dict(self.env.context, skip_tournament_sync=True)
        if 'tournament_id' in vals:
            for user in self:
                if user.tournament_id and user.tournament_id not in user.tournament_ids:
                    user.with_context(**sync_ctx).sudo().write({
                        'tournament_ids': [(4, user.tournament_id.id)],
                    })
        if 'tournament_ids' in vals:
            for user in self:
                if not user.tournament_id and user.tournament_ids:
                    user.with_context(**sync_ctx).sudo().write({
                        'tournament_id': user.tournament_ids[:1].id,
                    })
        return res

    @api.model_create_multi
    def create(self, vals_list):
        users = super().create(vals_list)
        sync_ctx = dict(self.env.context, skip_tournament_sync=True)
        for user in users:
            updates = {}
            if user.tournament_id and user.tournament_id not in user.tournament_ids:
                updates['tournament_ids'] = [(4, user.tournament_id.id)]
            if not user.tournament_id and user.tournament_ids:
                updates['tournament_id'] = user.tournament_ids[:1].id
            if updates:
                user.with_context(**sync_ctx).sudo().write(updates)
        return users
