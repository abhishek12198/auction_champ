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

    apply_max_call = fields.Boolean(string='Update?', default=False)
    new_max_call = fields.Integer(
        string='New Max Call',
        default=0,
        help='Maximum bid for a player of this tier. 0 = no cap.',
    )


class UpdateTierLimitsSlabLine(models.TransientModel):
    _name = 'auction.update.tier.limits.slab.line'
    _description = 'Bid Slab Update Line'
    _order = 'from_amount'

    wizard_id = fields.Many2one('auction.update.tier.limits', ondelete='cascade')
    from_amount = fields.Integer(string='From', required=True)
    to_amount = fields.Integer(string='To', required=True)
    increment = fields.Integer(string='Increment', required=True)


class UpdateTierLimits(models.TransientModel):
    _name = 'auction.update.tier.limits'
    _description = 'Bulk Update Tier Limits & Bid Slabs across Auctions'

    auction_ids = fields.Many2many('auction.auction', string='Selected Auctions', readonly=True)
    apply_global_base = fields.Boolean(
        string='Update global base point',
        default=False,
        help='When ticked, write Global base point on every selected auction.',
    )
    new_global_base = fields.Integer(
        string='Global base point',
        default=0,
        help='Default minimum bid for tiers whose Base Point is 0. No hidden fallback.',
    )
    line_ids = fields.One2many('auction.update.tier.limits.line', 'wizard_id', string='Tier Adjustments')
    update_slabs = fields.Boolean(
        string='Update Bid Slabs',
        default=False,
        help='When ticked, replace bid slabs on all selected auctions with the table below.',
    )
    slab_ids = fields.One2many(
        'auction.update.tier.limits.slab.line',
        'wizard_id',
        string='Bid Slabs',
    )

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
            'name': 'Update Tier Limits & Slabs',
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
                        'new_max_call': tl.max_call,
                        'apply_max_players': False,
                        'apply_base_point': False,
                        'apply_max_call': False,
                    }))

        # Prefill slabs from the first selected auction that has them
        slab_lines = []
        for auction in auctions:
            slabs = auction.auction_bid_slab_ids.sorted('from_amount')
            if slabs:
                for s in slabs:
                    slab_lines.append((0, 0, {
                        'from_amount': s.from_amount,
                        'to_amount': s.to_amount,
                        'increment': s.increment,
                    }))
                break

        if not lines and not slab_lines:
            raise UserError(
                'None of the selected auctions have tier limits or bid slabs configured. '
                'Please set them up on the auction first (Set Auction Rules).'
            )

        defaults['line_ids'] = lines
        defaults['slab_ids'] = slab_lines
        defaults['update_slabs'] = False
        defaults['apply_global_base'] = False
        defaults['new_global_base'] = auctions[:1].base_point if auctions else 0
        defaults['auction_ids'] = [(6, 0, auction_ids)]
        return defaults

    def _validate_slabs(self):
        self.ensure_one()
        if not self.slab_ids:
            raise UserError('Add at least one bid slab row before applying slab updates.')
        rows = self.slab_ids.sorted('from_amount')
        prev_to = None
        for s in rows:
            if s.from_amount < 0 or s.to_amount < 0 or s.increment < 1:
                raise UserError(
                    'Each slab needs From/To ≥ 0 and Increment ≥ 1.'
                )
            if s.to_amount < s.from_amount:
                raise UserError(
                    'Slab "To" must be greater than or equal to "From" '
                    '(%s → %s).' % (s.from_amount, s.to_amount)
                )
            if prev_to is not None and s.from_amount < prev_to:
                raise UserError(
                    'Slab ranges overlap or are out of order. '
                    'Sort by From amount without overlapping ranges.'
                )
            prev_to = s.to_amount

    def button_apply(self):
        self.ensure_one()

        auctions = self.auction_ids
        if not auctions:
            raise UserError(
                'No auctions found. Please re-open this wizard from the auction list.'
            )

        tier_changes = any(
            l.apply_max_players or l.apply_base_point or l.apply_max_call
            for l in self.line_ids
        )
        if not tier_changes and not self.update_slabs and not self.apply_global_base:
            raise UserError(
                'No changes selected. Tick a toggle for global base, a tier field, '
                'and/or "Update Bid Slabs" to apply.'
            )
        if self.apply_global_base and self.new_global_base < 0:
            raise UserError('Global base point cannot be negative.')

        if self.update_slabs:
            self._validate_slabs()

        updated_tiers = 0
        updated_slab_auctions = 0

        for auction in auctions:
            for line in self.line_ids:
                tl = auction.tier_limit_ids.filtered(
                    lambda t, l=line: t.tier_id.id == l.tier_id.id
                )
                if not tl:
                    continue
                vals = {}
                if line.apply_max_players:
                    if line.new_max_players < 1:
                        raise UserError(
                            'Max Players for tier "%s" must be at least 1.'
                            % line.tier_id.name
                        )
                    vals['max_players'] = line.new_max_players
                if line.apply_base_point:
                    if line.new_base_point < 0:
                        raise UserError(
                            'Base Point for tier "%s" cannot be negative.'
                            % line.tier_id.name
                        )
                    vals['base_point'] = line.new_base_point
                if line.apply_max_call:
                    if line.new_max_call < 0:
                        raise UserError(
                            'Max Call for tier "%s" cannot be negative.'
                            % line.tier_id.name
                        )
                    vals['max_call'] = line.new_max_call
                if vals:
                    tl.write(vals)
                    updated_tiers += 1

            if self.apply_global_base:
                auction.write({'base_point': self.new_global_base})

            if self.update_slabs:
                auction.auction_bid_slab_ids.unlink()
                auction.write({
                    'auction_bid_slab_ids': [
                        (0, 0, {
                            'from_amount': s.from_amount,
                            'to_amount': s.to_amount,
                            'increment': s.increment,
                        })
                        for s in self.slab_ids.sorted('from_amount')
                    ],
                })
                updated_slab_auctions += 1

        parts = []
        if self.apply_global_base:
            parts.append('global base point')
        if updated_tiers:
            parts.append('%s tier limit record(s)' % updated_tiers)
        if updated_slab_auctions:
            parts.append('bid slabs on %s auction(s)' % updated_slab_auctions)
        message = 'Updated %s across %s auction(s).' % (
            ' and '.join(parts) if parts else 'nothing',
            len(auctions),
        )

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Tier Limits & Slabs Updated',
                'message': message,
                'type': 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }
