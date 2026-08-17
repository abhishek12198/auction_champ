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
#  Company  : AuctionChamp
#  Website  : www.auctionchamp.live
#  Email    : auctionchamp.live@gmail.com
#
#  © 2026 AuctionChamp. All Rights Reserved.
#
##############################################################################

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError
from ..models.auction_team_player import _get_default_player_photo


class AuctionPlayerRegisterWizard(models.TransientModel):
    _name = 'auction.player.register.wizard'
    _description = 'Register Player on Tournament'

    tournament_id = fields.Many2one(
        'auction.tournament', string='Tournament', required=True, readonly=True,
    )
    tournament_type = fields.Selection(
        related='tournament_id.tournament_type', readonly=True,
    )
    enable_jersey_section = fields.Boolean(
        related='tournament_id.enable_jersey_section', readonly=True,
    )
    sl_no = fields.Integer(string='Sl No')
    name = fields.Char(string='Name of the player', required=True)
    photo = fields.Binary(string='Photo', default=_get_default_player_photo)
    contact = fields.Char(string='Mobile Number')
    org_id = fields.Char(string='Org ID#')
    address = fields.Text(string='Address')
    role = fields.Char(string='Role')
    tier_id = fields.Many2one(
        'auction.player.tier', string='Tier',
        domain="[('tournament_id', '=', tournament_id)]",
    )
    current_team = fields.Char(string='Previous / Current Club')
    batting_style = fields.Char(string='Batting Style')
    bowling_style = fields.Char(string='Bowling Style')
    dominant_position_id = fields.Many2one(
        'auction.player.position', string='Playing Position',
    )
    secondary_position_ids = fields.Many2many(
        'auction.player.position',
        'apr_wiz_secondary_position_rel',
        'wizard_id', 'position_id',
        string='Secondary Position(s)',
    )
    preferred_foot = fields.Selection(
        [('left', 'Left'), ('right', 'Right'), ('both', 'Both')],
        string='Preferred Foot',
    )
    age = fields.Integer(string='Age')
    height = fields.Char(string='Height')
    weight = fields.Char(string='Weight')
    playing_style_ids = fields.Many2many(
        'auction.player.style',
        'apr_wiz_playing_style_rel',
        'wizard_id', 'style_id',
        string='Playing Style',
    )
    strength_ids = fields.Many2many(
        'auction.player.strength',
        'apr_wiz_strength_rel',
        'wizard_id', 'strength_id',
        string='Strengths',
    )
    work_rate = fields.Selection(
        [('low', 'Low'), ('medium', 'Medium'), ('high', 'High')],
        string='Work Rate',
    )
    blood_group = fields.Char(string='Blood Group')
    p_type = fields.Char(string='Type')
    jersy_name = fields.Char(string='Name on Jersey')
    jersy_number = fields.Char(string='Jersey Number')
    jersy_size = fields.Char(string='Jersey Size')
    amount_paid = fields.Boolean(string='Payment Received', default=True)

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        tid = res.get('tournament_id') or self.env.context.get('default_tournament_id')
        if tid:
            res['tournament_id'] = tid
        return res

    @api.onchange('tournament_id')
    def _onchange_tournament_id(self):
        if self.tournament_id:
            if self.tier_id and self.tier_id.tournament_id != self.tournament_id:
                self.tier_id = False
        else:
            self.tier_id = False

    def action_register(self):
        self.ensure_one()
        name = (self.name or '').strip()
        if not name:
            raise ValidationError(_('Enter the player name.'))
        if not self.tournament_id:
            raise ValidationError(_('Tournament is missing. Re-open this form from the tournament.'))
        Player = self.env['auction.team.player']
        sl_no = Player._get_next_tournament_sl_no(self.tournament_id.id)
        if self.tier_id and self.tier_id.tournament_id and self.tier_id.tournament_id != self.tournament_id:
            raise ValidationError(_('Choose a tier that belongs to this tournament.'))

        vals = {
            'tournament_id': self.tournament_id.id,
            'name': name,
            'sl_no': sl_no,
            'state': 'draft',
            'photo': self.photo or False,
            'contact': self.contact or False,
            'org_id': self.org_id or False,
            'address': self.address or False,
            'role': self.role or False,
            'tier_id': self.tier_id.id or False,
            'current_team': self.current_team or False,
            'blood_group': self.blood_group or False,
            'p_type': self.p_type or False,
        }
        if self.enable_jersey_section:
            vals.update({
                'jersy_name': self.jersy_name or False,
                'jersy_number': self.jersy_number or False,
                'jersy_size': self.jersy_size or False,
            })
        if self.tournament_type == 'football':
            vals.update({
                'dominant_position_id': self.dominant_position_id.id or False,
                'secondary_position_ids': [(6, 0, self.secondary_position_ids.ids)],
                'preferred_foot': self.preferred_foot or False,
                'age': self.age or 0,
                'height': self.height or False,
                'weight': self.weight or False,
                'playing_style_ids': [(6, 0, self.playing_style_ids.ids)],
                'strength_ids': [(6, 0, self.strength_ids.ids)],
                'work_rate': self.work_rate or False,
            })
        else:
            vals.update({
                'batting_style': self.batting_style or False,
                'bowling_style': self.bowling_style or False,
            })

        player = Player.create(vals)
        if self.amount_paid and not player.amount_paid:
            player.write({'amount_paid': True})

        msg = _(
            'Player %s with Sl No %s has been registered on this tournament successfully!'
        ) % (player.name, player.sl_no)
        if hasattr(self.env.user, 'notify_success'):
            self.env.user.notify_success(message=msg, title=_('Player registered'))
        return {'type': 'ir.actions.act_window_close'}
