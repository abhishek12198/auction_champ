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
from odoo.exceptions import ValidationError


_EXTRA_INPUT_TYPES = [
    ('text', 'Text'),
    ('dropdown', 'Dropdown'),
    ('radio', 'Radio'),
    ('badge', 'Selection Badge'),
    ('multi', 'Multi-select checkbox'),
    ('checkbox', 'Checkbox'),
]
_EXTRA_TYPES_WITH_OPTIONS = frozenset(('dropdown', 'radio', 'badge', 'multi'))
_MAX_DISPLAY_EXTRA_ATTRS = 3


class AuctionPlayerPosition(models.Model):
    _name = 'auction.player.position'
    _description = 'Football Playing Position'
    _order = 'sequence, id'

    name = fields.Char(string='Position', required=True)
    code = fields.Char(string='Code', help='Short code, e.g. GK, CB, ST.')
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    sport = fields.Selection(
        [('football', 'Football'), ('badminton', 'Badminton')],
        string='Sport', default='football', required=True, index=True,
    )


class AuctionPlayerStyle(models.Model):
    _name = 'auction.player.style'
    _description = 'Player Playing Style'
    _order = 'sequence, id'

    name = fields.Char(string='Playing Style', required=True)
    icon = fields.Char(string='Icon', help='Emoji/icon shown on the chip.')
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    sport = fields.Selection(
        [('football', 'Football'), ('badminton', 'Badminton')],
        string='Sport', default='football', required=True, index=True,
    )


class AuctionPlayerStrength(models.Model):
    _name = 'auction.player.strength'
    _description = 'Player Strength'
    _order = 'sequence, id'

    name = fields.Char(string='Strength', required=True)
    icon = fields.Char(string='Icon', help='Emoji/icon shown on the chip.')
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    sport = fields.Selection(
        [('football', 'Football'), ('badminton', 'Badminton')],
        string='Sport', default='football', required=True, index=True,
    )


class AuctionPlayerOtherAttribute(models.Model):
    _name = 'auction.player.other.attribute'
    _inherit = ['auction.tournament.security.mixin']
    _description = 'Player Additional Attribute'
    _order = 'sequence, id'

    player_id = fields.Many2one(
        'auction.team.player', string='Player', required=True, ondelete='cascade', index=True)
    definition_id = fields.Many2one(
        'auction.tournament.attribute.label',
        string='Attribute',
        ondelete='cascade',
        index=True,
    )
    label = fields.Char(string='Attribute', required=True)
    value = fields.Char(string='Value')
    sequence = fields.Integer(default=10)
    input_type = fields.Selection(
        related='definition_id.input_type', readonly=True,
    )
    show_on_display = fields.Boolean(
        related='definition_id.show_on_display', readonly=True,
    )

    @api.onchange('definition_id')
    def _onchange_definition_id(self):
        if self.definition_id:
            self.label = self.definition_id.label
            self.sequence = self.definition_id.sequence


class AuctionTournamentAttributeLabel(models.Model):
    _name = 'auction.tournament.attribute.label'
    _inherit = ['auction.tournament.security.mixin']
    _description = 'Tournament Additional Attribute'
    _order = 'sequence, id'

    tournament_id = fields.Many2one(
        'auction.tournament', string='Tournament', required=True, ondelete='cascade', index=True)
    label = fields.Char(
        string='Attribute', required=True,
        help='Question shown on player registration and stored on the player.',
    )
    input_type = fields.Selection(
        _EXTRA_INPUT_TYPES,
        string='Input Type',
        default='text',
        required=True,
    )
    option_text = fields.Text(
        string='Attribute Values',
        help='Comma-separated options for Dropdown, Radio, Selection Badge '
             'and Multi-select checkbox. Example: Fast, Medium, Slow',
    )
    required = fields.Boolean(string='Mandatory', default=False)
    show_on_display = fields.Boolean(
        string='Show on player card / showcase',
        default=False,
        help='Show this answer on the player card, projector and live URL. '
             'At most 3 attributes can be shown so the current layout stays intact.',
    )
    sequence = fields.Integer(default=10)
    answer_ids = fields.One2many(
        'auction.player.other.attribute', 'definition_id', string='Answers',
    )

    def option_list(self):
        self.ensure_one()
        options = []
        seen = set()
        raw = (self.option_text or '').replace('\r\n', '\n').replace('\r', '\n')
        for chunk in raw.replace('\n', ',').split(','):
            opt = chunk.strip()
            if not opt or opt in seen:
                continue
            seen.add(opt)
            options.append(opt)
        return options

    def posted_value(self, post):
        """Read this question's submitted value from a registration POST."""
        self.ensure_one()
        key = 'extra_attr_%s' % self.id
        getter = post.getlist if hasattr(post, 'getlist') else None
        if self.input_type == 'checkbox':
            raw = (post.get(key) or '').strip()
            return 'Yes' if raw else ''
        if self.input_type == 'multi':
            raw = getter(key) if getter else post.get(key)
            if isinstance(raw, str):
                raw = [part.strip() for part in raw.split(',') if part.strip()]
            allowed = set(self.option_list())
            values = [val for val in (raw or []) if val in allowed]
            return ', '.join(values)
        value = (post.get(key) or '').strip()
        if self.input_type in _EXTRA_TYPES_WITH_OPTIONS:
            return value if value in self.option_list() else ''
        return value

    def validate_posted_value(self, value):
        self.ensure_one()
        if self.required and not (value or '').strip():
            if self.input_type == 'checkbox':
                return _('%s must be checked.') % (self.label or 'This field')
            return _('%s is required.') % (self.label or 'This field')
        return None

    @api.constrains('input_type', 'option_text')
    def _check_option_text(self):
        for rec in self:
            if rec.input_type in _EXTRA_TYPES_WITH_OPTIONS and not rec.option_list():
                raise ValidationError(_(
                    'Enter possible values (comma-separated) for "%s".'
                ) % (rec.label or _('this attribute')))

    @api.constrains('show_on_display', 'tournament_id')
    def _check_max_display_attributes(self):
        for tournament in self.mapped('tournament_id'):
            shown = self.search_count([
                ('tournament_id', '=', tournament.id),
                ('show_on_display', '=', True),
            ])
            if shown > _MAX_DISPLAY_EXTRA_ATTRS:
                raise ValidationError(_(
                    'You can show at most %s additional attributes on the player card, '
                    'projector and live URL so the current design is not disturbed.'
                ) % _MAX_DISPLAY_EXTRA_ATTRS)

    def create(self, vals_list):
        records = super().create(vals_list)
        records._sync_tournament_players()
        return records

    def write(self, vals):
        res = super().write(vals)
        if any(key in vals for key in ('label', 'sequence', 'show_on_display')):
            self._sync_tournament_players()
        return res

    def _sync_tournament_players(self):
        tournaments = self.mapped('tournament_id')
        if not tournaments:
            return
        players = self.env['auction.team.player'].search([
            ('tournament_id', 'in', tournaments.ids),
        ])
        if players:
            players._sync_other_attributes_from_tournament()
