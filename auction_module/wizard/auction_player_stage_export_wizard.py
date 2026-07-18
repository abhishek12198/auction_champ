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
import re

from odoo import api, fields, models, _
from odoo.exceptions import UserError

try:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter
except ImportError:  # pragma: no cover
    Workbook = None


class AuctionPlayerStageExportWizard(models.TransientModel):
    _name = 'auction.player.stage.export.wizard'
    _description = 'Export Sold / Unsold Players to Excel'

    tournament_id = fields.Many2one(
        'auction.tournament', string='Tournament', required=True, readonly=True)
    tournament_type = fields.Selection(
        related='tournament_id.tournament_type', string='Sport', readonly=True)
    export_scope = fields.Selection(
        [
            ('both', 'Sold and Unsold'),
            ('sold', 'Sold only'),
            ('unsold', 'Unsold only'),
        ],
        string='Export',
        default='both',
        required=True,
    )
    sold_count = fields.Integer(string='Sold Players', compute='_compute_counts')
    unsold_count = fields.Integer(string='Unsold Players', compute='_compute_counts')
    file_data = fields.Binary(string='Excel File', readonly=True)
    file_name = fields.Char(string='Filename', readonly=True)
    state = fields.Selection(
        [('choose', 'Choose'), ('done', 'Done')],
        default='choose',
    )

    @api.depends('tournament_id')
    def _compute_counts(self):
        Player = self.env['auction.team.player']
        for wiz in self:
            tid = wiz.tournament_id.id
            if not tid:
                wiz.sold_count = 0
                wiz.unsold_count = 0
                continue
            wiz.sold_count = Player.search_count([
                ('tournament_id', '=', tid), ('state', '=', 'sold'),
            ])
            wiz.unsold_count = Player.search_count([
                ('tournament_id', '=', tid), ('state', '=', 'unsold'),
            ])

    def action_generate_excel(self):
        self.ensure_one()
        if Workbook is None:
            raise UserError(_(
                'openpyxl is not installed. Please run: pip install openpyxl'
            ))
        if not self.tournament_id:
            raise UserError(_('Please select a tournament.'))

        scope = self.export_scope
        need_sold = scope in ('sold', 'both')
        need_unsold = scope in ('unsold', 'both')
        if need_sold and not self.sold_count and need_unsold and not self.unsold_count:
            raise UserError(_('No sold or unsold players found for this tournament.'))
        if need_sold and not need_unsold and not self.sold_count:
            raise UserError(_('No sold players found for this tournament.'))
        if need_unsold and not need_sold and not self.unsold_count:
            raise UserError(_('No unsold players found for this tournament.'))

        wb = Workbook()
        # Remove default sheet; we'll add named ones
        default = wb.active
        wb.remove(default)

        if need_sold and self.sold_count:
            self._write_sheet(wb, 'Sold', 'sold')
        if need_unsold and self.unsold_count:
            self._write_sheet(wb, 'Unsold', 'unsold')

        if not wb.sheetnames:
            raise UserError(_('Nothing to export for the selected stage.'))

        buf = io.BytesIO()
        wb.save(buf)
        safe = re.sub(r'[^\w\-]+', '_', self.tournament_id.name or 'tournament')
        fname = 'players_%s_%s.xlsx' % (safe, scope)
        self.write({
            'file_data': base64.b64encode(buf.getvalue()),
            'file_name': fname,
            'state': 'done',
        })
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_back(self):
        self.ensure_one()
        self.write({
            'state': 'choose',
            'file_data': False,
            'file_name': False,
        })
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    # ── Sheet builders ────────────────────────────────────────────────────

    def _header_style(self):
        return (
            PatternFill('solid', fgColor='1B3F8F'),
            Font(color='FFFFFF', bold=True, size=11),
            Alignment(horizontal='center', vertical='center', wrap_text=True),
            Border(
                left=Side(style='thin', color='CCCCCC'),
                right=Side(style='thin', color='CCCCCC'),
                top=Side(style='thin', color='CCCCCC'),
                bottom=Side(style='thin', color='CCCCCC'),
            ),
        )

    def _common_headers(self):
        return ['Sl.No', 'Name', 'Contact', 'Card No']

    def _sport_headers(self):
        t = self.tournament_id
        if t.tournament_type == 'football':
            cols = [
                'Playing Position',
                'Secondary Positions',
                'Preferred Foot',
                'Age',
                'Height',
                'Weight',
                'Work Rate',
                'Playing Styles',
                'Strengths',
            ]
            for lab in t.other_attribute_label_ids.sorted('sequence'):
                if lab.label and lab.label not in cols:
                    cols.append(lab.label)
            return cols
        return [
            'Role',
            'Batting Style',
            'Bowling Style',
            'Blood Group',
            'Player Category',
        ]

    def _sold_headers(self):
        return self._common_headers() + self._sport_headers() + [
            'Sold To', 'Sold Points', 'Base Point', 'Tier',
        ]

    def _unsold_headers(self):
        return self._common_headers() + self._sport_headers() + [
            'Status', 'Tier', 'Base Point',
        ]

    def _sold_points_map(self, players):
        """player_id → sold points (latest auction line)."""
        if not players:
            return {}
        lines = self.env['auction.auction.player'].sudo().search(
            [('player_id', 'in', players.ids)], order='id asc')
        mapping = {}
        for line in lines:
            mapping[line.player_id.id] = line.points or 0
        return mapping

    def _sport_values(self, player):
        t = self.tournament_id
        if t.tournament_type == 'football':
            vals = [
                player.dominant_position_id.name if player.dominant_position_id else '',
                ', '.join(player.secondary_position_ids.mapped('name')),
                (player.preferred_foot or '').capitalize(),
                player.age or '',
                player.height or '',
                player.weight or '',
                (player.work_rate or '').capitalize(),
                ', '.join(player.playing_style_ids.mapped('name')),
                ', '.join(player.strength_ids.mapped('name')),
            ]
            attr_map = {
                (a.label or '').strip().lower(): (a.value or '').strip()
                for a in player.other_attribute_ids
            }
            for lab in t.other_attribute_label_ids.sorted('sequence'):
                if not lab.label:
                    continue
                vals.append(attr_map.get(lab.label.strip().lower(), ''))
            return vals
        return [
            player.role or '',
            player.batting_style or '',
            player.bowling_style or '',
            player.blood_group or '',
            player.p_category or '',
        ]

    def _write_sheet(self, wb, title, stage):
        ws = wb.create_sheet(title)
        headers = self._sold_headers() if stage == 'sold' else self._unsold_headers()
        fill, font, align, border = self._header_style()

        for col_idx, header in enumerate(headers, start=1):
            cell = ws.cell(row=1, column=col_idx, value=header)
            cell.fill = fill
            cell.font = font
            cell.alignment = align
            cell.border = border
            ws.column_dimensions[get_column_letter(col_idx)].width = max(
                12, min(28, len(header) + 4))

        players = self.env['auction.team.player'].search(
            [
                ('tournament_id', '=', self.tournament_id.id),
                ('state', '=', stage),
            ],
            order='sl_no asc, name asc',
        )
        points_map = self._sold_points_map(players) if stage == 'sold' else {}

        thin = Border(
            left=Side(style='thin', color='DDDDDD'),
            right=Side(style='thin', color='DDDDDD'),
            top=Side(style='thin', color='DDDDDD'),
            bottom=Side(style='thin', color='DDDDDD'),
        )
        for seq, player in enumerate(players, start=1):
            row = [
                seq,
                (player.name or '').upper(),
                player.contact or '',
                player.sl_no or '',
            ]
            row.extend(self._sport_values(player))
            if stage == 'sold':
                row.extend([
                    player.assigned_team_id.name if player.assigned_team_id else '',
                    points_map.get(player.id, 0),
                    player.effective_base_price or 0,
                    player.tier_id.name if player.tier_id else '',
                ])
            else:
                row.extend([
                    'Unsold',
                    player.tier_id.name if player.tier_id else '',
                    player.effective_base_price or 0,
                ])
            for col_idx, value in enumerate(row, start=1):
                cell = ws.cell(row=seq + 1, column=col_idx, value=value)
                cell.border = thin
                if col_idx == 2:
                    cell.font = Font(bold=True)

        ws.auto_filter.ref = 'A1:%s%d' % (
            get_column_letter(len(headers)), max(1, len(players) + 1))
        ws.freeze_panes = 'A2'
