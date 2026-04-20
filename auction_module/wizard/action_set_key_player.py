# -*- coding: utf-8 -*-
import base64

from odoo import api, models, fields, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools.image import image_data_uri

import werkzeug
import werkzeug.exceptions

class SetKeyPlayer(models.TransientModel):
    _name = 'auction.set.key.player'


    team_id = fields.Many2one('auction.team', 'Team')
    team_selection = fields.Selection(selection='_get_team_selection', string='Select Team')
    player_id = fields.Many2one('auction.team.player', 'Player')
    player_photo  = fields.Binary()
    team_logo = fields.Binary()

    def _get_team_selection(self):
        teams = self.env['auction.team'].search([], order='name asc')
        return [(str(t.id), t.name) for t in teams]

    @api.model
    def default_get(self, fields):
        defaults = super(SetKeyPlayer, self).default_get(fields)
        if self.env.context.get('active_id', False):
            player = self.env['auction.team.player'].browse(self.env.context.get('active_id', False))
            defaults.update({'player_photo': player.photo,'player_id': self.env.context.get('active_id', False)})
        return defaults

    @api.onchange('team_selection')
    def onchange_team_selection(self):
        if self.team_selection:
            self.team_id = int(self.team_selection)
            self.team_logo = self.team_id.logo
        else:
            self.team_id = False
            self.team_logo = False

    @api.onchange('team_id')
    def onchange_team(self):
        if self.team_id:
            self.team_logo = self.team_id.logo
        else:
            self.team_logo = False

    def button_set_keyplayer(self):
        player_id = self.env.context.get('active_id', False)
        if player_id:
            player = self.player_id
            team = self.team_id
            # Fallback: if onchange value was flushed during form-save,
            # reconstruct team from team_selection (always persisted as a simple Selection)
            if not team and self.team_selection:
                team = self.env['auction.team'].browse(int(self.team_selection))

            if not team:
                raise UserError('Please select a team before confirming.')
            # Find the icon tier (only one should exist due to constraint)
            icon_tier = self.env['auction.player.tier'].search([('is_an_icon_tier', '=', True)], limit=1)
            if not icon_tier:
                raise UserError(
                    'No Icon Tier is configured. Please mark one tier as "Icon Tier" in Player Tiers before promoting a player.'
                )

            player.write({
                'icon_player': True,
                'state': 'sold',
                'assigned_team_id': team.id,
                'previous_tier_id': player.tier_id.id if player.tier_id else False,
                'tier_id': icon_tier.id,
            })

            team.key_player_ids = [(4, player.id)]

            message = player.name + ' set as Icon Player for team ' + team.name + ' and moved to "%s" tier successfully!' % icon_tier.name
            self.env.user.notify_success(message)


