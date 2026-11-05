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

import re
import secrets
import string
import logging

from odoo import models, fields, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

_OWNER_PASSWORD_UPPER = ''.join(ch for ch in string.ascii_uppercase if ch not in 'OI')
_OWNER_PASSWORD_LOWER = ''.join(ch for ch in string.ascii_lowercase if ch not in 'lo')
_OWNER_PASSWORD_DIGITS = '23456789'


def _owner_random_password(length=8):
    """8 characters from upper, lower, and digits. No symbols or look-alikes."""
    length = max(int(length or 8), 3)
    alphabet = _OWNER_PASSWORD_UPPER + _OWNER_PASSWORD_LOWER + _OWNER_PASSWORD_DIGITS
    chars = [
        secrets.choice(_OWNER_PASSWORD_UPPER),
        secrets.choice(_OWNER_PASSWORD_LOWER),
        secrets.choice(_OWNER_PASSWORD_DIGITS),
    ]
    chars.extend(secrets.choice(alphabet) for _ in range(length - 3))
    for index in range(len(chars) - 1, 0, -1):
        swap = secrets.randbelow(index + 1)
        chars[index], chars[swap] = chars[swap], chars[index]
    return ''.join(chars)


def _owner_team_key(name):
    """Short key from a team name. Several words use initials; one word uses 4 letters."""
    parts = re.findall(r'[a-z0-9]+', (name or '').lower())
    if not parts:
        return 'tm'
    if len(parts) == 1:
        return parts[0][:4]
    return ''.join(part[0] for part in parts)[:4]


def _owner_pin_from_digits(digits, other_digits):
    """Shortest tail of this tournament code that no other tournament ends with.

    Starts at 4 digits and grows only when another tournament shares that ending.
    """
    digits = digits or ''
    start = 4 if len(digits) >= 4 else len(digits)
    for size in range(start, len(digits) + 1):
        tail = digits[-size:]
        if not any(other.endswith(tail) for other in other_digits):
            return tail
    return digits


def _owner_login_stem(name, sibling_pairs, team_id, pin):
    """``key_pin``, or ``key2_pin`` when an earlier team in the tournament shares the key."""
    key = _owner_team_key(name)
    same = [pair for pair in sibling_pairs if _owner_team_key(pair[0]) == key]
    same.sort(key=lambda pair: ((pair[0] or '').lower(), pair[1] or 0))
    index = 0
    for position, pair in enumerate(same):
        if pair[1] == team_id:
            index = position
            break
    suffix = '' if index == 0 else str(index + 1)
    return '%s%s_%s' % (key, suffix, pin)


class AuctionTeamOwnerUser(models.Model):
    _inherit = 'auction.team'

    owner_user_id = fields.Many2one(
        'res.users',
        string='Owner Login',
        ondelete='set null',
        readonly=True,
        copy=False,
        help='Auto-generated owner user for this team.',
    )
    # Restricted to admin at ORM level so team owners cannot read their own password via RPC
    owner_password = fields.Char(
        string='Owner Password',
        readonly=True,
        copy=False,
        groups='auction_module.group_auction_group_admin',
        help='Plain-text password stored for admin reference. Share this with the team owner.',
    )

    owner_wizard_created = fields.Boolean(
        string='Owner Login Created by Wizard',
        copy=False,
        readonly=True,
        help='Set when the owner user was created from Tournament Settings → '
             'Create Owner Users. Enables the Excel export of owner logins.',
    )

    @staticmethod
    def _random_password(length=8):
        return _owner_random_password(length)

    def _owner_digit_rows(self):
        """(tournament id, digits) for every tournament that has a code."""
        tournaments = self.env['auction.tournament'].sudo().with_context(
            active_test=False,
        ).search([])
        rows = []
        for tournament in tournaments:
            digits = re.sub(r'\D', '', tournament.tournament_code or '')
            if digits:
                rows.append((tournament.id, digits))
        return rows

    def _owner_login_base(self, team, digit_rows=None):
        """Login stem: team key + same-tournament number + tournament pin.

        ``mi_3237`` is Mumbai Indians in the tournament whose code ends in 3237.
        A second team in that tournament with the same key becomes ``mi2_3237``.
        The same team name in another tournament gets that tournament's pin.
        """
        tournament = team.tournament_id
        digits = re.sub(r'\D', '', (tournament.tournament_code or '') if tournament else '')
        if not digits:
            raise UserError(
                _('Team "%s" has no tournament unique code. '
                  'Set the tournament code before creating the owner user.')
                % (team.name or '')
            )
        if digit_rows is None:
            digit_rows = self._owner_digit_rows()
        others = [other for tid, other in digit_rows if tid != tournament.id]
        pin = _owner_pin_from_digits(digits, others)
        siblings = tournament.sudo().with_context(
            auction_skip_tournament_security=True,
        )._tournament_team_records()
        pairs = [(sibling.name, sibling.id) for sibling in siblings]
        if team.id not in {pair[1] for pair in pairs}:
            pairs.append((team.name, team.id))
        return _owner_login_stem(team.name, pairs, team.id, pin)

    def action_create_owner_user(self):
        owner_group = self.env.ref('auction_owner.group_auction_owner')
        internal_group = self.env.ref('base.group_user')

        # Pre-validate all selected teams before any write
        missing_manager = self.filtered(lambda t: not t.manager)
        if missing_manager:
            raise UserError(
                _('The following teams have no Owner set — please fill the Owner field first:\n%s')
                % ', '.join(missing_manager.mapped('name'))
            )

        results = []
        digit_rows = self._owner_digit_rows()
        for team in self:
            password = self._random_password()

            if team.owner_user_id:
                # User already exists — reset password and re-assert group + team link
                team.owner_user_id.sudo().write({
                    'password': password,
                    'auction_team_id': team.id,
                    'tournament_id': team.tournament_id.id if team.tournament_id else False,
                    'tournament_ids': [(4, team.tournament_id.id)] if team.tournament_id else [],
                    'groups_id': [(4, owner_group.id), (4, internal_group.id)],
                })
                team.write({'owner_password': password})
                results.append(_('"%s": password reset (login: %s)') % (team.name, team.owner_user_id.login))
            else:
                # Login: team key + tournament pin (e.g. mi_3237, bc2_3809).
                base_login = self._owner_login_base(team, digit_rows)
                login = base_login
                counter = 2
                while self.env['res.users'].sudo().with_context(active_test=False).search(
                        [('login', '=', login)], limit=1):
                    login = '%s_%d' % (base_login, counter)
                    counter += 1

                full_name = '%s %s' % (team.manager, team.name)
                user_vals = {
                    'name': full_name,
                    'login': login,
                    'password': password,
                    'auction_team_id': team.id,
                    'tournament_id': team.tournament_id.id if team.tournament_id else False,
                    'tournament_ids': [(4, team.tournament_id.id)] if team.tournament_id else [],
                }
                if team.logo:
                    user_vals['image_1920'] = team.logo

                user = self.env['res.users'].sudo().create(user_vals)
                # Ensure both internal-user and owner-console groups are present
                user.sudo().write({
                    'groups_id': [(4, internal_group.id), (4, owner_group.id)],
                })
                team.write({
                    'owner_user_id': user.id,
                    'owner_password': password,
                })
                results.append(_('"%s": user created (login: %s)') % (team.name, login))

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Owner Users'),
                'message': ',  '.join(results),
                'type': 'success',
                'sticky': False,
            },
        }

    # ── Remove / recreate support (Tournament Settings → Remove Owner Users) ──

    def _owner_user_remove(self, mode='archive'):
        """Detach the owner user from the team and optionally archive / delete it.

        ``unlink``  — detach from the team and drop the Owner Console access;
                      the user account itself is kept.
        ``archive`` — soft delete: detach, archive the user and free its login,
                      so re-creating the owner user gives the same login again.
        ``delete``  — detach and delete the user permanently (falls back to
                      archive when the user is referenced elsewhere).

        Returns a dict of counters for the confirmation message.
        """
        owner_group = self.env.ref('auction_owner.group_auction_owner')
        done = {'unlink': 0, 'archive': 0, 'delete': 0, 'archived_instead': 0}
        for team in self.sudo().with_context(auction_skip_tournament_security=True):
            user = team.owner_user_id
            team.write({
                'owner_user_id': False,
                'owner_password': False,
                'owner_wizard_created': False,
            })
            if not user:
                continue
            user = user.sudo()
            user.write({'auction_team_id': False, 'groups_id': [(3, owner_group.id)]})
            if mode == 'unlink':
                done['unlink'] += 1
                continue
            if mode == 'delete':
                try:
                    with self.env.cr.savepoint():
                        user.unlink()
                    done['delete'] += 1
                    continue
                except Exception:
                    _logger.info('Owner user %s kept (archived): still referenced', user.login)
                    done['archived_instead'] += 1
            # archive / soft delete — free the login for re-creation
            user.write({
                'login': '%s__archived_%d' % (user.login.split('__archived_')[0], user.id),
                'active': False,
            })
            if mode != 'delete':
                done['archive'] += 1
        return done
