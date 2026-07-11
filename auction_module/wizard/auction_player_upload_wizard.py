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

import base64
import io
import os
import re
import zipfile

from odoo import fields, models, _
from odoo.exceptions import UserError

try:
    from openpyxl import Workbook, load_workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
except ImportError:  # pragma: no cover
    Workbook = None
    load_workbook = None


_PHOTO_EXTS = {'.jpg', '.jpeg', '.png'}


class AuctionPlayerUploadWizard(models.TransientModel):
    _name = 'auction.player.upload.wizard'
    _description = 'Upload Players from Excel + Photo ZIP'

    tournament_id = fields.Many2one(
        'auction.tournament', string='Tournament', required=True, readonly=True)
    tournament_type = fields.Selection(
        related='tournament_id.tournament_type', readonly=True)
    excel_file = fields.Binary(string='Players Excel (.xlsx)')
    excel_filename = fields.Char(string='Excel Filename')
    photos_zip = fields.Binary(
        string='Player Photos ZIP',
        help='Optional. ZIP of photos named 1.jpg, 2.png, … matching Excel row order '
             '(first data row = 1). Supports .jpg / .jpeg / .png (any case).')
    photos_zip_filename = fields.Char(string='ZIP Filename')
    template_file = fields.Binary(string='Download Template', readonly=True)
    template_filename = fields.Char(readonly=True)
    state = fields.Selection(
        [('draft', 'Upload'), ('done', 'Done')], default='draft')
    result_message = fields.Text(string='Result', readonly=True)
    created_count = fields.Integer(readonly=True)
    photo_count = fields.Integer(readonly=True)

    def _cricket_columns(self):
        return [
            'Serial No',
            'Name',
            'Contact',
            'Role',
            'Batting Style',
            'Bowling Style',
            'Blood Group',
            'Category',
            'Location',
            'Tier',
            'Base Price',
            'Jersey Name',
            'Jersey Number',
            'Jersey Size',
        ]

    def _football_base_columns(self):
        return [
            'Serial No',
            'Name',
            'Contact',
            'Playing Position',
            'Secondary Positions',
            'Preferred Foot',
            'Age',
            'Height',
            'Weight',
            'Playing Styles',
            'Strengths',
            'Work Rate',
            'Blood Group',
            'Category',
            'Location',
            'Tier',
            'Base Price',
            'Jersey Name',
            'Jersey Number',
            'Jersey Size',
        ]

    def _excel_columns(self):
        self.ensure_one()
        if self.tournament_id.tournament_type == 'football':
            cols = list(self._football_base_columns())
            for lab in self.tournament_id.other_attribute_label_ids.sorted('sequence'):
                if lab.label and lab.label not in cols:
                    cols.append(lab.label)
            return cols
        return list(self._cricket_columns())

    def action_download_template(self):
        self.ensure_one()
        if Workbook is None:
            raise UserError(_(
                'openpyxl is not installed. Please run: pip install openpyxl'
            ))
        columns = self._excel_columns()
        wb = Workbook()
        ws = wb.active
        ws.title = 'Players'

        header_fill = PatternFill('solid', fgColor='1B3F8F')
        header_font = Font(color='FFFFFF', bold=True)
        thin = Border(
            left=Side(style='thin', color='CCCCCC'),
            right=Side(style='thin', color='CCCCCC'),
            top=Side(style='thin', color='CCCCCC'),
            bottom=Side(style='thin', color='CCCCCC'),
        )
        for col_idx, title in enumerate(columns, start=1):
            cell = ws.cell(row=1, column=col_idx, value=title)
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal='center', wrap_text=True)
            cell.border = thin
            ws.column_dimensions[cell.column_letter].width = max(14, min(28, len(title) + 4))

        sample = {c: '' for c in columns}
        sample['Serial No'] = '1'
        sample['Name'] = 'Sample Player'
        sample['Contact'] = '9876543210'
        if self.tournament_id.tournament_type == 'football':
            sample['Playing Position'] = 'CB'
            sample['Secondary Positions'] = 'CB, RB'
            sample['Preferred Foot'] = 'Left'
            sample['Age'] = '25'
            sample['Playing Styles'] = 'Target Man'
            sample['Strengths'] = 'Speed'
            sample['Work Rate'] = 'Medium'
            for lab in self.tournament_id.other_attribute_label_ids:
                if lab.label in sample:
                    sample[lab.label] = 'Example'
        else:
            sample['Role'] = 'Batsman'
            sample['Batting Style'] = 'Right Handed Batter'
            sample['Bowling Style'] = 'Right Arm'
        sample['Blood Group'] = 'A+'
        sample['Tier'] = 'Rookie'
        for col_idx, title in enumerate(columns, start=1):
            cell = ws.cell(row=2, column=col_idx, value=sample.get(title, ''))
            cell.border = thin
            cell.font = Font(italic=True, color='888888')

        info = wb.create_sheet('Instructions')
        tips = [
            'Player Upload Template — %s (%s)' % (
                self.tournament_id.name,
                (self.tournament_id.tournament_type or '').title(),
            ),
            '',
            '1. Fill the Players sheet. Row 2 is a sample — replace or delete it.',
            '2. Name is required. Other columns are optional.',
            '3. Serial No is optional; if blank, players are numbered in Excel order.',
            '4. Photos ZIP (optional): name files 1.jpg, 2.png, 3.jpeg … matching Excel data row order '
            '(first player row after the header = 1). PNG / JPG / JPEG (any case) are supported.',
            '5. Football — Playing Position / Secondary / Styles / Strengths: use names or codes '
            'from the master data (comma-separated for multi values).',
            '6. Football — Preferred Foot: Left / Right / Both. Work Rate: Low / Medium / High.',
        ]
        if self.tournament_id.tournament_type == 'football':
            labels = self.tournament_id.other_attribute_label_ids.mapped('label')
            tips.append(
                '7. Other Attribute columns (Att-Labels from this tournament): %s' % (
                    ', '.join(labels) if labels else
                    '(none configured — add them on the tournament Other Attributes tab)'
                )
            )
            tips.append(
                '   Fill Label-Values under those columns; they become Other Attributes on each player.'
            )
        for i, line in enumerate(tips, start=1):
            info.cell(row=i, column=1, value=line)
        info.column_dimensions['A'].width = 110

        buf = io.BytesIO()
        wb.save(buf)
        sport = self.tournament_id.tournament_type or 'players'
        fname = 'player_upload_%s_%s.xlsx' % (
            re.sub(r'[^\w\-]+', '_', self.tournament_id.name or 'tournament'),
            sport,
        )
        self.write({
            'template_file': base64.b64encode(buf.getvalue()),
            'template_filename': fname,
        })
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_import(self):
        self.ensure_one()
        if load_workbook is None:
            raise UserError(_(
                'openpyxl is not installed. Please run: pip install openpyxl'
            ))
        if not self.excel_file:
            raise UserError(_('Please upload a filled Players Excel (.xlsx) file.'))

        try:
            wb = load_workbook(
                filename=io.BytesIO(base64.b64decode(self.excel_file)),
                data_only=True,
            )
        except Exception as exc:
            raise UserError(_('Could not read Excel file: %s') % exc) from exc

        ws = wb.active
        rows = list(ws.iter_rows(values_only=True))
        if not rows:
            raise UserError(_('The Excel file is empty.'))

        headers = [self._norm_header(h) for h in rows[0]]
        if not any(headers):
            raise UserError(_('The Excel header row is missing.'))

        header_map = {}
        for idx, h in enumerate(headers):
            if h and h not in header_map:
                header_map[h] = idx

        name_key = self._find_header(header_map, ['name', 'player name', 'player'])
        if name_key is None:
            raise UserError(_('Excel must include a "Name" column.'))

        photo_map = self._parse_photos_zip()
        Player = self.env['auction.team.player']
        created = 0
        photos_applied = 0
        errors = []
        data_row_no = 0

        for raw in rows[1:]:
            if not raw or all(v is None or str(v).strip() == '' for v in raw):
                continue
            data_row_no += 1

            def cell(key_aliases, _raw=raw, _map=header_map):
                key = self._find_header(_map, key_aliases)
                if key is None:
                    return ''
                val = _raw[_map[key]] if _map[key] < len(_raw) else None
                if val is None:
                    return ''
                if isinstance(val, float) and val.is_integer():
                    return str(int(val))
                return str(val).strip()

            name = cell(['name', 'player name', 'player'])
            if not name:
                data_row_no -= 1
                continue
            if name.lower().startswith('sample'):
                continue

            try:
                vals = self._row_to_player_vals(cell, name, data_row_no, header_map, raw)
                photo_b64 = photo_map.get(data_row_no)
                if photo_b64:
                    vals['photo'] = photo_b64
                    photos_applied += 1
                Player.create(vals)
                created += 1
            except Exception as exc:
                errors.append('Row %s (%s): %s' % (data_row_no, name, exc))

        msg_lines = [
            'Imported %s player(s) into %s.' % (created, self.tournament_id.name),
            'Photos attached: %s.' % photos_applied,
        ]
        if errors:
            msg_lines.append('')
            msg_lines.append('Skipped / failed rows:')
            msg_lines.extend(errors[:30])
            if len(errors) > 30:
                msg_lines.append('… and %s more.' % (len(errors) - 30))

        self.write({
            'state': 'done',
            'created_count': created,
            'photo_count': photos_applied,
            'result_message': '\n'.join(msg_lines),
        })
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_close(self):
        return {'type': 'ir.actions.act_window_close'}

    @staticmethod
    def _norm_header(value):
        if value is None:
            return ''
        return re.sub(r'\s+', ' ', str(value).strip()).lower()

    @staticmethod
    def _find_header(header_map, aliases):
        for alias in aliases:
            key = alias.lower().strip()
            if key in header_map:
                return key
        return None

    def _parse_photos_zip(self):
        """Return {1: base64, 2: base64, …} from ZIP entries named N.ext."""
        self.ensure_one()
        mapping = {}
        if not self.photos_zip:
            return mapping
        try:
            zf = zipfile.ZipFile(io.BytesIO(base64.b64decode(self.photos_zip)))
        except Exception as exc:
            raise UserError(_('Could not read photos ZIP: %s') % exc) from exc

        for info in zf.infolist():
            if info.is_dir():
                continue
            basename = os.path.basename(info.filename)
            if not basename or basename.startswith('.') or '__MACOSX' in info.filename:
                continue
            stem, ext = os.path.splitext(basename)
            if ext.lower() not in _PHOTO_EXTS:
                continue
            match = re.search(r'(\d+)$', stem.strip())
            if not match:
                continue
            num = int(match.group(1))
            if num < 1:
                continue
            mapping[num] = base64.b64encode(zf.read(info)).decode('ascii')
        return mapping

    def _resolve_tier(self, tier_name):
        if not tier_name:
            return False
        Tier = self.env['auction.player.tier']
        domain_extra = []
        if 'tournament_id' in Tier._fields:
            domain_extra = ['|', ('tournament_id', '=', self.tournament_id.id),
                            ('tournament_id', '=', False)]
        tier = Tier.search([('name', '=ilike', tier_name)] + domain_extra, limit=1)
        if not tier:
            tier = Tier.search([('name', '=ilike', tier_name)], limit=1)
        return tier.id if tier else False

    def _resolve_positions(self, text, multi=False):
        Position = self.env['auction.player.position']
        if not text:
            return [] if multi else False
        parts = [p.strip() for p in re.split(r'[,;/|]+', text) if p.strip()]
        ids = []
        for part in parts:
            pos = Position.search([
                '|', ('code', '=ilike', part), ('name', '=ilike', part)
            ], limit=1)
            if pos:
                ids.append(pos.id)
        if multi:
            return ids
        return ids[0] if ids else False

    def _resolve_m2m_by_name(self, model, text):
        if not text:
            return []
        Model = self.env[model]
        ids = []
        for part in [p.strip() for p in re.split(r'[,;/|]+', text) if p.strip()]:
            rec = Model.search([('name', '=ilike', part)], limit=1)
            if rec:
                ids.append(rec.id)
        return ids

    def _row_to_player_vals(self, cell, name, data_row_no, header_map, raw):
        tournament = self.tournament_id
        sl_raw = cell(['serial no', 'serial', 'sl no', 'sl_no', '#'])
        try:
            sl_no = int(float(sl_raw)) if sl_raw else data_row_no
        except ValueError:
            sl_no = data_row_no

        vals = {
            'tournament_id': tournament.id,
            'name': name,
            'sl_no': sl_no,
            'contact': cell(['contact', 'mobile', 'phone', 'mobile no', 'mobile number']),
            'blood_group': cell(['blood group', 'blood']),
            'p_category': cell(['category', 'player category']),
            'address': cell(['location', 'address', 'venue']),
            'jersy_name': cell(['jersey name', 'jersy name', 'name on jersey']),
            'jersy_number': cell(['jersey number', 'jersy number', 'jersey no']),
            'jersy_size': cell(['jersey size', 'jersy size']),
            'state': 'draft',
        }
        tier_id = self._resolve_tier(cell(['tier']))
        if tier_id:
            vals['tier_id'] = tier_id
        base_price = cell(['base price', 'base_price', 'base point'])
        if base_price:
            try:
                vals['base_price'] = int(float(base_price))
            except ValueError:
                pass

        if tournament.tournament_type == 'football':
            pos_id = self._resolve_positions(
                cell(['playing position', 'position', 'dominant position']), multi=False)
            if pos_id:
                vals['dominant_position_id'] = pos_id
            sec_ids = self._resolve_positions(
                cell(['secondary positions', 'secondary', 'secondary position']), multi=True)
            if sec_ids:
                vals['secondary_position_ids'] = [(6, 0, sec_ids)]
            foot = cell(['preferred foot', 'foot']).lower()
            if foot in ('left', 'right', 'both'):
                vals['preferred_foot'] = foot
            age = cell(['age'])
            if age:
                try:
                    vals['age'] = int(float(age))
                except ValueError:
                    pass
            height = cell(['height'])
            weight = cell(['weight'])
            if height:
                vals['height'] = height
            if weight:
                vals['weight'] = weight
            style_ids = self._resolve_m2m_by_name(
                'auction.player.style',
                cell(['playing styles', 'playing style', 'styles']))
            if style_ids:
                vals['playing_style_ids'] = [(6, 0, style_ids)]
            strength_ids = self._resolve_m2m_by_name(
                'auction.player.strength',
                cell(['strengths', 'strength']))
            if strength_ids:
                vals['strength_ids'] = [(6, 0, strength_ids)]
            rate = cell(['work rate', 'workrate']).lower()
            if rate in ('low', 'medium', 'high'):
                vals['work_rate'] = rate

            attr_commands = []
            for lab in tournament.other_attribute_label_ids.sorted('sequence'):
                label = (lab.label or '').strip()
                if not label:
                    continue
                key = self._norm_header(label)
                value = ''
                if key in header_map:
                    idx = header_map[key]
                    raw_val = raw[idx] if idx < len(raw) else None
                    if raw_val is not None:
                        if isinstance(raw_val, float) and raw_val.is_integer():
                            value = str(int(raw_val))
                        else:
                            value = str(raw_val).strip()
                attr_commands.append((0, 0, {
                    'label': label,
                    'value': value,
                    'sequence': lab.sequence or 10,
                }))
            if attr_commands:
                vals['other_attribute_ids'] = attr_commands
        else:
            role = cell(['role'])
            if role:
                vals['role'] = role
            batting = cell(['batting style', 'batting'])
            bowling = cell(['bowling style', 'bowling'])
            if batting:
                vals['batting_style'] = batting
            if bowling:
                vals['bowling_style'] = bowling

        return vals
