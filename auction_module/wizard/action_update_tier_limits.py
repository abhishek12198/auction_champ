# -*- coding: utf-8 -*-
from odoo import api, models, fields
from odoo.exceptions import UserError


class UpdateTierLimitsLine(models.TransientModel):
    _name = 'auction.update.tier.limits.line'
    _description = 'Tier Limit Update Line'

    wizard_id = fields.Many2one('auction.update.tier.limits', ondelete='cascade')
    tier_id = fields.Many2one('auction.player.tier', string='Tier', readonly=True)

    apply_max_players = fields.Boolean(string='Update?', default=False)
    new_max_players = fields.Integer(string='New Max Players', default=1)

    apply_base_point = fields.Boolean(string='Update?', default=False)
    new_base_point = fields.Integer(string='New Base Point', default=0)


class UpdateTierLimits(models.TransientModel):
    _name = 'auction.update.tier.limits'
    _description = 'Bulk Update Tier Limits across Auctions'

    auction_ids = fields.Many2many('auction.auction', string='Selected Auctions', readonly=True)
    line_ids = fields.One2many('auction.update.tier.limits.line', 'wizard_id', string='Tier Adjustments')

    @api.model
    def action_open_wizard(self):
        # Pre-create the wizard via Python ORM so readonly fields (auction_ids,
        # tier_id on lines) are persisted before the dialog opens.  The JS client
        # strips readonly field values from its create/write payloads, so if we
        # relied on the client to create the record these fields would be empty
        # when button_apply runs.
        wizard = self.create(self.default_get(list(self._fields)))
        return {
            'type': 'ir.actions.act_window',
            'name': 'Update Tier Limits',
            'res_model': 'auction.update.tier.limits',
            'view_mode': 'form',
            'target': 'new',
            'res_id': wizard.id,
            'context': self.env.context,
        }

    @api.model
    def default_get(self, fields_list):
        defaults = super().default_get(fields_list)
        auction_ids = self.env.context.get('active_ids', [])
        auctions = self.env['auction.auction'].browse(auction_ids)

        seen_tier_ids = set()
        lines = []
        for auction in auctions:
            for tl in auction.tier_limit_ids:
                if tl.tier_id.id not in seen_tier_ids:
                    seen_tier_ids.add(tl.tier_id.id)
                    lines.append((0, 0, {
                        'tier_id': tl.tier_id.id,
                        'new_max_players': tl.max_players,
                        'new_base_point': tl.base_point,
                        'apply_max_players': False,
                        'apply_base_point': False,
                    }))

        if not lines:
            raise UserError(
                'None of the selected auctions have tier limits configured. '
                'Please set up tier limits on the auction first.'
            )

        defaults['line_ids'] = lines
        defaults['auction_ids'] = [(6, 0, auction_ids)]
        return defaults

    def button_apply(self):
        self.ensure_one()

        auctions = self.auction_ids
        if not auctions:
            raise UserError(
                'No auctions found. Please re-open this wizard from the auction list.'
            )

        if not any(l.apply_max_players or l.apply_base_point for l in self.line_ids):
            raise UserError('No changes selected. Tick the "Update?" checkbox for at least one field to apply.')

        updated = 0
        for auction in auctions:
            for line in self.line_ids:
                tl = auction.tier_limit_ids.filtered(lambda t, l=line: t.tier_id.id == l.tier_id.id)
                if not tl:
                    continue
                vals = {}
                if line.apply_max_players:
                    if line.new_max_players < 1:
                        raise UserError(
                            f'Max Players for tier "{line.tier_id.name}" must be at least 1.'
                        )
                    vals['max_players'] = line.new_max_players
                if line.apply_base_point:
                    if line.new_base_point < 0:
                        raise UserError(
                            f'Base Point for tier "{line.tier_id.name}" cannot be negative.'
                        )
                    vals['base_point'] = line.new_base_point
                if vals:
                    tl.write(vals)
                    updated += 1

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Tier Limits Updated',
                'message': f'Updated {updated} tier limit record(s) across {len(auctions)} auction(s).',
                'type': 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }
