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

from odoo import api, models, fields, _
from odoo.exceptions import AccessError, UserError


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
        help='The tournament this user is currently working in. '
             'Auction Users with several Organizer Tournaments switch this from the navbar. '
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
        """Do NOT set a permanent Home Action (res.users.action_id).

        A forced Home Action hijacks sidebar/menu clicks when the URL has only
        menu_id or a missing action_id (known Odoo behavior) — users stay on
        Tournament / Player Dashboard instead of opening the clicked app.

        Landing is handled by root-menu order instead:
          admin → Tournament(s) first; others → Player Dashboard first
        (openFirstApp on login). Clear any previously forced auction home actions.
        """
        try:
            admin_action = self.env.ref('auction_module.action_auction_tournament')
            dash_action = self.env.ref('auction_module.action_player_dashboard_client')
        except ValueError:
            return
        forced_ids = {admin_action.id, dash_action.id}
        sync_ctx = dict(
            self.env.context,
            skip_tournament_sync=True,
            skip_home_action_sync=True,
        )
        for user in self:
            if user.share:
                continue
            if user.action_id and user.action_id.id in forced_ids:
                user.with_context(**sync_ctx).sudo().write({'action_id': False})

    @api.model
    def _auction_apply_home_actions_all(self):
        """Clear forced auction Home Actions on all internal users."""
        self.search([('share', '=', False)])._auction_sync_home_action()
        return True

    def _register_hook(self):
        super()._register_hook()
        # Clear forced Home Actions on restart (no -u required) so menu clicks work.
        try:
            self.search([('share', '=', False)])._auction_sync_home_action()
        except Exception:
            # Avoid blocking registry load if refs are missing mid-upgrade
            pass

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

    def _auction_is_admin_user(self):
        self.ensure_one()
        return self.has_group('auction_module.group_auction_group_admin')

    def _auction_is_switchable_user(self):
        """Navbar switcher: Auction User and Administrator."""
        self.ensure_one()
        return (
            self._auction_is_admin_user()
            or self.has_group('auction_module.group_auction_group')
        )

    def _auction_switchable_tournaments(self):
        """Tournaments this login may enable from the navbar.

        Returns a browse recordset (ids only) so callers can ``read()`` a
        narrow field list instead of prefetching logos / snapshots.
        """
        self.ensure_one()
        Tournament = self.env['auction.tournament'].sudo()
        if self._auction_is_admin_user():
            return Tournament.search([('active', '=', True)], order='name asc, id asc')
        user = self.sudo()
        ids = list(user.tournament_ids.ids)
        if user.tournament_id and user.tournament_id.id not in ids:
            ids.append(user.tournament_id.id)
        return Tournament.browse(ids)

    def _auction_systray_logo_ids(self, tournament_ids):
        """Ids that have a logo, without reading Binary payloads."""
        if not tournament_ids:
            return set()
        return set(self.env['auction.tournament'].sudo().search([
            ('id', 'in', list(tournament_ids)),
            ('logo', '!=', False),
        ]).ids)

    def _auction_systray_rule_ids(self, tournament_ids):
        """Ids that have at least one auction-rule row."""
        if not tournament_ids:
            return set()
        groups = self.env['auction.auction'].sudo().read_group(
            [('tournament_id', 'in', list(tournament_ids))],
            ['tournament_id'],
            ['tournament_id'],
        )
        return {
            g['tournament_id'][0]
            for g in groups
            if g.get('tournament_id')
        }

    def _auction_systray_items(self, tournaments, active_id):
        """Navbar rows: name / slug / logo URL only — no binary or URL computes."""
        rows = tournaments.sudo().read(['id', 'name', 'slug', 'active'], load=False)
        rows.sort(key=lambda r: (
            not r.get('active'),
            (r.get('name') or '').lower(),
            r['id'],
        ))
        ids = [r['id'] for r in rows]
        logo_ids = self._auction_systray_logo_ids(ids)
        rule_ids = self._auction_systray_rule_ids(ids)
        db_name = self.env.cr.dbname
        items = []
        for row in rows:
            tid = row['id']
            slug = row.get('slug') or ''
            rules_ready = tid in rule_ids
            projector_url = ''
            if rules_ready and slug:
                projector_url = '/%s/auction/projector/%s/' % (db_name, slug)
            live_board_url = ''
            if slug:
                live_board_url = '/%s/%s/auction/live-board' % (db_name, slug)
            items.append({
                'id': tid,
                'name': row.get('name') or _('Tournament'),
                'active': bool(active_id and tid == active_id),
                'logo': (
                    '/web/image/auction.tournament/%s/logo' % tid
                    if tid in logo_ids else ''
                ),
                'has_auction_rules': rules_ready,
                'projector_url': projector_url,
                'live_board_url': live_board_url or '/auction/my/live-board',
            })
        return items

    def get_working_tournament(self):
        """Tournament used for menus, creates, and the navbar badge."""
        self.ensure_one()
        allowed = self._auction_switchable_tournaments()
        if self.tournament_id and self.tournament_id.exists():
            if self.tournament_id in allowed:
                return self.tournament_id
            if self._auction_is_admin_user():
                return self.tournament_id
        return allowed[:1]

    def get_working_tournament_id(self):
        tournament = self.get_working_tournament()
        return tournament.id if tournament else False

    def _auction_systray_item(self, tournament, active_id):
        items = self._auction_systray_items(tournament, active_id)
        return items[0] if items else {}

    @api.model
    def get_systray_tournaments(self):
        """Payload for the navbar tournament badge / Auction User switcher."""
        user = self.env.user
        tournaments = user._auction_switchable_tournaments()
        working = user.get_working_tournament()
        active_id = working.id if working else False
        items = user._auction_systray_items(tournaments, active_id)
        current = next((i for i in items if i['active']), items[0] if items else None)
        return {
            'tournaments': items,
            'current': current,
            'can_switch': bool(user._auction_is_switchable_user() and len(items) > 1),
        }

    def set_active_tournament(self, tournament_id):
        """Set Active Tournament for menus and creates (navbar switcher)."""
        self.ensure_one()
        if self.env.user != self and not self.env.su:
            raise AccessError(_('You can only switch your own active tournament.'))
        if not self._auction_is_switchable_user():
            raise AccessError(_('You cannot switch tournament from the navbar.'))
        tournament_id = int(tournament_id or 0)
        if not tournament_id:
            raise UserError(_('Select a tournament to enable.'))

        allowed = self._auction_switchable_tournaments()
        tournament = allowed.filtered(lambda t: t.id == tournament_id)
        if not tournament and self._auction_is_admin_user():
            tournament = self.env['auction.tournament'].sudo().browse(tournament_id).exists()
        if not tournament:
            raise AccessError(_(
                'You cannot enable that tournament — it is not available for your login.'
            ))

        vals = {}
        if self.tournament_id.id != tournament.id:
            vals['tournament_id'] = tournament.id
        if (
            not self._auction_is_admin_user()
            and tournament.id not in self.tournament_ids.ids
        ):
            vals['tournament_ids'] = [(4, tournament.id)]
        if vals:
            self.sudo().with_context(
                skip_tournament_sync=True,
                mail_notrack=True,
                tracking_disable=True,
            ).write(vals)
        return self.get_systray_tournaments()
