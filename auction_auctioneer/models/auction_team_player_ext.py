# -*- coding: utf-8 -*-
from odoo import models, fields


class AuctionTeamPlayerExt(models.Model):
    """Extends auction.team.player with live-bid tracking fields."""
    _inherit = 'auction.team.player'

    current_bid = fields.Integer(
        string='Current Live Bid',
        default=0,
        help='The current highest bid placed by the auctioneer for this player. '
             'Reset to 0 when the player is sold or removed from stage.',
    )
    current_bid_team_id = fields.Many2one(
        'auction.team',
        string='Current Bidding Team',
        help='The team that placed the current highest bid.',
    )
