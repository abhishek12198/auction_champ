# -*- coding: utf-8 -*-
from odoo import fields, models


class AuctionTournament(models.Model):
    _inherit = 'auction.tournament'

    hammer_count = fields.Integer(
        string='Counter Hammer Strikes',
        default=3,
        help='Number of hammer strikes shown on owner consoles when Enable Counter is activated.',
    )
    counter_started_at = fields.Datetime(
        string='Counter Started At',
        copy=False,
        help='Set each time the auctioneer activates the countdown. '
             'Owner consoles detect the change and play the mallet animation.',
    )

    # ── Bid Revoke settings ───────────────────────────────────────────────
    revoke_enabled = fields.Boolean(
        string='Enable Bid Revoke',
        default=False,
        help='Allow owners to revoke (undo) their most recent bid during live auction. '
             'Can be toggled off at any time to immediately disable the feature.',
    )
    max_revokes = fields.Integer(
        string='Max Revokes (Global)',
        default=0,
        help='Total revokes allowed across ALL owners for this tournament. '
             '0 = feature disabled even if Enable Bid Revoke is on.',
    )
    revokes_used = fields.Integer(
        string='Revokes Used',
        default=0,
        readonly=True,
        copy=False,
        help='Running count of revokes consumed globally. Auto-incremented on each revoke.',
    )
