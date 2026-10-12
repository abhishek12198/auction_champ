# -*- coding: utf-8 -*-
##############################################################################
#
#  AuctionChamp - Professional Sports Auction Management Platform
#  Copyright (c) 2026 AuctionChamp. All Rights Reserved.
#  CONFIDENTIAL & PROPRIETARY — see the licence header of the other modules.
#
##############################################################################

import logging

from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

CREATED_MESSAGE = 'Owner Users for the Selected users has been created'


def _toast(title, message, kind='success'):
    """Success toast that also closes the wizard dialog."""
    return {
        'type': 'ir.actions.client',
        'tag': 'display_notification',
        'params': {
            'title': title,
            'message': message,
            'type': kind,
            'sticky': False,
            'className': 'ac_owner_toast ac_owner_toast_%s' % kind,
            'next': {'type': 'ir.actions.act_window_close'},
        },
    }


class AuctionOwnerUserWizard(models.TransientModel):
    _name = 'auction.owner.user.wizard'
    _description = 'Create / Remove Owner Users'

    mode = fields.Selection(
        [('create', 'Create'), ('remove', 'Remove')],
        required=True, default='create', readonly=True,
    )
    tournament_id = fields.Many2one('auction.tournament', required=True, readonly=True)
    line_ids = fields.One2many('auction.owner.user.wizard.line', 'wizard_id', string='Teams')
    remove_mode = fields.Selection(
        [
            ('archive', 'Soft delete (archive) — keeps history, the login can be re-created'),
            ('unlink', 'Unlink from team only — the user account is kept'),
            ('delete', 'Delete permanently'),
        ],
        string='What should happen to the users?', default='archive',
    )
    selected_count = fields.Integer(compute='_compute_selected_count')

    @api.depends('line_ids.selected')
    def _compute_selected_count(self):
        for wiz in self:
            wiz.selected_count = len(wiz.line_ids.filtered('selected'))

    # ── helpers ────────────────────────────────────────────────────────────

    def _reopen(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self._wizard_title(self.mode),
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'views': [[False, 'form']],
            'target': 'new',
        }

    @api.model
    def _wizard_title(self, mode):
        return _('Create Owner Users') if mode == 'create' else _('Remove Owner Users')

    def action_select_all(self):
        self.mapped('line_ids').write({'selected': True})
        return self._reopen()

    def action_unselect_all(self):
        self.mapped('line_ids').write({'selected': False})
        return self._reopen()

    def _selected_teams(self):
        self.ensure_one()
        teams = self.line_ids.filtered('selected').mapped('team_id')
        if not teams:
            raise UserError(_('Please select at least one team to continue.'))
        return teams

    # ── actions ────────────────────────────────────────────────────────────

    def action_confirm(self):
        self.ensure_one()
        self.tournament_id._owner_users_check_access()
        teams = self._selected_teams().sudo().with_context(
            auction_skip_tournament_security=True,
        )
        if self.mode == 'create':
            # Same convention as Team Master → "Create Owner User".
            teams.action_create_owner_user()
            teams.write({'owner_wizard_created': True})
            return _toast(_('Owner Users Created'), _(CREATED_MESSAGE))
        done = teams._owner_user_remove(self.remove_mode)
        parts = []
        if done['unlink']:
            parts.append(_('%d unlinked') % done['unlink'])
        if done['archive'] or done['archived_instead']:
            parts.append(_('%d soft deleted') % (done['archive'] + done['archived_instead']))
        if done['delete']:
            parts.append(_('%d deleted') % done['delete'])
        message = _('Owner users for the selected teams have been removed (%s). '
                    'You can create them again from Create Owner Users.') % ', '.join(parts)
        return _toast(_('Owner Users Removed'), message, 'warning')


class AuctionOwnerUserWizardLine(models.TransientModel):
    _name = 'auction.owner.user.wizard.line'
    _description = 'Create / Remove Owner Users — team line'
    _order = 'team_name, id'

    wizard_id = fields.Many2one('auction.owner.user.wizard', required=True, ondelete='cascade')
    team_id = fields.Many2one('auction.team', required=True, readonly=True)
    selected = fields.Boolean(string='Select', default=False)
    team_name = fields.Char(related='team_id.name', readonly=True, store=True)
    owner_name = fields.Char(related='team_id.manager', string='Owner', readonly=True)
    owner_login = fields.Char(compute='_compute_login', string='Username')
    status = fields.Char(compute='_compute_status')

    @api.depends('team_id.owner_user_id')
    def _compute_login(self):
        for line in self:
            line.owner_login = line.team_id.sudo().owner_user_id.login or ''

    @api.depends('team_id.owner_user_id', 'team_id.manager', 'wizard_id.mode')
    def _compute_status(self):
        for line in self:
            team = line.team_id.sudo()
            if line.wizard_id.mode == 'remove':
                line.status = _('Linked user') if team.owner_user_id else ''
            elif not team.manager:
                line.status = _('Owner name missing')
            elif team.owner_user_id:
                line.status = _('User exists — password will be reset')
            else:
                line.status = _('Ready to create')
