# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import UserError


class MigrateTierLine(models.TransientModel):
    _name = 'auction.migrate.tier.line'
    _description = 'Migrate Tier – Player Line'

    wizard_id = fields.Many2one('auction.migrate.tier', ondelete='cascade')
    player_id = fields.Many2one('auction.team.player', string='Player', readonly=True)
    sl_no = fields.Integer(related='player_id.sl_no', string='#', readonly=True, store=True)
    role = fields.Char(related='player_id.role', string='Role', readonly=True)
    batting_style = fields.Char(related='player_id.batting_style', string='Batting', readonly=True)
    bowling_style = fields.Char(related='player_id.bowling_style', string='Bowling', readonly=True)
    state = fields.Selection(related='player_id.state', string='Status', readonly=True)
    migrate = fields.Boolean(string='Migrate', default=True)


class MigrateTier(models.TransientModel):
    _name = 'auction.migrate.tier'
    _description = 'Migrate Players to Another Tier'

    tier_id = fields.Many2one('auction.player.tier', string='Current Tier', readonly=True)
    target_tier_id = fields.Many2one(
        'auction.player.tier', string='Target Tier',
        domain="[('id', '!=', tier_id)]",
    )
    player_line_ids = fields.One2many('auction.migrate.tier.line', 'wizard_id', string='Players')
    player_count = fields.Integer(string='Total Players', compute='_compute_player_count')
    selected_count = fields.Integer(string='Selected', compute='_compute_player_count')

    @api.depends('player_line_ids', 'player_line_ids.migrate')
    def _compute_player_count(self):
        for rec in self:
            rec.player_count = len(rec.player_line_ids)
            rec.selected_count = len(rec.player_line_ids.filtered('migrate'))

    @api.model
    def action_open_wizard(self):
        wizard = self.create(self.default_get(list(self._fields)))
        return {
            'type': 'ir.actions.act_window',
            'name': 'Migrate Tier',
            'res_model': 'auction.migrate.tier',
            'view_mode': 'form',
            'target': 'new',
            'res_id': wizard.id,
            'context': self.env.context,
        }

    @api.model
    def default_get(self, fields_list):
        defaults = super().default_get(fields_list)
        tier_id = self.env.context.get('active_id')
        if not tier_id:
            raise UserError('No tier selected. Please open this wizard from the tier form.')

        players = self.env['auction.team.player'].search(
            [('tier_id', '=', tier_id)], order='sl_no asc'
        )
        defaults['tier_id'] = tier_id
        defaults['player_line_ids'] = [(0, 0, {'player_id': p.id, 'migrate': True}) for p in players]
        return defaults

    def button_select_all(self):
        self.player_line_ids.write({'migrate': True})

    def button_deselect_all(self):
        self.player_line_ids.write({'migrate': False})

    def button_migrate(self):
        self.ensure_one()
        if not self.target_tier_id:
            raise UserError('Please select a Target Tier.')
        if self.target_tier_id == self.tier_id:
            raise UserError('Target tier must be different from the current tier.')

        to_migrate = self.player_line_ids.filtered('migrate').mapped('player_id')
        if not to_migrate:
            raise UserError('No players selected. Tick "Migrate" for at least one player.')

        to_migrate.write({'tier_id': self.target_tier_id.id})
        count = len(to_migrate)

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Tier Migration Complete',
                'message': f'{count} player(s) moved from "{self.tier_id.name}" → "{self.target_tier_id.name}".',
                'type': 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }
