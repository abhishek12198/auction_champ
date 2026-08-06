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
        """Keep Active Tournament ↔ Organizers M2M in sync for ir.rule domains.

        Heals two common mis-assignment cases:
        - Active set but missing from Organizers M2M
        - Organizers M2M set (e.g. via tournament form) but Active empty
          → list views / logos were empty while dashboards could still count
        """
        sync_ctx = dict(self.env.context, skip_tournament_sync=True)
        User = self.sudo()
        # Active → M2M
        for user in User.search([('tournament_id', '!=', False)]):
            if user.tournament_id not in user.tournament_ids:
                user.with_context(**sync_ctx).write({
                    'tournament_ids': [(4, user.tournament_id.id)],
                })
        # M2M → Active (when Active is empty)
        self.env.cr.execute("""
            SELECT DISTINCT user_id FROM auction_tournament_user_rel
        """)
        m2m_uids = [row[0] for row in self.env.cr.fetchall()]
        if m2m_uids:
            for user in User.browse(m2m_uids).exists():
                if not user.tournament_id and user.tournament_ids:
                    user.with_context(**sync_ctx).write({
                        'tournament_id': user.tournament_ids[:1].id,
                    })

    def _auction_sync_home_action(self):
        """Login landing: Auction Admin → Tournament(s); other auction users → Player Dashboard."""
        try:
            admin_action = self.env.ref('auction_module.action_auction_tournament')
            dash_action = self.env.ref('auction_module.action_player_dashboard_client')
        except ValueError:
            return
        sync_ctx = dict(
            self.env.context,
            skip_tournament_sync=True,
            skip_home_action_sync=True,
        )
        for user in self:
            if user.share:
                continue
            is_admin = user.has_group('auction_module.group_auction_group_admin')
            is_auction_user = (
                is_admin
                or user.has_group('auction_module.group_auction_group')
                or user.has_group('auction_module.group_auction_player_dashboard')
            )
            if not is_auction_user:
                continue
            target = admin_action if is_admin else dash_action
            if user.action_id != target:
                user.with_context(**sync_ctx).sudo().write({'action_id': target.id})

    @api.model
    def _auction_apply_home_actions_all(self):
        """Apply auction home actions to all internal users (install / upgrade)."""
        self.search([('share', '=', False)])._auction_sync_home_action()
        return True

    @api.model
    def _auction_reorder_root_menus(self):
        """Force root app menu order (XML sequence updates are unreliable on upgrade).

        1 Tournament(s)  2 Player Dashboard  3 Player Showcase
        4 Auctioneer Console  5 Pool Generator  6 Auction Settings
        """
        Menu = self.env['ir.ui.menu'].sudo()
        # (xml_id, sequence) — use gaps so other apps do not slip between
        ordered = [
            ('auction_module.menu_action_auction_tournament', 10),
            ('ac_saas_manager.menu_saas_tournament', 10),
            ('auction_module.menu_action_player_dashboard', 20),
            ('auction_module.menu_action_launch_auction_root', 30),
            ('auction_auctioneer.menu_auctioneer_console', 40),
            ('auction_module.menu_action_team_pool_wizard', 50),
            ('auction_module.menu_action_auction_root', 60),
            ('auction_module.menu_action_payment_marker', 70),
        ]
        for xmlid, sequence in ordered:
            menu = self.env.ref(xmlid, raise_if_not_found=False)
            if menu and menu.exists() and menu.sequence != sequence:
                menu.write({
                    'sequence': sequence,
                    'parent_id': False,
                })
        return True

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
        if (
            not self.env.context.get('skip_home_action_sync')
            and 'groups_id' in vals
        ):
            self._auction_sync_home_action()
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
        if not self.env.context.get('skip_home_action_sync'):
            users._auction_sync_home_action()
        return users
