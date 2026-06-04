# -*- coding: utf-8 -*-
import secrets
import string
import logging

from odoo import models, fields, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


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

    @staticmethod
    def _random_password(length=12):
        chars = string.ascii_letters + string.digits + '!@#$%'
        return ''.join(secrets.choice(chars) for _ in range(length))

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
        for team in self:
            password = self._random_password()

            if team.owner_user_id:
                # User already exists — reset password and re-assert group + team link
                team.owner_user_id.sudo().write({
                    'password': password,
                    'auction_team_id': team.id,
                    'groups_id': [(4, owner_group.id), (4, internal_group.id)],
                })
                team.write({'owner_password': password})
                results.append(_('"%s": password reset (login: %s)') % (team.name, team.owner_user_id.login))
            else:
                # Build a unique login: team_name lowercased, spaces → underscores
                base_login = team.name.lower().replace(' ', '_')
                login = base_login
                counter = 1
                while self.env['res.users'].sudo().search([('login', '=', login)], limit=1):
                    login = '%s_%d' % (base_login, counter)
                    counter += 1

                full_name = '%s %s' % (team.manager, team.name)
                user_vals = {
                    'name': full_name,
                    'login': login,
                    'password': password,
                    'auction_team_id': team.id,
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
