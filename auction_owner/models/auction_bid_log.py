# -*- coding: utf-8 -*-
from odoo import fields, models


class AuctionBidLog(models.Model):
    """Records every live bid placed via the Owner Console.
    Used to restore the previous bid state when an owner exercises a revoke.
    Entries are scoped to a player so revokes on one player never affect another.
    """
    _name = 'auction.bid.log'
    _description = 'Live Auction Bid History'
    _order = 'id asc'

    player_id = fields.Many2one(
        'auction.team.player', required=True, ondelete='cascade', index=True,
    )
    team_id = fields.Many2one(
        'auction.team', required=True, ondelete='cascade',
    )
    bid_amount = fields.Integer(required=True)
    tournament_id = fields.Many2one(
        'auction.tournament', required=True, ondelete='cascade', index=True,
    )
    timestamp = fields.Datetime(default=fields.Datetime.now, readonly=True)
