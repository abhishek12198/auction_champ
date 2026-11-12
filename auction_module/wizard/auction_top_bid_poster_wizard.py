# -*- coding: utf-8 -*-
##############################################################################
#
#  AuctionChamp - Professional Sports Auction Management Platform
#
#  Copyright (c) 2026 AuctionChamp.
#  All Rights Reserved.
#
##############################################################################

import base64
import io
import zipfile
from datetime import datetime

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class AuctionTopBidPosterWizardLine(models.TransientModel):
    _name = 'auction.top.bid.poster.wizard.line'
    _description = 'Top Bid Poster Tier'
    _order = 'sequence, id'

    wizard_id = fields.Many2one(
        'auction.top.bid.poster.wizard', required=True, ondelete='cascade',
    )
    tier_id = fields.Many2one('auction.player.tier', string='Tier', required=True)
    sequence = fields.Integer(related='tier_id.sequence', store=True)
    sold_count = fields.Integer(string='Sold')
    available = fields.Boolean(string='Has sales')
    selected = fields.Boolean(string='Download')


class AuctionTopBidPosterWizard(models.TransientModel):
    _name = 'auction.top.bid.poster.wizard'
    _description = 'Top 5 Bid Posters'

    tournament_id = fields.Many2one(
        'auction.tournament', string='Tournament', required=True, readonly=True,
    )
    include_overall = fields.Boolean(string='Overall', default=True)
    overall_sold_count = fields.Integer(string='Sold')
    line_ids = fields.One2many(
        'auction.top.bid.poster.wizard.line', 'wizard_id', string='Tiers',
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        tid = res.get('tournament_id') or self.env.context.get('default_tournament_id')
        if not tid:
            return res
        tournament = self.env['auction.tournament'].browse(tid)
        if not tournament.exists():
            return res
        res['tournament_id'] = tournament.id
        overall = len(tournament._top_bid_pool())
        res['overall_sold_count'] = overall
        res['include_overall'] = overall > 0
        tiers = self.env['auction.player.tier'].search([
            ('tournament_id', '=', tournament.id),
            ('is_an_icon_tier', '=', False),
        ])
        commands = []
        for tier in tiers:
            count = len(tournament._top_bid_pool(tier))
            commands.append((0, 0, {
                'tier_id': tier.id,
                'sold_count': count,
                'available': count > 0,
                'selected': False,
            }))
        res['line_ids'] = commands
        return res

    def _reopen(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Top 5 Bid Posters'),
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_select_tiers(self):
        self.ensure_one()
        for line in self.line_ids:
            count = len(self.tournament_id._top_bid_pool(line.tier_id)) if line.tier_id else 0
            line.write({
                'sold_count': count,
                'available': count > 0,
                'selected': count > 0,
            })
        return self._reopen()

    def action_clear_tiers(self):
        self.ensure_one()
        self.line_ids.write({'selected': False})
        return self._reopen()

    def _scopes(self):
        self.ensure_one()
        tournament = self.tournament_id
        scopes = []
        if self.include_overall and tournament._top_bid_pool():
            lines = tournament._top_bid_lines()
            if lines:
                scopes.append({
                    'label': 'OVERALL',
                    'file_part': 'Overall',
                    'night_color': None,
                    'lines': lines,
                    'chip_bg': '#f0c14b',
                    'chip_ink': '#1a1404',
                })
        for line in self.line_ids:
            if not line.selected or not line.tier_id:
                continue
            if line.tier_id.is_an_icon_tier:
                continue
            sold = tournament._top_bid_lines(line.tier_id)
            if not sold:
                continue
            color = (line.tier_id.color or '#3498db').lower()
            scopes.append({
                'label': (line.tier_id.name or 'Tier').upper(),
                'file_part': line.tier_id.name or 'Tier',
                'night_color': color,
                'lines': sold,
                'chip_bg': color,
                'chip_ink': tournament._top_bid_chip_ink(color),
            })
        return scopes

    def _download_action(self, filename, payload, mimetype):
        attachment = self.env['ir.attachment'].sudo().create({
            'name': filename,
            'type': 'binary',
            'datas': base64.b64encode(payload),
            'mimetype': mimetype,
            'res_model': 'auction.tournament',
            'res_id': self.tournament_id.id,
        })
        return {
            'type': 'ir.actions.act_url',
            'url': '/web/content/%s?download=true&unique=%s' % (
                attachment.id, attachment.id),
            'target': 'new',
        }

    def action_download(self):
        self.ensure_one()
        scopes = self._scopes()
        if not scopes:
            raise UserError(_(
                'Select Overall or a tier that already has a sold player.'
            ))
        tournament = self.tournament_id
        stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        tname = tournament._top_bid_file_part(tournament.name or 'Tournament')
        rendered = []
        used = set()
        for scope in scopes:
            jpg = tournament._top_bid_poster_jpg(
                scope['lines'],
                scope['label'],
                'background:%s;color:%s;' % (scope['chip_bg'], scope['chip_ink']),
                scope['night_color'],
            )
            part = tournament._top_bid_file_part(scope['file_part'])
            name = 'Top_5_Bids_%s_%s.jpg' % (tname, part)
            if name in used:
                name = 'Top_5_Bids_%s_%s_%s.jpg' % (tname, part, scope['lines'][0].id)
            used.add(name)
            rendered.append((name, jpg))
        if len(rendered) == 1:
            filename = rendered[0][0].replace('.jpg', '_%s.jpg' % stamp)
            return self._download_action(filename, rendered[0][1], 'image/jpeg')
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
            for name, jpg in rendered:
                archive.writestr(name, jpg)
        filename = 'Top_5_Bids_%s_%s.zip' % (tname, stamp)
        return self._download_action(filename, buffer.getvalue(), 'application/zip')
