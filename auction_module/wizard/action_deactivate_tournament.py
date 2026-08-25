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

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class AuctionDeactivateTournamentWizard(models.TransientModel):
    _name = 'auction.deactivate.tournament.wizard'
    _description = 'Deactivate Tournament'

    tournament_id = fields.Many2one(
        'auction.tournament', string='Tournament', required=True, readonly=True,
    )
    tournament_name = fields.Char(related='tournament_id.name', readonly=True)
    player_count = fields.Integer(compute='_compute_counts')
    team_count = fields.Integer(compute='_compute_counts')
    auction_count = fields.Integer(compute='_compute_counts')
    history_count = fields.Integer(compute='_compute_counts')
    advertiser_count = fields.Integer(compute='_compute_counts')
    deleted_player_count = fields.Integer(compute='_compute_counts')
    accept_consent = fields.Boolean(
        string='I understand and consent to deactivate this tournament',
        default=False,
    )

    @api.depends('tournament_id')
    def _compute_counts(self):
        Player = self.env['auction.team.player'].sudo().with_context(active_test=False)
        Team = self.env['auction.team'].sudo().with_context(active_test=False)
        Auction = self.env['auction.auction'].sudo().with_context(active_test=False)
        History = self.env['auction.history'].sudo().with_context(active_test=False)
        Advertiser = self.env['auction.advertiser'].sudo().with_context(active_test=False)
        Deleted = self.env['auction.team.player.deleted'].sudo()
        for wiz in self:
            tid = wiz.tournament_id.id
            if not tid:
                wiz.player_count = wiz.team_count = wiz.auction_count = 0
                wiz.history_count = wiz.advertiser_count = wiz.deleted_player_count = 0
                continue
            domain = [('tournament_id', '=', tid)]
            wiz.player_count = Player.search_count(domain)
            wiz.team_count = Team.search_count(domain)
            wiz.auction_count = Auction.search_count(domain)
            wiz.history_count = History.search_count(domain)
            wiz.advertiser_count = Advertiser.search_count(domain)
            wiz.deleted_player_count = Deleted.search_count(domain)

    def action_confirm(self):
        self.ensure_one()
        if not self.accept_consent:
            raise UserError(_(
                'Please read the list of changes and tick the consent box '
                'before deactivating this tournament.'
            ))
        if not self.tournament_id:
            raise UserError(_('No tournament selected.'))
        return self.tournament_id._deactivate_tournament_records()
