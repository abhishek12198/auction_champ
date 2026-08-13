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
import hashlib
import json
import logging
import os

from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.tools import html_escape

_logger = logging.getLogger(__name__)

_SNAPSHOT_SKIP_NAMES = {
    'id',
    'create_uid',
    'create_date',
    'write_uid',
    'write_date',
    '__last_update',
    'display_name',
    'photo_card',
    'masked_contact',
    'kanban_other_attrs_html',
    'effective_base_price',
    'photo',
    'payment_proof',
}

_SNAPSHOT_SKIP_TYPES = {
    'binary',
    'one2many',
    'html',
    'reference',
    'many2one_reference',
}

_RESTORE_SKIP_NAMES = {
    'sl_no',
    'is_on_stage',
    'card_access_token',
    'current_bid',
    'current_bid_team_id',
    'photo_card',
    'id',
    'other_attribute_ids',
}

_DEFAULT_PHOTO_CHECKSUM = None


def _normalize_contact(contact):
    digits = ''.join(ch for ch in (contact or '') if ch.isdigit())
    if len(digits) >= 10:
        return digits[-10:]
    return digits or False


def _binary_sha1(data):
    if not data:
        return False
    if isinstance(data, str):
        try:
            raw = base64.b64decode(data)
        except Exception:
            raw = data.encode('utf-8')
    else:
        try:
            raw = base64.b64decode(data)
        except Exception:
            raw = data
    if not raw:
        return False
    return hashlib.sha1(raw).hexdigest()


def _default_photo_checksum():
    global _DEFAULT_PHOTO_CHECKSUM
    if _DEFAULT_PHOTO_CHECKSUM is not None:
        return _DEFAULT_PHOTO_CHECKSUM
    path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        'static', 'img', 'default_icon.png',
    )
    try:
        with open(path, 'rb') as fh:
            _DEFAULT_PHOTO_CHECKSUM = hashlib.sha1(fh.read()).hexdigest()
    except Exception:
        _DEFAULT_PHOTO_CHECKSUM = False
    return _DEFAULT_PHOTO_CHECKSUM


class AuctionTeamPlayerDeleted(models.Model):
    """Per-tournament recycle bin for deleted ``auction.team.player`` rows.

    Players are still physically removed from the live table. A full copy is
    kept here so organizers can restore without data loss, with audit of who
    deleted / restored and when.
    """

    _name = 'auction.team.player.deleted'
    _description = 'Deleted Tournament Player'
    _inherit = ['auction.tournament.security.mixin']
    _order = 'deleted_date desc, id desc'
    _rec_name = 'name'

    tournament_id = fields.Many2one(
        'auction.tournament',
        string='Tournament',
        required=True,
        index=True,
        ondelete='cascade',
    )
    original_player_id = fields.Integer(
        string='Original Player ID',
        readonly=True,
        index=True,
        help='Database id of the player row at the time it was deleted.',
    )
    original_sl_no = fields.Integer(string='Original Sl No', readonly=True)
    name = fields.Char(string='Player Name', required=True, readonly=True)
    contact = fields.Char(string='Mobile Number', readonly=True)
    org_id = fields.Char(string='Org ID#', readonly=True)
    role = fields.Char(string='Role', readonly=True)
    photo = fields.Binary(string='Photo', readonly=True, attachment=True)
    payment_proof = fields.Binary(string='Payment Proof', readonly=True, attachment=True)
    state_at_delete = fields.Selection(
        [
            ('draft', 'Draft'),
            ('auction', 'In Auction'),
            ('sold', 'Sold'),
            ('unsold', 'Unsold'),
        ],
        string='State at Delete',
        readonly=True,
    )
    assigned_team_id = fields.Many2one(
        'auction.team', string='Assigned Team', readonly=True, ondelete='set null',
    )
    tier_id = fields.Many2one(
        'auction.player.tier', string='Tier', readonly=True, ondelete='set null',
    )
    icon_player = fields.Boolean(string='Key Player', readonly=True)
    amount_paid = fields.Boolean(string='Payment Received', readonly=True)
    sold_points = fields.Integer(string='Sold For', readonly=True)
    sold_auction_id = fields.Many2one(
        'auction.auction', string='Sale Auction', readonly=True, ondelete='set null',
    )
    snapshot_json = fields.Text(
        string='Player Snapshot',
        readonly=True,
        help='JSON copy of stored player fields used to restore the record.',
    )

    deleted_by_id = fields.Many2one(
        'res.users', string='Deleted By', readonly=True, index=True,
    )
    deleted_date = fields.Datetime(string='Deleted On', readonly=True, index=True)

    is_restored = fields.Boolean(string='Restored', default=False, readonly=True, index=True)
    restored_by_id = fields.Many2one(
        'res.users', string='Restored By', readonly=True, index=True,
    )
    restored_date = fields.Datetime(string='Restored On', readonly=True)
    restored_player_id = fields.Many2one(
        'auction.team.player',
        string='Restored Player',
        readonly=True,
        ondelete='set null',
        help='New player row created when this archive was restored.',
    )
    restored_sl_no = fields.Integer(
        string='Restored Sl No',
        readonly=True,
        help='Serial issued on restore: original Sl No if still free in the '
             'tournament (draft / in auction / sold / unsold), otherwise next.',
    )

    @api.model
    def _build_snapshot(self, player):
        """JSON-safe copy of stored player fields (binaries stored separately)."""
        data = {}
        for name, field in player._fields.items():
            if name in _SNAPSHOT_SKIP_NAMES or not field.store or field.related:
                continue
            if field.type in _SNAPSHOT_SKIP_TYPES:
                continue
            value = player[name]
            if field.type == 'many2one':
                data[name] = value.id if value else False
            elif field.type == 'many2many':
                data[name] = value.ids
            elif field.type in ('date', 'datetime'):
                data[name] = value.isoformat() if value else False
            else:
                data[name] = value
        data['other_attribute_ids'] = [
            {
                'label': attr.label,
                'value': attr.value,
                'sequence': attr.sequence,
            }
            for attr in player.other_attribute_ids
        ]
        return data

    @api.model
    def _archive_players(self, players):
        """Create recycle-bin rows for ``players`` before they are unlinked."""
        if not players:
            return self.browse()
        SaleLine = self.env['auction.auction.player'].sudo()
        now = fields.Datetime.now()
        user_id = self.env.uid
        created = self.browse()
        for player in players:
            sale = SaleLine.search(
                [('player_id', '=', player.id)], limit=1, order='id desc',
            )
            snapshot = self._build_snapshot(player)
            created |= self.create({
                'tournament_id': player.tournament_id.id,
                'original_player_id': player.id,
                'original_sl_no': player.sl_no or 0,
                'name': player.name,
                'contact': player.contact,
                'org_id': player.org_id,
                'role': player.role,
                'photo': player.photo,
                'payment_proof': player.payment_proof,
                'state_at_delete': player.state,
                'assigned_team_id': player.assigned_team_id.id if player.assigned_team_id else False,
                'tier_id': player.tier_id.id if player.tier_id else False,
                'icon_player': bool(player.icon_player),
                'amount_paid': bool(player.amount_paid),
                'sold_points': sale.points if sale else 0,
                'sold_auction_id': sale.auction_id.id if sale else False,
                'snapshot_json': json.dumps(snapshot, default=str),
                'deleted_by_id': user_id,
                'deleted_date': now,
            })
        return created

    def _load_snapshot(self):
        self.ensure_one()
        try:
            return json.loads(self.snapshot_json or '{}')
        except (TypeError, ValueError):
            _logger.warning(
                'Invalid player snapshot on deleted record %s', self.id,
            )
            return {}

    def _existing_id(self, comodel, rec_id):
        if not rec_id:
            return False
        rec = self.env[comodel].browse(int(rec_id))
        return rec.id if rec.exists() else False

    def _prepare_restore_vals(self):
        """Build ``auction.team.player`` create vals from this archive row."""
        self.ensure_one()
        Player = self.env['auction.team.player']
        snapshot = self._load_snapshot()
        vals = {}
        for name, value in snapshot.items():
            if name in _RESTORE_SKIP_NAMES:
                continue
            field = Player._fields.get(name)
            if not field or not field.store or field.related:
                continue
            if field.type == 'many2one':
                vals[name] = self._existing_id(field.comodel_name, value)
            elif field.type == 'many2many':
                ids = [
                    rec_id for rec_id in (value or [])
                    if self._existing_id(field.comodel_name, rec_id)
                ]
                vals[name] = [(6, 0, ids)]
            elif field.type == 'one2many':
                continue
            else:
                vals[name] = value
        vals['tournament_id'] = self.tournament_id.id
        vals['is_on_stage'] = False
        vals['active'] = True
        if 'current_bid' in Player._fields:
            vals['current_bid'] = 0
        if 'current_bid_team_id' in Player._fields:
            vals['current_bid_team_id'] = False
        if self.photo:
            vals['photo'] = self.photo
        if self.payment_proof:
            vals['payment_proof'] = self.payment_proof
        return vals

    def _restore_related_records(self, player):
        """Recreate one2many attributes, sale line and icon-team link."""
        self.ensure_one()
        snapshot = self._load_snapshot()
        attrs = snapshot.get('other_attribute_ids') or []
        commands = []
        for attr in attrs:
            label = (attr.get('label') or '').strip()
            if not label:
                continue
            commands.append((0, 0, {
                'label': label,
                'value': attr.get('value') or '',
                'sequence': attr.get('sequence') or 10,
            }))
        if commands:
            # Drop labels auto-synced on create so restore matches the snapshot.
            player.other_attribute_ids.unlink()
            player.other_attribute_ids = commands

        if (
            player.state == 'sold'
            and self.sold_auction_id
            and self.sold_auction_id.exists()
        ):
            self.env['auction.auction.player'].create({
                'auction_id': self.sold_auction_id.id,
                'player_id': player.id,
                'points': self.sold_points or 0,
            })

        if player.icon_player and player.assigned_team_id:
            player.assigned_team_id.key_player_ids = [(4, player.id)]

    def _photo_checksum(self):
        self.ensure_one()
        Attachment = self.env['ir.attachment'].sudo()
        att = Attachment.search([
            ('res_model', '=', self._name),
            ('res_field', '=', 'photo'),
            ('res_id', '=', self.id),
        ], limit=1)
        if att and att.checksum:
            return att.checksum
        return _binary_sha1(self.photo)

    def _find_contact_matches(self):
        self.ensure_one()
        key = _normalize_contact(self.contact)
        if not key or not self.tournament_id:
            return self.env['auction.team.player']
        players = self.env['auction.team.player'].search([
            ('tournament_id', '=', self.tournament_id.id),
            ('contact', '!=', False),
        ])
        return players.filtered(lambda p: _normalize_contact(p.contact) == key)

    def _find_photo_matches(self):
        self.ensure_one()
        checksum = self._photo_checksum()
        default_cs = _default_photo_checksum()
        if not checksum or checksum == default_cs or not self.tournament_id:
            return self.env['auction.team.player']
        attachments = self.env['ir.attachment'].sudo().search([
            ('res_model', '=', 'auction.team.player'),
            ('res_field', '=', 'photo'),
            ('checksum', '=', checksum),
        ])
        if not attachments:
            return self.env['auction.team.player']
        matches = self.env['auction.team.player'].search([
            ('id', 'in', attachments.mapped('res_id')),
            ('tournament_id', '=', self.tournament_id.id),
        ])
        # Many players sharing one checksum = default / stock photo, not a real duplicate.
        if len(matches) > 2:
            return self.env['auction.team.player']
        return matches

    def _restore_duplicate_warning_html(self):
        """HTML warning if live players already have the same phone or photo."""
        blocks = []
        for rec in self:
            phone_hits = rec._find_contact_matches()
            photo_hits = rec._find_photo_matches()
            if not phone_hits and not photo_hits:
                continue
            lines = []
            for player in phone_hits:
                lines.append(_(
                    'Same mobile number as <b>%(name)s</b> (Sl No %(sl)s): %(phone)s'
                ) % {
                    'name': html_escape(player.name or ''),
                    'sl': player.sl_no or '—',
                    'phone': html_escape(player.contact or rec.contact or ''),
                })
            for player in photo_hits:
                lines.append(_(
                    'Same photo as <b>%(name)s</b> (Sl No %(sl)s)'
                ) % {
                    'name': html_escape(player.name or ''),
                    'sl': player.sl_no or '—',
                })
            blocks.append(
                '<p><b>%s</b> (old Sl No %s)</p><ul>%s</ul>' % (
                    html_escape(rec.name or ''),
                    rec.original_sl_no or '—',
                    ''.join('<li>%s</li>' % line for line in lines),
                )
            )
        if not blocks:
            return False
        return (
            '<div class="alert alert-warning" role="alert">'
            '<p><strong>%s</strong></p>'
            '%s'
            '<p>%s</p>'
            '</div>'
        ) % (
            html_escape(_(
                'A player with the same mobile number or photo already exists '
                'in this tournament.'
            )),
            ''.join(blocks),
            html_escape(_('Do you want to continue restoring anyway?')),
        )

    def _do_restore_players(self):
        """Recreate live player row(s) with the next tournament serial number."""
        Player = self.env['auction.team.player']
        restored = Player.browse()
        for rec in self:
            if rec.is_restored:
                raise UserError(_(
                    '"%s" has already been restored (Sl No %s).'
                ) % (rec.name, rec.restored_sl_no or rec.restored_player_id.sl_no or '—'))
            if not rec.tournament_id:
                raise UserError(_(
                    'Cannot restore "%s": the original tournament is missing.'
                ) % rec.name)
            vals = rec._prepare_restore_vals()
            vals['sl_no'] = Player._get_restore_sl_no(
                rec.tournament_id.id, rec.original_sl_no,
            )
            new_player = Player.create(vals)
            rec._restore_related_records(new_player)
            rec.write({
                'is_restored': True,
                'restored_by_id': self.env.user.id,
                'restored_date': fields.Datetime.now(),
                'restored_player_id': new_player.id,
                'restored_sl_no': new_player.sl_no,
            })
            restored |= new_player

        if restored:
            if len(restored) == 1:
                message = _(
                    '%(name)s restored as Sl No %(sl)s.'
                ) % {'name': restored.name, 'sl': restored.sl_no}
            else:
                message = _(
                    '%(count)s players restored with new serial numbers.'
                ) % {'count': len(restored)}
            try:
                self.env.user.notify_success(message)
            except Exception:
                pass

        if self.env.context.get('restore_from_tournament') and restored:
            tournament = restored.mapped('tournament_id')[:1]
            if tournament:
                return {
                    'type': 'ir.actions.act_window',
                    'res_model': 'auction.tournament',
                    'res_id': tournament.id,
                    'view_mode': 'form',
                    'views': [(False, 'form')],
                    'target': 'current',
                    'context': {'form_view_initial_mode': 'edit'},
                }
        if len(restored) == 1 and not self.env.context.get('restore_from_tournament'):
            return {
                'type': 'ir.actions.act_window',
                'name': _('Restored Player'),
                'res_model': 'auction.team.player',
                'res_id': restored.id,
                'view_mode': 'form',
                'views': [(False, 'form')],
                'target': 'current',
            }
        if restored:
            return {'type': 'ir.actions.client', 'tag': 'reload'}
        return True

    def action_restore_player(self):
        """Restore after an optional duplicate phone/photo warning."""
        recs = self.filtered(lambda r: not r.is_restored)
        already = self - recs
        if already and not recs:
            raise UserError(_(
                '"%s" has already been restored.'
            ) % already[0].name)
        if not recs:
            return True
        missing = recs.filtered(lambda r: not r.tournament_id)
        if missing:
            raise UserError(_(
                'Cannot restore "%s": the original tournament is missing.'
            ) % missing[0].name)
        if not self.env.context.get('skip_restore_duplicate_warning'):
            warning = recs._restore_duplicate_warning_html()
            if warning:
                wizard = self.env['auction.team.player.restore.wizard'].create({
                    'deleted_player_ids': [(6, 0, recs.ids)],
                    'warning_html': warning,
                })
                return {
                    'type': 'ir.actions.act_window',
                    'name': _('Restore Players — Duplicate Found')
                    if len(recs) > 1 else _('Restore Player — Duplicate Found'),
                    'res_model': 'auction.team.player.restore.wizard',
                    'res_id': wizard.id,
                    'view_mode': 'form',
                    'target': 'new',
                    'context': {
                        'restore_from_tournament': self.env.context.get(
                            'restore_from_tournament'
                        ),
                    },
                }
        return recs._do_restore_players()
