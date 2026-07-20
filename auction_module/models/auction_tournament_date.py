# -*- coding: utf-8 -*-
##############################################################################
#
#  AuctionChamp - Professional Sports Auction Management Platform
#
#  Copyright (c) 2026 AuctionChamp.
#  All Rights Reserved.
#
##############################################################################

from odoo import api, fields, models


class AuctionTournamentDate(models.Model):
    _name = 'auction.tournament.date'
    _description = 'Tournament Date'
    _order = 'date asc, id asc'

    tournament_id = fields.Many2one(
        'auction.tournament',
        string='Tournament',
        required=True,
        ondelete='cascade',
        index=True,
    )
    date = fields.Date(string='Date', required=True)

    _sql_constraints = [
        (
            'tournament_date_uniq',
            'unique(tournament_id, date)',
            'Each tournament date must be unique.',
        ),
    ]

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        if not self.env.context.get('skip_tournament_date_sync'):
            records.mapped('tournament_id')._sync_tournament_date_from_lines()
        return records

    def write(self, vals):
        res = super().write(vals)
        if (
            not self.env.context.get('skip_tournament_date_sync')
            and ('date' in vals or 'tournament_id' in vals)
        ):
            self.mapped('tournament_id')._sync_tournament_date_from_lines()
        return res

    def unlink(self):
        tournaments = self.mapped('tournament_id')
        res = super().unlink()
        if not self.env.context.get('skip_tournament_date_sync'):
            tournaments._sync_tournament_date_from_lines()
        return res
