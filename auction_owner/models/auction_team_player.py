# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import api, fields, models


class AuctionTeamPlayerOwnerBidTimer(models.Model):
    _inherit = 'auction.team.player'

    owner_bid_deadline = fields.Datetime(
        string='Owner Bid Deadline',
        copy=False,
        help='When the owner-console bid window closes for the current live bid.',
    )

    def write(self, vals):
        vals = dict(vals)
        start_window = bool(vals.get('is_on_stage')) and 'owner_bid_deadline' not in vals
        if (
            'current_bid' in vals
            and not vals.get('current_bid')
            and 'owner_bid_deadline' not in vals
            and not start_window
        ):
            vals['owner_bid_deadline'] = False
        res = super().write(vals)
        if start_window:
            self.filtered(lambda player: player.state == 'auction')._restart_owner_bid_window(
                require_bid=False,
            )
        return res

    def get_owner_bid_timer_state(self):
        """Countdown shared by owner consoles and the auctioneer console."""
        self.ensure_one()
        tournament = self.tournament_id
        seconds = int(getattr(tournament, 'owner_bid_timer_seconds', 0) or 0) if tournament else 0
        deadline = self.owner_bid_deadline if seconds > 0 else False
        now = fields.Datetime.now()
        remaining = 0.0
        frozen = False
        running = False
        live = (
            seconds > 0
            and self.state == 'auction'
            and self.is_on_stage
            and deadline
        )
        if live:
            remaining = (deadline - now).total_seconds()
            if remaining <= 0:
                frozen = True
                remaining = 0.0
            else:
                running = True
        return {
            'enabled': seconds > 0,
            'seconds': seconds,
            'remaining': round(max(0.0, remaining), 2),
            'frozen': frozen,
            'running': running,
        }

    def _restart_owner_bid_window(self, require_bid=True):
        """Replace the deadline with a fresh full window. Never add time on."""
        for player in self:
            tournament = player.tournament_id
            seconds = int(getattr(tournament, 'owner_bid_timer_seconds', 0) or 0) if tournament else 0
            if seconds <= 0:
                if player.owner_bid_deadline:
                    player.sudo().write({'owner_bid_deadline': False})
                continue
            if require_bid and not (player.current_bid or 0) and not player.is_on_stage:
                continue
            player.sudo().write({
                'owner_bid_deadline': fields.Datetime.now() + timedelta(seconds=seconds),
            })
        return True

    @api.model
    def _owner_bid_window_closed(self, player):
        if not player or not hasattr(player, 'get_owner_bid_timer_state'):
            return False
        return bool(player.get_owner_bid_timer_state().get('frozen'))
