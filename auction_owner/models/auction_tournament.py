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
    owner_bid_timer_seconds = fields.Integer(
        string='Owner Bid Window (seconds)',
        default=0,
        help='Seconds the other owners have to raise after someone bids. '
             '0 turns the window off. Each new bid gives the other owners this full time again. '
             'If nobody raises in time, bidding closes for every owner except the one who bid last.',
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

    # ── Owner users: Tournament Settings → Auction Team and Rules ─────────

    _OWNER_USER_SETTINGS_ACTIONS = {
        'action_user_settings_create_owner_users',
        'action_user_settings_remove_owner_users',
        'action_user_settings_export_owner_users',
    }

    def _owner_users_check_access(self):
        """Admins, organizers and the tournament's working users only."""
        self.ensure_one()
        user = self.env.user
        if user.has_group('auction_module.group_auction_group_admin') or user.has_group('base.group_system'):
            return True
        if user.has_group('auction_owner.group_auction_owner'):
            raise UserError(_('Owner users cannot manage owner logins.'))
        if user == self.organizer_uid or user in self.organizer_uids:
            return True
        getter = getattr(user, 'get_working_tournament', None)
        if callable(getter) and getter() == self:
            return True
        raise UserError(_('You are not allowed to manage owner users for this tournament.'))

    def _owner_wizard_teams(self):
        self.ensure_one()
        return self._tournament_team_records()

    def _open_owner_user_wizard(self, mode):
        self.ensure_one()
        self._owner_users_check_access()
        teams = self._owner_wizard_teams()
        if mode == 'remove':
            teams = teams.filtered('owner_user_id')
            if not teams:
                raise UserError(_('No team in this tournament has an owner user yet.'))
        elif not teams:
            raise UserError(_('Add teams to this tournament first.'))
        lines = []
        for team in teams.sorted(lambda t: (t.name or '').lower()):
            if mode == 'create':
                # Pre-select teams that still need a login (never silently reset a password).
                selected = bool(team.manager) and not team.owner_user_id
            else:
                selected = False
            lines.append((0, 0, {'team_id': team.id, 'selected': selected}))
        wizard = self.env['auction.owner.user.wizard'].create({
            'mode': mode,
            'tournament_id': self.id,
            'line_ids': lines,
        })
        return wizard._reopen()

    def action_user_settings_create_owner_users(self):
        return self._open_owner_user_wizard('create')

    def action_user_settings_remove_owner_users(self):
        return self._open_owner_user_wizard('remove')

    def action_user_settings_export_owner_users(self):
        self.ensure_one()
        self._owner_users_check_access()
        return {
            'type': 'ir.actions.act_url',
            'url': '/auction_owner/owner_users/export/%d' % self.id,
            'target': 'self',
        }

    def call_user_settings_action(self, action_name):
        if action_name in self._OWNER_USER_SETTINGS_ACTIONS:
            self.ensure_one()
            rec = self.with_context(
                default_tournament_id=self.id,
                active_model='auction.tournament',
                active_id=self.id,
                active_ids=[self.id],
            )
            action = getattr(rec, action_name)()
            if isinstance(action, dict):
                ctx = dict(action.get('context') or {})
                ctx['from_user_settings'] = True
                action['context'] = ctx
            return action
        return super().call_user_settings_action(action_name)

    @api.model
    def get_user_settings_payload(self, tournament_id=None):
        payload = super().get_user_settings_payload(tournament_id=tournament_id)
        rec = self.browse((payload or {}).get('id') or 0).exists()
        if rec:
            teams = rec._tournament_team_records().sudo()
            payload['owner_users_enabled'] = True
            payload['owner_users_linked'] = len(teams.filtered('owner_user_id'))
            payload['owner_export_ready'] = bool(
                teams.filtered(lambda t: t.owner_user_id and t.owner_wizard_created)
            )
        return payload
