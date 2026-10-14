# -*- coding: utf-8 -*-
import time
from datetime import timedelta

from odoo import api, fields, models


class AuctionTeamPlayerOwnerBidTimer(models.Model):
    _inherit = 'auction.team.player'

    owner_bid_deadline = fields.Datetime(
        string='Owner Bid Deadline',
        copy=False,
        help='When the owner-console bid window closes for the current live bid.',
    )
    owner_bid_held = fields.Boolean(
        string='Owner Bid Timer Held',
        copy=False,
        help='Operator paused the shared owner bid clock. Remaining time is frozen.',
    )
    owner_bid_hold_remaining = fields.Float(
        string='Owner Bid Hold Remaining',
        copy=False,
        help='Seconds left on the owner bid clock when it was held.',
    )
    owner_bid_timer_epoch = fields.Float(
        string='Owner Bid Timer Epoch',
        copy=False,
        help='Monotonic stamp for hold/resume/restart so stale polls cannot rewind the clock.',
    )

    def init(self):
        super().init()
        self._ensure_owner_bid_hold_columns()

    def _ensure_owner_bid_hold_columns(self):
        registry = self.env.registry
        if getattr(registry, '_auction_owner_hold_cols_v2', False):
            return
        cr = self.env.cr
        cr.execute(
            """
            SELECT column_name FROM information_schema.columns
             WHERE table_name = 'auction_team_player'
               AND column_name IN (
                   'owner_bid_held',
                   'owner_bid_hold_remaining',
                   'owner_bid_timer_epoch'
               )
            """
        )
        have = {row[0] for row in cr.fetchall()}
        if 'owner_bid_held' not in have:
            cr.execute(
                'ALTER TABLE auction_team_player ADD COLUMN owner_bid_held boolean'
            )
        if 'owner_bid_hold_remaining' not in have:
            cr.execute(
                'ALTER TABLE auction_team_player '
                'ADD COLUMN owner_bid_hold_remaining double precision'
            )
        if 'owner_bid_timer_epoch' not in have:
            cr.execute(
                'ALTER TABLE auction_team_player '
                'ADD COLUMN owner_bid_timer_epoch double precision'
            )
        registry._auction_owner_hold_cols_v2 = True

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
            vals['owner_bid_held'] = False
            vals['owner_bid_hold_remaining'] = 0.0
            vals['owner_bid_timer_epoch'] = time.time()
        res = super().write(vals)
        if start_window:
            self.filtered(lambda player: player.state == 'auction')._restart_owner_bid_window(
                require_bid=False,
            )
        return res

    def get_owner_bid_timer_state(self):
        """Countdown shared by owner consoles and the auctioneer console."""
        self.ensure_one()
        self._ensure_owner_bid_hold_columns()
        tournament = self.tournament_id
        seconds = int(getattr(tournament, 'owner_bid_timer_seconds', 0) or 0) if tournament else 0
        deadline = self.owner_bid_deadline if seconds > 0 else False
        held = bool(self.owner_bid_held) if seconds > 0 else False
        now = fields.Datetime.now()
        remaining = 0.0
        frozen = False
        running = False
        live = (
            seconds > 0
            and self.state == 'auction'
            and self.is_on_stage
            and (deadline or held)
        )
        if live:
            if held:
                remaining = max(0.0, float(self.owner_bid_hold_remaining or 0.0))
                if remaining <= 0:
                    frozen = True
                    held = False
                    remaining = 0.0
            else:
                remaining = (deadline - now).total_seconds()
                if remaining <= 0:
                    frozen = True
                    remaining = 0.0
                else:
                    running = True
        else:
            held = False
        return {
            'enabled': seconds > 0,
            'seconds': seconds,
            'remaining': round(max(0.0, remaining), 2),
            'frozen': frozen,
            'running': running,
            'held': held,
            'epoch': float(self.owner_bid_timer_epoch or 0.0),
        }

    def _clear_owner_bid_hold_vals(self):
        return {
            'owner_bid_held': False,
            'owner_bid_hold_remaining': 0.0,
        }

    def _restart_owner_bid_window(self, require_bid=True):
        """Replace the deadline with a fresh full window. Never add time on."""
        for player in self:
            tournament = player.tournament_id
            seconds = int(getattr(tournament, 'owner_bid_timer_seconds', 0) or 0) if tournament else 0
            clear_hold = player._clear_owner_bid_hold_vals()
            if seconds <= 0:
                vals = dict(clear_hold)
                if player.owner_bid_deadline:
                    vals['owner_bid_deadline'] = False
                if vals:
                    player.sudo().write(vals)
                continue
            if require_bid and not (player.current_bid or 0) and not player.is_on_stage:
                continue
            vals = dict(clear_hold)
            vals['owner_bid_deadline'] = fields.Datetime.now() + timedelta(seconds=seconds)
            vals['owner_bid_timer_epoch'] = time.time()
            player.sudo().write(vals)
        return True

    def action_hold_owner_bid_timer(self):
        """Pause the shared owner clock. All owner consoles stay frozen until resume."""
        self.ensure_one()
        state = self.get_owner_bid_timer_state()
        if not state.get('enabled') or state.get('frozen') or state.get('held'):
            return state
        if not state.get('running'):
            return state
        remaining = max(0.0, float(state.get('remaining') or 0.0))
        if remaining <= 0:
            return state
        self.sudo().write({
            'owner_bid_held': True,
            'owner_bid_hold_remaining': remaining,
            # Stop the live deadline so owner polls cannot keep aging it to 3, 2, 1
            # and then resume from that leftover instead of the frozen 5.
            'owner_bid_deadline': False,
            'owner_bid_timer_epoch': time.time(),
        })
        return self.get_owner_bid_timer_state()

    def action_resume_owner_bid_timer(self):
        """Release a held clock so every owner can bid again from the remaining time."""
        self.ensure_one()
        state = self.get_owner_bid_timer_state()
        if not state.get('held'):
            return state
        remaining = max(0.0, float(self.owner_bid_hold_remaining or 0.0))
        vals = self._clear_owner_bid_hold_vals()
        if remaining > 0:
            vals['owner_bid_deadline'] = fields.Datetime.now() + timedelta(seconds=remaining)
        else:
            vals['owner_bid_deadline'] = False
        vals['owner_bid_timer_epoch'] = time.time()
        self.sudo().write(vals)
        return self.get_owner_bid_timer_state()

    @api.model
    def _owner_bid_window_closed(self, player):
        if not player or not hasattr(player, 'get_owner_bid_timer_state'):
            return False
        state = player.get_owner_bid_timer_state()
        return bool(state.get('frozen') or state.get('held'))

    @api.model
    def _owner_bid_lock_error(self, player):
        if not player or not hasattr(player, 'get_owner_bid_timer_state'):
            return False
        state = player.get_owner_bid_timer_state()
        if state.get('held'):
            return 'Timer is on hold. You can bid when it resumes.'
        if state.get('frozen'):
            return 'Time is up. Only the last bid stays open.'
        return False
