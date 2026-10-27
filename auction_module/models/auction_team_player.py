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
import logging
import os
import random
from odoo import api, models, fields, _
from odoo.exceptions import UserError
from odoo.tools.image import image_data_uri, image_process
import requests
import werkzeug
import werkzeug.exceptions
from urllib.parse import urlparse, parse_qs
import re

_logger = logging.getLogger(__name__)

# Stylesheet for Instagram Stories / Status player cards (9:16).
# Qt-WebKit-safe: -webkit- gradients, no CSS vars/grid/object-fit/backdrop-filter.
# Palette values substituted via string.Template ($name placeholders).
_CARD_SPLIT_THEMES = {
    'butterscotch': {'ink': '#C8960C', 'bright': '#F5C842', 'surname': '#F5C842'},
    'cherry':       {'ink': '#9F1239', 'bright': '#E11D48', 'surname': '#FB7185'},
    'vanilla':      {'ink': '#8A7D62', 'bright': '#C4B8A0', 'surname': '#8AA6D4'},
    'pistah':       {'ink': '#2E7D32', 'bright': '#6BBF4E', 'surname': '#A8E063'},
    'blueberry':    {'ink': '#1E3A8A', 'bright': '#3B82F6', 'surname': '#93C5FD'},
    'blackberry':   {'ink': '#4C1D95', 'bright': '#7629D9', 'surname': '#A77BFF'},
    'lemon':        {'ink': '#8F7400', 'bright': '#C9A400', 'surname': '#D9B820'},
    'strawberry':   {'ink': '#880E4F', 'bright': '#C2185B', 'surname': '#E91E63'},
    'standard':     {'ink': '#1058B0', 'bright': '#1058B0', 'surname': '#FFFFFF'},
}

_CARD_CSS = """
*{margin:0;padding:0;box-sizing:border-box;-webkit-print-color-adjust:exact;}
html,body{width:1080px;height:1920px;background:#ffffff;overflow:hidden;}
.pc{position:relative;width:1080px;height:1920px;overflow:hidden;background:#ffffff;font-family:Arial,Helvetica,sans-serif;color:#111827;}
.pc-left{position:absolute;top:0;left:0;width:560px;height:1920px;overflow:hidden;background:#071426;}
.pc-stadium{position:absolute;top:0;left:0;width:560px;height:1920px;background-color:#071426;background-size:cover;background-position:left top;background-repeat:no-repeat;}
.pc-player{position:absolute;left:0;bottom:0;width:560px;height:1460px;background-size:cover;background-position:center 18%;background-repeat:no-repeat;}
.pc-fade{position:absolute;left:0;bottom:0;width:560px;height:340px;background:-webkit-linear-gradient(top,rgba(0,0,0,0),$ink);}
.pc-logo{position:absolute;top:48px;left:180px;width:200px;height:200px;background:#fff7ea;border:8px solid $ink;text-align:center;}
.pc-logo-img{width:184px;height:184px;background-size:contain;background-position:center;background-repeat:no-repeat;}
.pc-logo-ph{line-height:184px;font-size:28px;font-weight:700;color:$ink;letter-spacing:1px;}
.pc-team{position:absolute;left:36px;bottom:48px;width:488px;color:#fff7ea;}
.pc-team-logo{width:120px;height:120px;margin-bottom:8px;background-size:contain;background-position:left center;background-repeat:no-repeat;}
.pc-team-name{font-size:42px;font-weight:700;letter-spacing:1px;line-height:1;text-transform:uppercase;}
.pc-tags{margin-top:10px;font-size:20px;font-weight:700;letter-spacing:1px;}
.pc-right{position:absolute;top:0;left:560px;width:520px;height:1920px;background:#ffffff;padding:120px 36px 48px;}
.pc-player-word{font-size:78px;font-weight:700;font-style:italic;line-height:.9;color:$ink;letter-spacing:1px;}
.pc-reg-word{margin-top:4px;font-size:64px;font-weight:700;font-style:italic;line-height:.9;color:$bright;letter-spacing:1px;}
.pc-tname{margin-top:22px;font-size:22px;font-weight:700;letter-spacing:1px;line-height:1.25;color:#334155;text-transform:uppercase;}
.pc-season{margin-top:4px;font-size:20px;font-weight:700;letter-spacing:2px;color:#334155;text-transform:uppercase;}
.pc-namebar{margin-top:28px;background:$ink;padding:16px 18px 18px;-webkit-transform:skewX(-10deg);}
.pc-nf,.pc-nl{display:inline-block;-webkit-transform:skewX(10deg);font-weight:700;font-style:italic;line-height:1;letter-spacing:1px;text-transform:uppercase;}
.pc-nf{font-size:48px;color:#fff7ea;margin-right:12px;}
.pc-nl{font-size:40px;color:$surname;}
.pc-rows{margin-top:36px;}
.pc-row{display:table;width:100%;margin-top:22px;}
.pc-tile{display:table-cell;width:72px;vertical-align:middle;}
.pc-tile-box{width:56px;height:56px;border-radius:12px;background:$ink;color:#ffffff;text-align:center;line-height:56px;font-size:22px;font-weight:700;}
.pc-meta{display:table-cell;vertical-align:middle;}
.pc-lbl{font-size:16px;font-weight:700;letter-spacing:1px;color:#64748b;text-transform:uppercase;line-height:1;}
.pc-val{margin-top:4px;font-size:28px;font-weight:700;color:#111827;line-height:1.15;}
"""



def _get_default_player_photo(self):
    img_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        'static', 'img', 'default_icon.png'
    )
    with open(img_path, 'rb') as f:
        return base64.b64encode(f.read())
class AuctionTeamPlayer(models.Model):
    _name = 'auction.team.player'
    _description = 'Auction Player'
    _inherit = [
        'auction.image.compress.mixin',
        'auction.tournament.security.mixin',
        'auction.live.snapshot.mixin',
    ]

    # photo: keep near–Stories resolution for sharp Instagram cards.
    _compressible_image_fields = {
        'photo':         (1600, 2200, 98, 'JPEG'),
        'payment_proof': (1200, 1600, 82, 'JPEG'),
    }

    def init(self):
        super().init()
        cr = self.env.cr
        cr.execute("""
            CREATE INDEX IF NOT EXISTS auction_team_player_tourney_stage_idx
            ON auction_team_player (tournament_id, is_on_stage)
        """)
        cr.execute("""
            CREATE INDEX IF NOT EXISTS auction_team_player_tourney_state_idx
            ON auction_team_player (tournament_id, state)
        """)

    @api.model
    def _get_next_tournament_sl_no(self, tournament_id):
        """Next serial number for a tournament (includes archived players)."""
        if tournament_id:
            self.env.cr.execute(
                "SELECT COALESCE(MAX(sl_no), 0) FROM auction_team_player "
                "WHERE tournament_id = %s",
                (tournament_id,),
            )
            return (self.env.cr.fetchone()[0] or 0) + 1
        last = self.with_context(active_test=False).search(
            [], limit=1, order='sl_no desc',
        )
        return (last.sl_no or 0) + 1

    @api.model
    def _sl_no_taken_in_tournament(self, tournament_id, sl_no):
        """True if any live player (draft / auction / sold / unsold) has this serial."""
        if not tournament_id or not sl_no:
            return True
        return bool(self.with_context(active_test=False).search_count([
            ('tournament_id', '=', tournament_id),
            ('sl_no', '=', sl_no),
            ('state', 'in', ('draft', 'auction', 'sold', 'unsold')),
        ]))

    @api.model
    def _get_restore_sl_no(self, tournament_id, original_sl_no):
        """Reuse the old serial if it is free in this tournament; else next number."""
        try:
            original = int(original_sl_no or 0)
        except (TypeError, ValueError):
            original = 0
        if original > 0 and not self._sl_no_taken_in_tournament(tournament_id, original):
            return original
        return self._get_next_tournament_sl_no(tournament_id)

    @api.model
    def default_get(self, fields):
        defaults = super(AuctionTeamPlayer, self).default_get(fields)
        last_record = self.search([],limit=1, order='sl_no desc')
        if last_record:
            defaults.update({'sl_no': last_record.sl_no+1})
        else:
            defaults.update({'sl_no': 1})
        # Auto-populate tournament_id from the logged-in user's profile
        if not defaults.get('tournament_id'):
            user_tournament = self.env.user.tournament_id
            if user_tournament:
                defaults['tournament_id'] = user_tournament.id
        return defaults

    @api.model
    def create(self, vals):
        player = super().create(vals)
        # Auto-close registration when the max limit is reached
        tournament = player.tournament_id
        if tournament and tournament.registration_open and tournament.max_registrations > 0:
            live_count = self.search_count([
                ('tournament_id', '=', tournament.id),
                ('state', 'in', ('draft', 'auction', 'sold', 'unsold')),
            ])
            if live_count >= tournament.max_registrations:
                tournament.sudo().write({'registration_open': False})
        return player

    sl_no = fields.Integer("Sl No")
    name = fields.Char(string="Name of the player", required=True)
    contact = fields.Char("Mobile Number")
    masked_contact = fields.Char(
        "Masked Mobile Number",
        compute='_compute_masked_contact',
        help='Contact number with all digits except the first and last replaced by X.',
    )
    org_id = fields.Char(
        string="Org ID#",
        help="Organisation unique ID provided by the player (optional).",
    )
    address = fields.Text("Address")
    batting_style = fields.Char(string="Batting Style", default='Right Handed Batter')
    bowling_style = fields.Char(string="Bowling Style", default='Right Arm')
    role = fields.Char()

    # ── Football profile (shown when tournament_type == 'football') ──────────
    dominant_position_id = fields.Many2one(
        'auction.player.position', string='Playing Position',
        help='Primary / dominant playing position.')
    secondary_position_ids = fields.Many2many(
        'auction.player.position', 'player_secondary_position_rel',
        'player_id', 'position_id', string='Secondary Position(s)')
    preferred_foot = fields.Selection(
        [('left', 'Left'), ('right', 'Right'), ('both', 'Both')],
        string='Preferred Foot',
        help='Football: preferred foot. Badminton: playing hand (Left/Right).')
    age = fields.Integer(string='Age')
    height = fields.Char(string='Height', help='e.g. 180 cm')
    weight = fields.Char(string='Weight', help='e.g. 75 kg')
    playing_style_ids = fields.Many2many(
        'auction.player.style', 'player_playing_style_rel',
        'player_id', 'style_id', string='Playing Style')
    strength_ids = fields.Many2many(
        'auction.player.strength', 'player_strength_rel',
        'player_id', 'strength_id', string='Strengths')
    work_rate = fields.Selection(
        [('low', 'Low'), ('medium', 'Medium'), ('high', 'High')],
        string='Work Rate')
    # ── Badminton profile (shown when tournament_type == 'badminton') ────────
    badminton_category = fields.Selection(
        [
            ('mens_singles', "Men's Singles"),
            ('mens_doubles', "Men's Doubles"),
            ('womens_singles', "Women's Singles"),
            ('womens_doubles', "Women's Doubles"),
            ('mixed_doubles', 'Mixed Doubles'),
        ],
        string='Category',
        help='Badminton event category (e.g. Men\'s Doubles).',
    )
    badminton_style = fields.Selection(
        [
            ('attacking', 'Attacking'),
            ('defensive', 'Defensive'),
            ('all_round', 'All-round'),
        ],
        string='Style',
        help='Badminton playing style.',
    )
    skill_level = fields.Selection(
        [
            ('beginner', 'Beginner'),
            ('intermediate', 'Intermediate'),
            ('advanced', 'Advanced'),
            ('professional', 'Professional'),
        ],
        string='Level',
        help='Badminton skill level.',
    )
    # ── Kabaddi profile (shown when tournament_type == 'kabaddi') ────────────
    kabaddi_role = fields.Selection(
        [
            ('defender', 'Defender'),
            ('rider', 'Rider'),
            ('all_rounder', 'AllRounder'),
        ],
        string='Role',
        help='Kabaddi role. The human label is copied onto role for generic displays.',
    )

    def kabaddi_role_label(self):
        """Human kabaddi role — Defender, Rider, or AllRounder."""
        self.ensure_one()
        labels = dict(self._fields['kabaddi_role'].selection or [])
        return labels.get(self.kabaddi_role, '') or (self.role or '')

    def _apply_kabaddi_role_label(self, vals):
        """Copy the kabaddi role label onto ``role`` when that selection is written."""
        if not vals.get('kabaddi_role'):
            return vals
        labels = dict(self._fields['kabaddi_role'].selection or [])
        vals = dict(vals)
        vals['role'] = labels.get(vals['kabaddi_role'], vals['kabaddi_role'])
        return vals

    def badminton_card_labels(self):
        """Human labels for badminton profile — used by HUD / PDF / stage cards."""
        self.ensure_one()
        cat_map = dict(self._fields['badminton_category'].selection or [])
        style_map = dict(self._fields['badminton_style'].selection or [])
        level_map = dict(self._fields['skill_level'].selection or [])
        hand_map = {'left': 'Left', 'right': 'Right', 'both': 'Both'}
        return {
            'category': cat_map.get(self.badminton_category, '') if self.badminton_category else '',
            'style': style_map.get(self.badminton_style, '') if self.badminton_style else '',
            'level': level_map.get(self.skill_level, '') if self.skill_level else '',
            'hand': hand_map.get(self.preferred_foot, '') if self.preferred_foot else '',
            'age': self.age or '',
            'strengths': [
                {'name': s.name, 'icon': s.icon or ''}
                for s in self.strength_ids
            ],
        }

    other_attribute_ids = fields.One2many(
        'auction.player.other.attribute', 'player_id',
        string='Additional Attributes',
        help='Answers to the tournament Additional Attributes questionnaire.',
    )
    display_extra_attribute_ids = fields.One2many(
        'auction.player.other.attribute',
        compute='_compute_display_extra_attribute_ids',
        string='Display Additional Attributes',
    )
    use_other_attributes = fields.Boolean(
        string='Has Display Additional Attributes',
        compute='_compute_use_other_attributes',
        help='True when at least one additional attribute is flagged to show '
             'on the player card, projector or live URL.',
    )
    has_extra_attributes = fields.Boolean(
        string='Has Additional Attribute Questions',
        compute='_compute_has_extra_attributes',
    )
    kanban_other_attrs_html = fields.Html(
        string='Other Attributes (Kanban)',
        compute='_compute_kanban_other_attrs_html',
        sanitize=False,
        help='Pre-rendered Other Attribute tiles for the player kanban card.')
    photo = fields.Binary("Photo", default=_get_default_player_photo, prefetch=False)
    squad_poster_crop = fields.Char(
        string="Squad Poster Crop",
        help="JSON crop window {l,t,sw,sh} for squad poster pan/zoom. "
             "Normalized against the full player photo.",
    )
    squad_poster_icon_label = fields.Char(
        string="Squad Poster Icon Label",
        help="Custom text for the gold ICON capsule on the squad poster "
             "(e.g. ICON PLAYER, CAPTAIN). Empty uses the default.",
    )
    photo_card = fields.Binary(
        string='Photo (Card Print)',
        compute='_compute_photo_card',
        store=True,
        prefetch=False,
        help='Resized & compressed JPEG for PDF card printing. Reduces PDF size and generation time.',
    )
    photo_url = fields.Char("Photo URL")
    payment_url = fields.Char("Payment URL")
    state = fields.Selection([('draft', 'Draft'), ('auction', 'In Auction'), ('sold', 'Sold'), ('unsold', 'Unsold')], default='draft', index=True)
    amount_paid = fields.Boolean(default=True)
    active = fields.Boolean(default=True)
    tournament_id = fields.Many2one('auction.tournament', 'Tournament', index=True)
    tournament_type = fields.Selection(related='tournament_id.tournament_type')
    tournament_color = fields.Char(related='tournament_id.kanban_color', string='Tournament Color')
    enable_jersey_section = fields.Boolean(
        related='tournament_id.enable_jersey_section',
        string='Jersey Included',
    )
    assigned_team_id = fields.Many2one('auction.team', 'Team')
    icon_player = fields.Boolean("Key Player")
    is_on_stage = fields.Boolean("Currently on Stage", default=False, index=True,
                                  help="True when this player is actively displayed in the auction stage. Only one player should have this True at a time.")
    tier_id = fields.Many2one(
        'auction.player.tier',
        string='Tier',
        domain="[('tournament_id', '=', tournament_id)]",
    )
    previous_tier_id = fields.Many2one('auction.player.tier', string='Previous Tier', help='Stores the tier before the player was promoted to Icon Player, used to restore on revoke.')
    tier_color = fields.Selection(related='tier_id.color', string='Tier Color')
    is_mystery = fields.Boolean(
        string='Mystery Player',
        related='tier_id.mystery',
        store=False,
        help='True when this player belongs to a Mystery tier.',
    )
    mystery_revealed = fields.Boolean(
        string='Mystery Revealed',
        default=False,
        copy=False,
        help='Set when a Mystery player is revealed on the auction stage after sale. '
             'Used by the live board to know when identity may be shown.',
    )
    base_price = fields.Integer(string='Base Price')
    effective_base_price = fields.Integer(
        string='Effective Base Price',
        compute='_compute_effective_base_price',
    )
    notes = fields.Char()
    #other details
    current_team = fields.Char("Current Team")
    jersy_size = fields.Char('Jersy Size')
    jersy_number = fields.Char("Number in Jersy")
    jersy_name = fields.Char("Name in Jersy")
    jersy_sleeve = fields.Selection(
        [('HS', 'HS'), ('FS', 'FS')],
        string='Sleeve',
        default='HS',
        help='Half Sleeve (HS) or Full Sleeve (FS).',
    )
    track_size = fields.Selection(
        [
            ('S', 'S'),
            ('M', 'M'),
            ('L', 'L'),
            ('XL', 'XL'),
            ('XXL', 'XXL'),
            ('XXXL', 'XXXL'),
            ('4XL', '4XL'),
        ],
        string='Track Size',
        help='Optional track size collected with jersey details.',
    )
    blood_group = fields.Char("Blood Group")
    p_type =   fields.Char("Type")
    payment_proof = fields.Binary("Payment Proof", attachment=True, help="Uploaded payment screenshot/receipt from registration form.")

    @api.depends('contact', 'tournament_id.expose_player_contact')
    def _compute_masked_contact(self):
        for player in self:
            c = player.contact or ''
            if player.tournament_id.expose_player_contact:
                player.masked_contact = c
            elif len(c) > 2:
                player.masked_contact = c[0] + 'X' * (len(c) - 2) + c[-1]
            else:
                player.masked_contact = c

    @api.depends('tournament_id', 'tournament_id.other_attribute_label_ids')
    def _compute_has_extra_attributes(self):
        for player in self:
            player.has_extra_attributes = bool(
                player.tournament_id.other_attribute_label_ids
            )

    def get_display_extra_attributes(self):
        """Answers flagged for public display, capped at 3."""
        Attribute = self.env['auction.player.other.attribute']
        if not self:
            return Attribute
        self.ensure_one()
        shown = Attribute.browse()
        try:
            attrs = self.other_attribute_ids.sorted(
                lambda rec: (rec.sequence or 0, rec.id or 0)
            )
        except Exception:
            attrs = self.other_attribute_ids
        for attr in attrs:
            try:
                definition = attr.definition_id if 'definition_id' in attr._fields else False
                if not definition or not getattr(definition, 'show_on_display', False):
                    continue
                if not (attr.value or '').strip() or not (attr.label or '').strip():
                    continue
                shown |= attr
                if len(shown) >= 3:
                    break
            except Exception:
                continue
        return shown

    def extra_attributes_payload(self, display_only=True):
        if not self:
            return []
        self.ensure_one()
        try:
            recs = (
                self.get_display_extra_attributes()
                if display_only
                else self.other_attribute_ids.sorted(
                    lambda rec: (rec.sequence or 0, rec.id or 0)
                ).filtered(
                    lambda rec: (rec.label or '').strip() and (rec.value or '').strip()
                )
            )
            return [
                {'label': (rec.label or '').strip(), 'value': (rec.value or '').strip()}
                for rec in recs
            ]
        except Exception:
            return []

    @api.depends(
        'other_attribute_ids',
        'other_attribute_ids.value',
        'other_attribute_ids.label',
        'other_attribute_ids.sequence',
        'other_attribute_ids.definition_id',
        'other_attribute_ids.definition_id.show_on_display',
    )
    def _compute_use_other_attributes(self):
        for player in self:
            player.use_other_attributes = bool(player.get_display_extra_attributes())

    @api.depends(
        'other_attribute_ids',
        'other_attribute_ids.value',
        'other_attribute_ids.label',
        'other_attribute_ids.sequence',
        'other_attribute_ids.definition_id',
        'other_attribute_ids.definition_id.show_on_display',
    )
    def _compute_display_extra_attribute_ids(self):
        for player in self:
            player.display_extra_attribute_ids = player.get_display_extra_attributes()

    @api.depends(
        'other_attribute_ids',
        'other_attribute_ids.value',
        'other_attribute_ids.label',
        'other_attribute_ids.sequence',
        'other_attribute_ids.definition_id',
        'other_attribute_ids.definition_id.show_on_display',
    )
    def _compute_kanban_other_attrs_html(self):
        from odoo.tools import html_escape
        for player in self:
            parts = []
            for attr in player.get_display_extra_attributes():
                parts.append(
                    '<div class="pk2-stat">'
                    '<div class="pk2-stat-label">%s</div>'
                    '<div class="pk2-stat-value">%s</div>'
                    '</div>' % (html_escape(attr.label or ''), html_escape(attr.value or ''))
                )
            player.kanban_other_attrs_html = ''.join(parts) or False

    def _sync_other_attributes_from_tournament(self):
        """Ensure every player has an answer row for each tournament question."""
        for player in self:
            tournament = player.tournament_id
            if not tournament:
                continue
            labels = tournament.other_attribute_label_ids.sorted('sequence')
            existing_by_def = {
                attr.definition_id.id: attr
                for attr in player.other_attribute_ids
                if attr.definition_id
            }
            existing_by_label = {
                (attr.label or '').strip().lower(): attr
                for attr in player.other_attribute_ids
            }
            commands = []
            for lab in labels:
                key = (lab.label or '').strip().lower()
                rec = existing_by_def.get(lab.id) or (existing_by_label.get(key) if key else False)
                if rec:
                    updates = {}
                    if rec.definition_id != lab:
                        updates['definition_id'] = lab.id
                    if rec.label != lab.label:
                        updates['label'] = lab.label
                    if rec.sequence != lab.sequence:
                        updates['sequence'] = lab.sequence
                    if updates:
                        commands.append((1, rec.id, updates))
                elif lab.label:
                    commands.append((0, 0, {
                        'definition_id': lab.id,
                        'label': lab.label,
                        'value': '',
                        'sequence': lab.sequence,
                    }))
            if commands:
                player.other_attribute_ids = commands

    @api.onchange('tournament_id')
    def _onchange_tournament_id_sync_other_attrs(self):
        if self.tier_id and (
            not self.tournament_id
            or (self.tier_id.tournament_id and self.tier_id.tournament_id != self.tournament_id)
        ):
            self.tier_id = False
        self._sync_other_attributes_from_tournament()

    @api.constrains('tier_id', 'tournament_id')
    def _check_tier_belongs_to_tournament(self):
        for player in self:
            if (
                player.tier_id
                and player.tournament_id
                and player.tier_id.tournament_id
                and player.tier_id.tournament_id != player.tournament_id
            ):
                raise UserError(_(
                    'Tier "%s" does not belong to tournament "%s". '
                    'Choose a tier from the selected tournament.'
                ) % (player.tier_id.name, player.tournament_id.name))

    def action_sync_other_attributes(self):
        """Manual sync of tournament Additional Attributes onto this player."""
        self._sync_other_attributes_from_tournament()
        return True

    # Card photo frame used by all PDF player-card templates (px).
    _CARD_PHOTO_W = 264
    _CARD_PHOTO_H = 300

    @api.model
    def _make_card_print_jpeg(self, photo_b64):
        """Return a JPEG that exactly fills the card photo frame (cover, top-biased).

        wkhtmltopdf ignores CSS object-fit, so the binary must already match the
        placeholder aspect ratio and pixel size to fill without stretch or gaps.
        """
        if not photo_b64:
            return False
        try:
            from PIL import Image
            import io
            data = base64.b64decode(photo_b64)
            im = Image.open(io.BytesIO(data))
            if im.mode not in ('RGB', 'L'):
                im = im.convert('RGB')
            elif im.mode == 'L':
                im = im.convert('RGB')
            tw, th = self._CARD_PHOTO_W, self._CARD_PHOTO_H
            target_ratio = tw / float(th)
            sw, sh = im.size
            if sw < 1 or sh < 1:
                return False
            src_ratio = sw / float(sh)
            if src_ratio > target_ratio:
                # Wider than frame → crop left/right, keep full height
                new_w = max(1, int(round(sh * target_ratio)))
                left = max(0, (sw - new_w) // 2)
                im = im.crop((left, 0, left + new_w, sh))
            else:
                # Taller / narrower → crop from bottom (keep top / face)
                new_h = max(1, int(round(sw / target_ratio)))
                im = im.crop((0, 0, sw, min(sh, new_h)))
            im = im.resize((tw, th), Image.LANCZOS)
            buf = io.BytesIO()
            im.save(buf, format='JPEG', quality=62, optimize=True)
            return base64.b64encode(buf.getvalue())
        except Exception:
            _logger.debug('Card photo crop failed, falling back to image_process', exc_info=True)
            try:
                return image_process(
                    photo_b64,
                    size=(self._CARD_PHOTO_W, self._CARD_PHOTO_H),
                    crop='top',
                    quality=62,
                    output_format='JPEG',
                )
            except Exception:
                return photo_b64

    @api.depends('photo')
    def _compute_photo_card(self):
        """Cached JPEG that exactly fills the card photo placeholder."""
        for player in self:
            raw = player.photo
            if not raw:
                player.photo_card = False
                continue
            processed = self._make_card_print_jpeg(raw)
            player.photo_card = processed if processed and len(processed) > 32 else raw

    def _get_card_print_photo(self):
        """Binary photo for PDF cards — prefer cached card size, always fall back to original."""
        self.ensure_one()
        card = self.photo_card
        if card and len(card) > 32:
            return card
        if self.photo:
            # On-the-fly crop if stored card photo is missing
            processed = self._make_card_print_jpeg(self.photo)
            if processed and len(processed) > 32:
                return processed
            # Last resort: still downscale so wkhtmltopdf does not embed a
            # multi-MB phone photo as a data URI (very slow for one-card PDF).
            try:
                return image_process(
                    self.photo,
                    size=(self._CARD_PHOTO_W, self._CARD_PHOTO_H),
                    quality=62,
                    output_format='JPEG',
                ) or self.photo
            except Exception:
                return self.photo
        return False

    def _compute_effective_base_price(self):
        """Return the base price for this player from the auction setup.
        Uses the tier-specific base_point if configured, otherwise the global base_point."""
        for player in self:
            auction = self.env['auction.auction'].search(
                [('tournament_id', '=', player.tournament_id.id)], limit=1
            ) if player.tournament_id else self.env['auction.auction'].search([], limit=1)

            if not auction:
                player.effective_base_price = 0
                continue

            base = auction.base_point
            if player.tier_id and auction.tier_limit_ids:
                tier_limit = auction.tier_limit_ids.filtered(
                    lambda l: l.tier_id.id == player.tier_id.id
                )
                if tier_limit and tier_limit[0].base_point > 0:
                    base = tier_limit[0].base_point

            player.effective_base_price = base

    @api.model
    def get_sell_teams_data(self, player_id):
        """Return available teams + auction data for the web sell modal."""
        player = self.browse(int(player_id))

        # ── Tournament-level bid config ───────────────────────────────────
        # Use the player's own tournament (not just any active tournament)
        tournament = player.tournament_id
        tournament_preset_points = []
        tournament_slabs = []
        if tournament:
            if tournament.preset_points:
                try:
                    tournament_preset_points = [
                        int(x.strip())
                        for x in tournament.preset_points.split(',')
                        if x.strip().lstrip('-').isdigit()
                    ]
                except Exception:
                    pass

            splits = tournament.points_split_ids.sorted('points')
            split_list = list(splits)
            for i, split in enumerate(split_list):
                to_amt = (split_list[i + 1].points - 1) if i + 1 < len(split_list) else 99999999
                tournament_slabs.append({
                    'from_amount': split.points,
                    'to_amount': to_amt,
                    'increment': split.no_of_calls,
                })

        # Only show teams that belong to the same tournament as the player
        auction_domain = [('tournament_id', '=', tournament.id)] if tournament else []
        auctions = self.env['auction.auction'].search(auction_domain)
        if auctions:
            auctions.mapped('team_id')
            auctions.mapped('tier_limit_ids.tier_id')
            auctions.mapped('auction_bid_slab_ids')
            auctions.mapped('player_ids.player_id.tier_id')

        sold_by_auction = {}
        if player.tier_id and auctions:
            grouped = self.env['auction.auction.player'].read_group(
                [
                    ('auction_id', 'in', auctions.ids),
                    ('player_id.tier_id', '=', player.tier_id.id),
                    ('player_id', '!=', player.id),
                ],
                ['auction_id'],
                ['auction_id'],
            )
            for grp in grouped:
                if grp.get('auction_id'):
                    sold_by_auction[grp['auction_id'][0]] = grp.get('auction_id_count') or 0

        teams = []
        for auction in auctions:
            if auction.remaining_players_count <= 0 or auction.remaining_points <= 0:
                continue

            # Compute effective base point for this player's tier
            effective_base = auction.base_point
            tier_limit = False
            if player.tier_id and auction.tier_limit_ids:
                tier_limit = auction.tier_limit_ids.filtered(
                    lambda l: l.tier_id.id == player.tier_id.id
                )
                if tier_limit and tier_limit[0].base_point > 0:
                    effective_base = tier_limit[0].base_point

            # Tier limit remaining slots
            # Exclude the current player from the count to avoid stale-record false positives
            # (e.g. if a player was previously sold to this team without proper record cleanup).
            tier_slots_ok = True
            if tier_limit:
                already_sold = sold_by_auction.get(auction.id, 0)
                if already_sold >= tier_limit[0].max_players:
                    tier_slots_ok = False

            # Check the team can actually afford the tier's minimum bid.
            tier_aware_max_call = auction.get_max_bid_for_team(auction, player)
            budget_ok = (effective_base <= tier_aware_max_call)

            # Prefer auction-level bid slabs (set in the wizard Slab Setup).
            # Fall back to tournament point-split slabs if none are configured.
            auction_slabs = [
                {'from_amount': s.from_amount, 'to_amount': s.to_amount, 'increment': s.increment}
                for s in auction.auction_bid_slab_ids.sorted('from_amount')
            ]
            effective_slabs = auction_slabs if auction_slabs else tournament_slabs

            teams.append({
                'team_id': auction.team_id.id,
                'team_name': auction.team_id.name,
                'auction_id': auction.id,
                'remaining_points': auction.remaining_points,
                'remaining_players': auction.remaining_players_count,
                'base_point': auction.base_point,
                'effective_base_point': effective_base,
                'max_call': tier_aware_max_call,
                'tier_slots_ok': tier_slots_ok,
                'budget_ok': budget_ok,
                'preset_points': tournament_preset_points,
                'slabs': effective_slabs,
            })
        teams.sort(key=lambda t: ((t.get('team_name') or '').lower(), t.get('team_id') or 0))
        return {
            'teams': teams,
            'current_bid': int(player.current_bid or 0),
            'current_bid_team_id': (
                player.current_bid_team_id.id if player.current_bid_team_id else False
            ),
        }

    @api.model
    def action_sell_from_web(self, player_id, team_id, final_point):
        """Execute sell from the web auction template. Returns dict with success/error."""
        player = self.browse(int(player_id))
        if not player.exists():
            return {'success': False, 'error': 'Player not found'}

        # Guard: player must still be in auction state
        if player.state == 'sold':
            return {
                'success': False,
                'error': '%s has already been sold. Use "Recall" to correct the sale.' % player.name,
            }
        if player.state != 'auction':
            return {
                'success': False,
                'error': '%s is not available for auction (current state: %s).' % (player.name, player.state),
            }

        # Icon player guard
        icon_players = self.env['auction.team'].search([]).mapped('key_player_ids')
        if player.id in icon_players.ids:
            return {'success': False, 'error': '%s is an icon player and cannot be sold via auction' % player.name}

        auction = self.env['auction.auction'].search([('team_id', '=', int(team_id))], limit=1)
        if not auction:
            return {'success': False, 'error': 'Selected team is not part of the current auction'}

        # Tier limit check
        if player.tier_id and auction.tier_limit_ids:
            tier_limit = auction.tier_limit_ids.filtered(lambda l: l.tier_id.id == player.tier_id.id)
            if tier_limit:
                already_sold = self.env['auction.auction.player'].search_count([
                    ('auction_id', '=', auction.id),
                    ('player_id.tier_id', '=', player.tier_id.id),
                ])
                if already_sold >= tier_limit[0].max_players:
                    return {
                        'success': False,
                        'error': '%s has already reached the maximum of %d player(s) from the "%s" tier' % (
                            auction.team_id.name, tier_limit[0].max_players, player.tier_id.name
                        )
                    }

        # Effective base point (tier-specific)
        effective_base = auction.base_point
        if player.tier_id and auction.tier_limit_ids:
            tier_limit = auction.tier_limit_ids.filtered(lambda l: l.tier_id.id == player.tier_id.id)
            if tier_limit and tier_limit[0].base_point > 0:
                effective_base = tier_limit[0].base_point

        if final_point < effective_base:
            return {'success': False, 'error': 'Points cannot be below the base point of %d' % effective_base}

        # Purse must cover the tier's minimum bid
        if player.tier_id and auction.tier_limit_ids:
            _tl_min = auction.tier_limit_ids.filtered(lambda l: l.tier_id.id == player.tier_id.id)
            _tier_min = (_tl_min[0].base_point if _tl_min and _tl_min[0].base_point > 0
                         else (auction.base_point or 0))
            if _tier_min > 0 and auction.remaining_points < _tier_min:
                return {
                    'success': False,
                    'error': 'Insufficient purse for "%s" tier (requires %d pts, team has %d pts)' % (
                        player.tier_id.name, _tier_min, auction.remaining_points
                    ),
                }

        # Tier-aware max call check (covers per-tier budget reserves + tier max_call cap + slab snapping)
        tier_aware_max_call = auction.get_max_bid_for_team(auction, player)
        if final_point > tier_aware_max_call:
            return {
                'success': False,
                'error': 'Points exceed the max call of %d pts for this team' % tier_aware_max_call,
            }

        # Max points cap (global auction ceiling)
        if auction.max_limited == 'yes' and final_point > auction.max_points:
            return {'success': False, 'error': 'Points exceed the auction cap of %d' % auction.max_points}

        # Execute the sell
        auction_line_data = {'player_id': player.id, 'points': final_point}
        is_mystery = bool(player.tier_id and player.tier_id.mystery)
        display_name = '???' if is_mystery else (player.name or '')
        message = '%s sold to %s for %s!' % (
            display_name, auction.team_id.name, player._history_value(final_point)
        )

        auction.player_ids = [(0, 0, auction_line_data)]
        player.assigned_team_id = auction.team_id.id
        player.state = 'sold'
        if is_mystery:
            player.mystery_revealed = False
        # is_on_stage stays True so the live board can show the SOLD stamp
        # until the next player is called via get_random_player()
        player.create_auction_history(auction.team_id.id, message, tournament_id=player.tournament_id.id, player=player)

        # ── Stamp: record on tournament for the live board ──
        if player.tournament_id:
            from datetime import timedelta
            stamp_secs = player.tournament_id.result_stamp_hold_seconds(is_mystery=is_mystery)
            player.tournament_id.sudo().write({
                'stamp_player_id': player.id,
                'stamp_state': 'sold',
                'stamp_expires_at': fields.Datetime.now() + timedelta(seconds=stamp_secs),
            })

        # Notify operators with real name; live board uses the ??? history message
        notify_msg = '%s sold to %s for %s!' % (
            player.name, auction.team_id.name, player._history_value(final_point)
        )
        self.env.user.notify_success(message=notify_msg, title='CONGRATULATIONS!')
        queue_remaining = 0
        if player.tournament_id:
            queue_remaining = self.search_count([
                ('tournament_id', '=', player.tournament_id.id),
                ('state', '=', 'auction'),
                ('icon_player', '=', False),
            ])
        return {
            'success': True,
            'message': notify_msg,
            'player_id': player.id,
            'player_name': player.name,
            'team_id': auction.team_id.id,
            'team_name': auction.team_id.name,
            'final_point': final_point,
            'display_seconds': player.tournament_id.sold_display_seconds if player.tournament_id else 5,
            'tournament_id': player.tournament_id.id if player.tournament_id else False,
            'queue_remaining': queue_remaining,
        }

    @api.model
    def action_reveal_mystery(self, player_id=None):
        """Reveal a Mystery player's identity after sale (display_auction + live board).

        Prefer calling with ``player_id`` from the web console_call endpoint.
        Does not replay the SOLD stamp — that is reserved for the sale moment.
        Returns ``{'success': True, 'player_name': ...}`` on success.
        """
        if not player_id:
            return {'success': False, 'error': 'missing player'}
        player = self.browse(int(player_id))
        if not player.exists():
            return {'success': False, 'error': 'player not found'}
        if not (player.tier_id and player.tier_id.mystery):
            return {'success': False, 'error': 'not a mystery player'}
        player.sudo().write({'mystery_revealed': True})
        # Unmask live-board transaction history for this player
        try:
            History = self.env['auction.history'].sudo()
            histories = History.search([('player_id', '=', player.id)])
            for hist in histories:
                msg = hist.message or ''
                if '???' in msg:
                    msg = msg.replace('???', player.name or '???', 1)
                hist.write({
                    'message': msg,
                    'player_photo': player.photo,
                })
        except Exception:
            # History unmask is best-effort — reveal flag is already set
            _logger = logging.getLogger(__name__)
            _logger.exception('Failed to unmask mystery history for player %s', player.id)
        # Reveal identity only — do not replay the SOLD stamp (that is for the
        # sale moment). Clear any lingering stamp so projector/live board show
        # the revealed photo without the sold overlay returning.
        if player.tournament_id and player.state == 'sold':
            tournament = player.tournament_id.sudo()
            if tournament.stamp_player_id and tournament.stamp_player_id.id == player.id:
                tournament.write({
                    'stamp_player_id': False,
                    'stamp_state': False,
                    'stamp_expires_at': False,
                })
        return {
            'success': True,
            'player_id': player.id,
            'player_name': player.name or '',
        }

    def print_player_cards(self):
        # Always print in serial-number order. Selection / mapped() recordsets
        # follow click order or player.id (model has no _order), so #12 can
        # appear before #3 unless we sort here.
        self = self.sorted(lambda p: (p.sl_no or 0, p.name or '', p.id))
        # Refresh print photos so crop/size matches the card frame (wkhtmltopdf
        # ignores object-fit; pre-cropped JPEGs prevent stretch).
        with_photo = self.filtered('photo')
        if with_photo:
            with_photo._compute_photo_card()
            with_photo.flush(['photo_card'])
        # Use the player's own tournament theme, not the globally "active" tournament
        tournament = self[0].tournament_id if self else None
        if tournament and tournament.logo and not tournament.logo_card:
            tournament._compute_logo_card()
            tournament.flush(['logo_card'])
        # Football has its own card format/paperformat (theme-aware internally)
        if tournament and tournament.tournament_type in ('football', 'badminton', 'kabaddi'):
            return self.env.ref('auction_module.action_report_player_card_football').report_action(self)
        template = tournament.player_display_template if tournament else 'vanilla'
        report_map = {
            'vanilla':       'auction_module.action_report_player_card',
            'butterscotch':  'auction_module.action_report_player_card_butterscotch',
            'strawberry':    'auction_module.action_report_player_card_strawberry',
            'cherry':        'auction_module.action_report_player_card_cherry',
            'pistah':        'auction_module.action_report_player_card_pistah',
            'lemon':         'auction_module.action_report_player_card_lemon',
            'standard':      'auction_module.action_report_player_card_standard',
            'blackberry':    'auction_module.action_report_player_card_blackberry_matte',
            'blueberry':     'auction_module.action_report_player_card_blackberry',
        }
        report_ref = report_map.get(template, 'auction_module.action_report_player_card')
        return self.env.ref(report_ref).report_action(self)


    # ══════════════════════════════════════════════════════════════════
    #  Bulk Instagram Stories / Status player-card export (ZIP of JPGs)
    #  Renders a premium 1080×1920 (9:16) stadium-backed social card
    #  per player via wkhtmltoimage and streams a ZIP to the browser.
    # ══════════════════════════════════════════════════════════════════
    _CARD_W = 1080
    _CARD_H = 1350
    # Fixed portrait box. Every player photo is cropped to this size
    # before it is placed, so the source photo cannot change the poster.
    # 1080×1350 is the Instagram feed portrait (4:5). A 9:16 story is
    # cropped in the feed and cuts off the heading.
    _PHOTO_W = 580
    _PHOTO_H = 1350
    _PORTRAIT_CSS = None
    _FACE_DET = None
    _CARD_FONT_FILES = (
        ('__FONT_BANGERS__', 'Bangers-Regular.ttf'),
        ('__FONT_ANTON__', 'Anton-Regular.ttf'),
        ('__FONT_OSWALD__', 'Oswald-Bold.ttf'),
        ('__FONT_MONTSERRAT__', 'Montserrat-Bold.ttf'),
    )
    _BRAND_LOGO = None
    # Projector / display_auction palette.
    # ink = --gold (primary), bright = --amber (secondary), paper = --navy.
    # Light editions (lemon, strawberry, standard) keep the light projector paper.
    _CARD_PAINTS = {
        'standard': {
            'ink': '#1058B0', 'bright': '#F5A623', 'paper': '#FFFFFF',
            'panel': '#F3F7FC', 'label': '#5B7BA6', 'value': '#1A202C',
            'onbar': '#FFFFFF', 'surname': '#F5A623',
        },
        'butterscotch': {
            'ink': '#F5C842', 'bright': '#FF9F1C', 'paper': '#070B14',
            'panel': '#0C1120', 'label': '#C9B27A', 'value': '#FFFFFF',
            'onbar': '#070B14', 'surname': '#3A2A08',
        },
        'cherry': {
            'ink': '#E11D48', 'bright': '#FB7185', 'paper': '#070104',
            'panel': '#12060A', 'label': '#E7A8B4', 'value': '#FFFFFF',
            'onbar': '#1A0408', 'surname': '#FFE4E8',
        },
        'vanilla': {
            'ink': '#C4B8A0', 'bright': '#8AA6D4', 'paper': '#0D1524',
            'panel': '#142036', 'label': '#C4B8A0', 'value': '#FFFFFF',
            'onbar': '#121820', 'surname': '#1A2744',
        },
        'pistah': {
            'ink': '#6BBF4E', 'bright': '#A8E063', 'paper': '#060E08',
            'panel': '#0B1A0E', 'label': '#A8D4A0', 'value': '#FFFFFF',
            'onbar': '#061208', 'surname': '#0B3D12',
        },
        'blueberry': {
            'ink': '#3B82F6', 'bright': '#93C5FD', 'paper': '#050A14',
            'panel': '#0A1220', 'label': '#93C5FD', 'value': '#FFFFFF',
            'onbar': '#050A14', 'surname': '#DBEAFE',
        },
        'blackberry': {
            'ink': '#7629D9', 'bright': '#A77BFF', 'paper': '#101113',
            'panel': '#222328', 'label': '#BFC3CC', 'value': '#FFFFFF',
            'onbar': '#FFFFFF', 'surname': '#E4D4FF',
        },
        'lemon': {
            'ink': '#C9A400', 'bright': '#8F7400', 'paper': '#FDF8EF',
            'panel': '#FFFFFF', 'label': '#8F7400', 'value': '#1A1000',
            'onbar': '#1A1608', 'surname': '#3A3008',
        },
        'strawberry': {
            'ink': '#C2185B', 'bright': '#E91E63', 'paper': '#FFF0F5',
            'panel': '#FFFFFF', 'label': '#880E4F', 'value': '#1A0A12',
            'onbar': '#FFFFFF', 'surname': '#FCE4EC',
        },
    }
    _CARD_EDITIONS = {
        'butterscotch': 'Butterscotch Edition',
        'cherry': 'Cherry Edition',
        'vanilla': 'Vanilla Edition',
        'pistah': 'Pistah Edition',
        'blueberry': 'Blueberry Edition',
        'blackberry': 'Blackberry Edition',
        'lemon': 'Lemon Edition',
        'strawberry': 'Strawberry Edition',
        'standard': 'Standard Edition',
    }
    _CARD_LIGHT_THEMES = ('lemon', 'strawberry', 'standard')

    _FOOT_LABELS = {'left': 'Left Foot', 'right': 'Right Foot', 'both': 'Both Feet'}

    _CARD_ICONS = {
        'bat': '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M14.5 3.5l6 6"/><path d="M18 6l-9.5 9.5"/><path d="M8.5 15.5l-4.2 4.2a1.5 1.5 0 01-2.1-2.1L6.4 13.4z"/><circle cx="5" cy="19" r="0.6" fill="currentColor"/></svg>',
        'ball': '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><circle cx="12" cy="12" r="8.5"/><path d="M12 3.5v17"/><path d="M9 4.2c1.6 4.8 1.6 10.8 0 15.6M15 4.2c-1.6 4.8-1.6 10.8 0 15.6" stroke-dasharray="2 2"/></svg>',
        'position': '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><circle cx="12" cy="12" r="8.5"/><circle cx="12" cy="12" r="4"/><circle cx="12" cy="12" r="0.8" fill="currentColor"/></svg>',
        'foot': '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"><path d="M8 3c1.6 0 2.5 1.4 2.7 3.2.2 1.8.5 3.3 1.4 4.6.8 1.2 1.9 2 1.9 3.9 0 2.4-1.8 4.3-4.3 4.3-2.2 0-3.7-1.4-3.7-3.6 0-1.3.3-2.2.3-3.6C6.3 12 5 9.4 5 6.8 5 4.6 6.2 3 8 3z"/></svg>',
        'age': '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"><rect x="3.5" y="5" width="17" height="15.5" rx="2.2"/><path d="M3.5 9.5h17M8 3v4M16 3v4"/></svg>',
        'category': '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"><path d="M20.5 12.5l-8 8-9-9V4h7.5z"/><circle cx="8" cy="8" r="1.4" fill="currentColor"/></svg>',
        'user': '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"><circle cx="12" cy="8" r="3.2"/><path d="M5.5 19.5c1.2-3.2 3.4-4.8 6.5-4.8s5.3 1.6 6.5 4.8"/></svg>',
        'location': '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"><path d="M12 21.5c4.5-4.8 7-8.3 7-11.5a7 7 0 10-14 0c0 3.2 2.5 6.7 7 11.5z"/><circle cx="12" cy="10" r="2.6"/></svg>',
        'nation': '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c2.5 2.8 3.8 5.8 3.8 9s-1.3 6.2-3.8 9c-2.5-2.8-3.8-5.8-3.8-9S9.5 5.8 12 3z"/></svg>',
        'price': '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="8.5"/><path d="M9 8h6M9 11h6M14 8c0 3-2 4-4.5 4L15 16.5"/></svg>',
        'team': '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"><path d="M12 3l7 2.5v5c0 4.5-3 8-7 9.5-4-1.5-7-5-7-9.5v-5z"/><path d="M9.5 12l1.8 1.8 3.5-3.6"/></svg>',
        'height': '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"><path d="M12 3v18M8 6l4-3 4 3M8 18l4 3 4-3"/></svg>',
        'phone': '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M6.6 3.5H5.5A2 2 0 003.5 5.5c0 7.7 6.3 14 14 14a2 2 0 002-2v-1.1a2 2 0 00-1.3-1.9l-2.5-.8a2 2 0 00-2 .5l-.7.7a13.8 13.8 0 01-6.3-6.3l.7-.7a2 2 0 00.5-2l-.8-2.5a2 2 0 00-1.9-1.4z"/></svg>',
        'jersey': '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6.5L6.5 3H10v1.5L12 3l2 1.5V3h3.5L21 6.5l-3.5 2V21H6.5V8.5L3 6.5z"/></svg>',
    }

    _STADIUM_CACHE = {}

    _CARD_THEMES = {
        'vanilla':      {'bg1': '#0b1c3c', 'bg2': '#040a17', 'bg3': '#16346a', 'accent': '#e9c15a', 'accent2': '#ffe6a0', 'accentD': '#a9781f', 'txt': '#eef3fb', 'sub': '#9fb2d4', 'badge1': '#e0349b', 'badge2': '#7d1f6b'},
        'butterscotch': {'bg1': '#2a1c08', 'bg2': '#120b03', 'bg3': '#4a3210', 'accent': '#f5c842', 'accent2': '#ffe89a', 'accentD': '#b3801f', 'txt': '#fff7e6', 'sub': '#d8b98a', 'badge1': '#f5a623', 'badge2': '#8a4b0f'},
        'strawberry':   {'bg1': '#3a0f22', 'bg2': '#1c0710', 'bg3': '#5f1a38', 'accent': '#ff9bbb', 'accent2': '#ffd6a8', 'accentD': '#c2185b', 'txt': '#ffeaf3', 'sub': '#e5a9c2', 'badge1': '#ff4d84', 'badge2': '#7a1030'},
        'cherry':       {'bg1': '#2a0509', 'bg2': '#140203', 'bg3': '#4a0a13', 'accent': '#f5c842', 'accent2': '#ffdd88', 'accentD': '#9a0f22', 'txt': '#ffecec', 'sub': '#e0a0a8', 'badge1': '#e01e37', 'badge2': '#5a0810'},
        'pistah':       {'bg1': '#0e2a15', 'bg2': '#05130a', 'bg3': '#1c4d2a', 'accent': '#d4e157', 'accent2': '#eaff9a', 'accentD': '#2f7d32', 'txt': '#ecfce8', 'sub': '#a7d1a0', 'badge1': '#7cb342', 'badge2': '#1b4a1e'},
        'lemon':        {'bg1': '#1a1e10', 'bg2': '#0c0e08', 'bg3': '#2a3218', 'accent': '#D9B820', 'accent2': '#E8D48A', 'accentD': '#8F7400', 'txt': '#fff6d6', 'sub': '#d4c078', 'badge1': '#C9A400', 'badge2': '#6E5A00'},
        'standard':     {'bg1': '#1058B0', 'bg2': '#1058B0', 'bg3': '#1058B0', 'accent': '#FFFFFF', 'accent2': '#FFFFFF', 'accentD': '#1058B0', 'txt': '#FFFFFF', 'sub': '#FFFFFF', 'badge1': '#1058B0', 'badge2': '#1058B0'},
        'blackberry':   {'bg1': '#101113', 'bg2': '#222328', 'bg3': '#303137', 'accent': '#7629D9', 'accent2': '#A77BFF', 'accentD': '#4C1D95', 'txt': '#FFFFFF', 'sub': '#BFC3CC', 'badge1': '#7629D9', 'badge2': '#4C1D95'},
        'blueberry':    {'bg1': '#0a1628', 'bg2': '#050a14', 'bg3': '#14305f', 'accent': '#60a5fa', 'accent2': '#93c5fd', 'accentD': '#1e3a8a', 'txt': '#ffffff', 'sub': '#93c5fd', 'badge1': '#3b82f6', 'badge2': '#0f285f'},
    }

    def _card_render_binary(self):
        import shutil
        for cand in ('/usr/local/bin/wkhtmltoimage', '/usr/bin/wkhtmltoimage', 'wkhtmltoimage'):
            path = cand if os.path.isabs(cand) else shutil.which(cand)
            if path and os.path.exists(path):
                return path
        return None

    def _card_workdir(self):
        """A private temp working dir for the HTML/JPG intermediates."""
        import tempfile
        return tempfile.mkdtemp(prefix='ac_cards_')

    def _card_stadium_uri(self, is_football):
        """Night stadium with floodlights, used behind the player photo."""
        key = 'night'
        cached = self._STADIUM_CACHE.get(key)
        if cached:
            return cached
        fname = 'top5_stadium_night.jpg'
        path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'static', 'img', fname)
        try:
            with open(path, 'rb') as fh:
                uri = 'data:image/jpeg;base64,' + base64.b64encode(fh.read()).decode('ascii')
        except Exception:
            uri = ''
        self._STADIUM_CACHE[key] = uri
        return uri

    def _card_poster_wash_uri(self, tournament, paper='#FFFFFF'):
        """Very light poster (or stadium) wash, tinted to the theme paper."""
        from io import BytesIO
        from PIL import Image
        paper = (paper or '#FFFFFF').upper()
        key = 'stadium'
        binary = False
        if tournament and tournament.poster_image:
            key = 'poster-%s-%s' % (tournament.id, tournament.write_date or '')
            binary = tournament.poster_image
        cache_key = 'wash-%s-%s' % (key, paper)
        cached = self._STADIUM_CACHE.get(cache_key)
        if cached:
            return cached
        try:
            if binary:
                raw = base64.b64decode(binary)
                im = Image.open(BytesIO(raw))
            else:
                path = os.path.join(
                    os.path.dirname(os.path.dirname(__file__)),
                    'static', 'img', 'top5_stadium_night.jpg')
                im = Image.open(path)
            im = im.convert('RGB')
            tw, th = 1000, 2700
            sw, sh = im.size
            scale = max(tw / float(sw or 1), th / float(sh or 1))
            nw, nh = max(1, int(sw * scale)), max(1, int(sh * scale))
            try:
                resample = Image.Resampling.LANCZOS
            except AttributeError:
                resample = Image.LANCZOS
            im = im.resize((nw, nh), resample)
            left = max(0, (nw - tw) // 2)
            top = max(0, (nh - th) // 2)
            im = im.crop((left, top, left + tw, top + th))
            hex_paper = paper[1:] if paper.startswith('#') else paper
            if len(hex_paper) != 6:
                rgb = (255, 255, 255)
            else:
                rgb = tuple(int(hex_paper[i:i + 2], 16) for i in (0, 2, 4))
            tint = Image.new('RGB', im.size, rgb)
            im = Image.blend(tint, im, 0.16)
            out = BytesIO()
            im.save(out, format='JPEG', quality=72, optimize=True)
            uri = 'data:image/jpeg;base64,' + base64.b64encode(out.getvalue()).decode('ascii')
        except Exception:
            _logger.debug('Player card poster wash failed', exc_info=True)
            uri = ''
        self._STADIUM_CACHE[cache_key] = uri
        return uri

    @staticmethod
    def _card_player_id_label(player, team, tournament):
        """Build a short PLAYER ID like RR-037 from team/tournament initials."""
        source = ''
        if team and team.name:
            source = team.name
        elif tournament and tournament.name:
            source = tournament.name
        letters = re.sub(r'[^A-Za-z]', '', source or '')[:3].upper() or 'AC'
        num = player.sl_no or (player.id % 1000) or 0
        return '%s-%03d' % (letters, int(num))

    def _card_portrait_css(self, paint):
        """Poster CSS with fonts inlined and the tournament theme painted in."""
        import string
        raw = type(self)._PORTRAIT_CSS
        if not raw:
            base = os.path.dirname(os.path.dirname(__file__))
            css_path = os.path.join(base, 'static', 'src', 'css', 'player_card_portrait.css')
            with open(css_path, 'r', encoding='utf-8') as fh:
                raw = fh.read()
            font_dir = os.path.join(base, 'static', 'src', 'assets', 'fonts')
            for token, fname in self._CARD_FONT_FILES:
                with open(os.path.join(font_dir, fname), 'rb') as fh:
                    uri = 'data:font/truetype;base64,' + base64.b64encode(fh.read()).decode('ascii')
                raw = raw.replace(token, uri)
            type(self)._PORTRAIT_CSS = raw
        return string.Template(raw).safe_substitute(paint)

    def _card_brand_logo_uri(self, on_light=True):
        """Navy wordmark on light paper, white wordmark on dark projector paper."""
        cache = type(self)._BRAND_LOGO
        if not isinstance(cache, dict):
            cache = {}
            type(self)._BRAND_LOGO = cache
        key = 'light' if on_light else 'dark'
        if key not in cache:
            cache[key] = self.env['auction.point.unit'].sudo().report_brand_logo_data_uri(
                dark=on_light) or ''
        return cache[key]

    def _detect_face_box(self, im):
        """Return (x, y, w, h) of the largest face, or None."""
        try:
            import cv2
            import numpy as np
        except Exception:
            return None
        model = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            'data', 'face_detection_yunet_2023mar.onnx')
        if not os.path.exists(model):
            return None
        width, height = im.size
        scale = min(1.0, 800.0 / float(max(width, height) or 1))
        arr = np.asarray(im.convert('RGB'), dtype=np.uint8)
        bgr = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
        if scale < 1:
            bgr = cv2.resize(bgr, (max(1, int(width * scale)), max(1, int(height * scale))))
        sh, sw = bgr.shape[:2]
        det = type(self)._FACE_DET
        try:
            if det is None:
                det = cv2.FaceDetectorYN.create(model, '', (sw, sh), 0.55, 0.3, 5000)
                type(self)._FACE_DET = det
            else:
                det.setInputSize((sw, sh))
            _, faces = det.detect(bgr)
        except Exception:
            _logger.debug('Player card face detection failed', exc_info=True)
            return None
        if faces is None or len(faces) == 0:
            return None
        best = max(faces, key=lambda face: float(face[2]) * float(face[3]))
        inv = 1.0 / scale
        return (
            float(best[0]) * inv, float(best[1]) * inv,
            float(best[2]) * inv, float(best[3]) * inv,
        )

    def _card_portrait_crop(self, im):
        """Crop to the fixed portrait box, keeping the face in the upper third.

        The returned image is always the same pixel size, so a square, landscape,
        close-up, or full-body source cannot change the poster.
        """
        from PIL import Image
        try:
            resample = Image.Resampling.LANCZOS
        except AttributeError:
            resample = Image.LANCZOS
        tw, th = self._PHOTO_W * 2, self._PHOTO_H * 2
        ratio = tw / float(th)
        im = im.convert('RGB')
        iw, ih = im.size
        if iw < 2 or ih < 2:
            return im.resize((tw, th), resample)
        face = self._detect_face_box(im)
        if face:
            x, y, fw, fh = face
            ax = x + fw / 2.0
            ay = y + fh / 2.0
            want_w = max(fw * 3.2, iw * 0.42)
        else:
            ax = iw / 2.0
            ay = ih * 0.28
            want_w = iw * 0.94
        want_h = want_w / ratio
        if want_w > iw or want_h > ih:
            if (iw / float(ih)) > ratio:
                want_h = float(ih)
                want_w = want_h * ratio
            else:
                want_w = float(iw)
                want_h = want_w / ratio
        left = ax - want_w / 2.0
        top = ay - (0.30 * want_h)
        left = min(max(0.0, left), max(0.0, iw - want_w))
        top = min(max(0.0, top), max(0.0, ih - want_h))
        box = (
            int(round(left)), int(round(top)),
            int(round(left + want_w)), int(round(top + want_h)),
        )
        box = (
            max(0, min(box[0], iw - 1)),
            max(0, min(box[1], ih - 1)),
            max(1, min(box[2], iw)),
            max(1, min(box[3], ih)),
        )
        cropped = im.crop(box)
        if cropped.size != (tw, th):
            cropped = cropped.resize((tw, th), resample)
        return cropped

    def _card_social_photo(self, binary_photo):
        """Face-cropped portrait at the fixed card size, as base64 JPEG."""
        if not binary_photo:
            return binary_photo
        try:
            from io import BytesIO
            from PIL import Image, ImageOps, ImageEnhance, ImageFilter
            raw = base64.b64decode(binary_photo)
            im = Image.open(BytesIO(raw))
            try:
                im = ImageOps.exif_transpose(im)
            except Exception:
                pass
            im = self._card_portrait_crop(im)
            im = ImageEnhance.Contrast(im).enhance(1.06)
            im = ImageEnhance.Sharpness(im).enhance(1.2)
            im = im.filter(ImageFilter.UnsharpMask(radius=1.2, percent=120, threshold=2))
            out = BytesIO()
            im.save(out, format='JPEG', quality=92, optimize=True, progressive=False,
                    subsampling=0, dpi=(72, 72))
            return base64.b64encode(out.getvalue())
        except Exception:
            _logger.debug('Social photo crop failed; using original', exc_info=True)
            try:
                return image_process(
                    binary_photo, size=(self._PHOTO_W * 2, self._PHOTO_H * 2), quality=90)
            except Exception:
                return binary_photo

    @staticmethod
    def _card_indian_amount(amount):
        try:
            n = int(amount or 0)
        except (TypeError, ValueError):
            return str(amount or '')
        s = str(n)
        if len(s) <= 3:
            return s
        last3, rest = s[-3:], s[:-3]
        rest = re.sub(r'(\d)(?=(\d\d)+$)', r'\1,', rest)
        return rest + ',' + last3

    @staticmethod
    def _card_format_price(amount):
        """Format an integer amount as Indian Rupee string.
        ≥1 Cr  → ₹X.XX Cr
        ≥1 Lakh → ₹X.XX Lakh
        else   → ₹X,XX,XXX
        """
        try:
            n = int(amount or 0)
        except (TypeError, ValueError):
            return u'\u20b9' + str(amount or '0')
        if n == 0:
            return u'\u20b90'
        if n >= 10000000:
            return u'\u20b9%.2f Cr' % (n / 10000000.0)
        if n >= 100000:
            return u'\u20b9%.2f Lakh' % (n / 100000.0)
        s = str(n)
        if len(s) <= 3:
            return u'\u20b9' + s
        last3, rest = s[-3:], s[:-3]
        rest = re.sub(r'(\d)(?=(\d\d)+$)', r'\1,', rest)
        return u'\u20b9' + rest + ',' + last3

    @staticmethod
    def _card_safe_filename(name, used):
        base = re.sub(r'[^A-Za-z0-9]+', '_', (name or 'Player').strip()).strip('_') or 'Player'
        candidate = base
        i = 1
        while candidate.lower() in used:
            i += 1
            candidate = '%s_%d' % (base, i)
        used.add(candidate.lower())
        return candidate + '.jpg'

    def _card_values(self, player):
        tournament = player.tournament_id
        team = player.assigned_team_id
        is_football = bool(tournament and tournament.tournament_type == 'football')
        is_badminton = bool(tournament and tournament.tournament_type == 'badminton')
        is_kabaddi = bool(tournament and tournament.tournament_type == 'kabaddi')
        theme = (tournament.player_display_template if tournament else False) or 'vanilla'
        pal = dict(self._CARD_THEMES.get(theme, self._CARD_THEMES['vanilla']))

        name = (player.name or '').strip().upper()
        parts = name.split()
        if len(parts) > 1:
            name_first, name_last = ' '.join(parts[:-1]), parts[-1]
        else:
            name_first, name_last = '', name or 'PLAYER'

        card_id = self._card_player_id_label(player, team, tournament)
        brand_name = (team.name if team and team.name else (tournament.name if tournament else 'AuctionChamp')) or 'AuctionChamp'

        if is_football:
            badge = (player.dominant_position_id.name if player.dominant_position_id
                     else (player.role or 'PLAYER'))
        elif is_badminton:
            cat_map = dict(player._fields['badminton_category'].selection or [])
            badge = cat_map.get(player.badminton_category) or player.role or 'PLAYER'
        elif is_kabaddi:
            badge = player.tier_id.name if player.tier_id else ''
        else:
            badge = player.role or 'PLAYER'

        # ── Sold points — used for price cell when sold ──
        sold_points = 0
        if player.state == 'sold':
            auction_line = self.env['auction.auction.player'].search(
                [('player_id', '=', player.id)], limit=1, order='id desc')
            sold_points = auction_line.points if auction_line else 0

        if player.state == 'sold' and sold_points:
            price_label = 'Sold For'
            price_display = self._card_format_price(sold_points)
        elif player.effective_base_price:
            price_label = 'Base Price'
            price_display = self._card_format_price(player.effective_base_price)
        else:
            price_label = 'Base Price'
            price_display = u'\u20b9—'

        _status_cfg = {
            'sold':    {'text': 'SOLD',           'color': '#C62828'},
            'unsold':  {'text': 'UNSOLD',         'color': '#424242'},
            'auction': {'text': 'IN AUCTION',     'color': '#E65100'},
            'draft':   {'text': 'REGISTERED',     'color': '#1565C0'},
        }
        _st = _status_cfg.get(player.state or 'draft', _status_cfg['draft'])
        player_state = player.state or 'draft'
        is_sold = player_state == 'sold'
        status_word = 'SOLD' if is_sold else 'REGISTERED'
        sold_points_label = ''
        if is_sold and tournament and sold_points:
            try:
                sold_points_label = tournament.format_points(sold_points) or ''
            except Exception:
                sold_points_label = '{:,}'.format(int(sold_points))
        show_stamp = player_state in ('sold', 'unsold')
        # Corner chip only for draft / in-auction — sold/unsold use the photo stamp
        show_status = player_state in ('draft', 'auction')

        stamp_title = 'SOLD' if player_state == 'sold' else 'UNSOLD'
        stamp_amount = price_display if player_state == 'sold' else 'UNSOLD'
        if player_state == 'sold' and team and team.name:
            stamp_sub = 'TO ' + team.name.upper()
        elif player_state == 'unsold':
            stamp_sub = ''
        else:
            stamp_sub = ''

        # Sport profile plus this tournament's own answered attributes.
        # Empty answers are omitted. No padded nationality, price, or team row.
        rows = []
        seen_labels = set()
        icon_for = {
            'role': 'user',
            'category': 'user',
            'batting': 'bat',
            'bowling': 'ball',
            'position': 'position',
            'preferred foot': 'foot',
            'hand': 'foot',
            'style': 'bat',
            'level': 'category',
            'age': 'age',
            'location': 'location',
            'height': 'height',
            'jersey': 'jersey',
            'number': 'jersey',
            'club': 'team',
        }

        def add_row(label, value):
            label = (label or '').strip()
            if isinstance(value, int):
                value = str(value) if value else ''
            value = (value or '').strip()
            key = label.lower()
            if not label or not value or value in ('—', '-', 'None') or key in seen_labels:
                return
            seen_labels.add(key)
            rows.append({
                'mark': label[:1].upper(),
                'label': label,
                'value': value,
                'icon': icon_for.get(key, 'category'),
            })

        if is_football:
            add_row('Position', player.dominant_position_id.name if player.dominant_position_id else player.role)
            if player.preferred_foot:
                add_row('Preferred Foot', self._FOOT_LABELS.get(player.preferred_foot, player.preferred_foot.title()))
            add_row('Height', player.height)
        elif is_badminton:
            labels = player.badminton_card_labels()
            add_row('Category', labels.get('category'))
            add_row('Hand', labels.get('hand'))
            add_row('Style', labels.get('style'))
            add_row('Level', labels.get('level'))
        elif is_kabaddi:
            add_row('Role', player.kabaddi_role_label())
            add_row('Club', player.current_team)
        else:
            add_row('Category', player.role)
            add_row('Batting', player.batting_style)
            add_row('Bowling', player.bowling_style)
        if player.age:
            add_row('Age', '%d' % player.age)
        location = ((player.address or '').splitlines() or [''])[0].strip()
        if len(location) > 32:
            location = location[:31].rstrip() + '…'
        add_row('Location', location)
        if tournament and tournament.enable_jersey_section:
            add_row('Jersey', player.jersy_size)
            add_row('Number', player.jersy_number)
        try:
            for extra in player.extra_attributes_payload(display_only=False):
                add_row(extra.get('label'), extra.get('value'))
        except Exception:
            pass
        rows = rows[:8]

        def _hash_tag(text):
            words = re.findall(r'[A-Za-z0-9]+', text or '')
            if not words:
                return ''
            if len(words) >= 2:
                return '#' + ''.join(word[0] for word in words[:4]).upper()
            return '#' + words[0][:14].upper()

        tag_line = '  '.join(tag for tag in (
            _hash_tag(team.name if team else ''),
            _hash_tag(tournament.name if tournament else ''),
        ) if tag)
        description = (tournament.description or '').strip() if tournament else ''
        if len(description) > 90:
            description = description[:89].rstrip() + '…'
        season_line = description
        date_line = ''
        venue_line = ''
        if tournament:
            date_line = (tournament.format_player_card_dates() or '').strip()
            if not date_line and tournament.auction_date:
                date_line = tournament.auction_date.strftime('%d %b %Y')
            venue_line = (tournament.get_venue_label() or (tournament.auction_venue or '')).strip()
        team_name = (team.name if team and team.name else '') or ''
        full_name = (name_first + ' ' + name_last).strip()
        name_px = 54
        if len(full_name) > 16:
            name_px = max(32, 54 - (len(full_name) - 16) * 2)

        def uri(binary_val):
            try:
                return image_data_uri(binary_val) if binary_val else ''
            except Exception:
                return ''

        # High-quality photo for Instagram Status (avoid print-sized photo_card)
        social_photo = self._card_social_photo(player.photo) or player.photo or player.photo_card

        from markupsafe import Markup
        paint = dict(self._CARD_PAINTS.get(theme, self._CARD_PAINTS['vanilla']))
        css = self._card_portrait_css(paint)

        icons_safe = {k: Markup(v) for k, v in self._CARD_ICONS.items()}

        return {
            'player': player,
            'tournament': tournament,
            'team': team,
            'is_football': is_football,
            'pal': pal,
            'css': Markup(css),
            'icons': icons_safe,
            'photo_uri': uri(social_photo),
            'team_logo_uri': uri(team.logo) if team else '',
            'tournament_logo_uri': uri(tournament.logo) if tournament else '',
            'poster_wash_uri': self._card_poster_wash_uri(tournament, paint['paper']),
            'edition_line': self._CARD_EDITIONS.get(theme, ''),
            'stadium_uri': self._card_stadium_uri(is_football),
            'brand_name': brand_name,
            'name_first': name_first,
            'name_last': name_last,
            'name_px': name_px,
            'card_id': card_id,
            'badge': badge,
            'rows': rows,
            'row_pairs': [],
            'season_line': season_line,
            'date_line': date_line,
            'venue_line': venue_line,
            'brand_logo_uri': self._card_brand_logo_uri(
                on_light=theme in self._CARD_LIGHT_THEMES),
            'tag_line': tag_line,
            'team_name': team_name,
            'is_sold': is_sold,
            'status_word': status_word,
            'sold_points_label': sold_points_label,
            'player_state': player_state,
            'sold_points': sold_points,
            'price_label': price_label,
            'price_display': price_display,
            'status_color': _st['color'],
            'status_text': _st['text'],
            'show_status': show_status,
            'show_stamp': show_stamp,
            'stamp_title': stamp_title,
            'stamp_amount': stamp_amount if player_state == 'sold' else '',
            'stamp_sub': stamp_sub,
            'stamp_is_unsold': player_state == 'unsold',
        }


    def _render_card_html(self, player):
        values = self._card_values(player)
        html = self.env['ir.qweb']._render('auction_module.player_card_portrait_image', values)
        if isinstance(html, bytes):
            html = html.decode('utf-8')
        return str(html)

    def _card_html_to_png(self, html, workdir, binary):
        """Render card at 2× via CSS scale, then LANCZOS-downscale to 1080×1920."""
        import subprocess
        import uuid as _uuid
        from PIL import Image

        base = os.path.join(workdir, _uuid.uuid4().hex)
        hpath, opath = base + '.html', base + '.png'

        # Supersample: double the viewport and scale the card with CSS transform.
        # wkhtmltoimage --zoom is a no-op on some builds; this is reliable.
        scale = 2
        big_w, big_h = self._CARD_W * scale, self._CARD_H * scale
        html_ss = html
        html_ss = html_ss.replace(
            'html,body{width:%dpx;height:%dpx;' % (self._CARD_W, self._CARD_H),
            'html,body{width:%dpx;height:%dpx;' % (big_w, big_h),
        )
        html_ss = html_ss.replace(
            'position:relative;width:%dpx;height:%dpx;overflow:hidden;' % (self._CARD_W, self._CARD_H),
            'position:relative;width:%dpx;height:%dpx;overflow:hidden;'
            '-webkit-transform:scale(%d);-webkit-transform-origin:0 0;' % (self._CARD_W, self._CARD_H, scale),
        )

        with open(hpath, 'w', encoding='utf-8') as fh:
            fh.write(html_ss)

        cmd = [
            binary, '--format', 'png',
            '--width', str(big_w), '--height', str(big_h),
            '--disable-smart-width',
            '--enable-local-file-access',
            '--load-error-handling', 'ignore',
            '--load-media-error-handling', 'ignore',
            '--quiet', hpath, opath,
        ]
        try:
            proc = subprocess.run(cmd, timeout=180, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except subprocess.TimeoutExpired:
            _logger.warning('wkhtmltoimage timed out rendering a player card')
            return None

        if not (os.path.exists(opath) and os.path.getsize(opath) > 0):
            # Fallback: 1× high-quality JPEG, then the same 1080×1920 finish.
            opath_jpg = base + '.jpg'
            with open(hpath, 'w', encoding='utf-8') as fh:
                fh.write(html)
            cmd2 = [
                binary, '--format', 'jpg', '--quality', '100',
                '--width', str(self._CARD_W), '--height', str(self._CARD_H),
                '--disable-smart-width',
                '--enable-local-file-access',
                '--load-error-handling', 'ignore',
                '--load-media-error-handling', 'ignore',
                '--quiet', hpath, opath_jpg,
            ]
            try:
                proc = subprocess.run(cmd2, timeout=120, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            except subprocess.TimeoutExpired:
                return None
            if not (os.path.exists(opath_jpg) and os.path.getsize(opath_jpg) > 0):
                _logger.warning('wkhtmltoimage produced no image (rc=%s). stderr: %s',
                                proc.returncode, (proc.stderr or b'')[-800:].decode('utf-8', 'replace'))
                return None
            opath = opath_jpg

        try:
            im = Image.open(opath)
            return self._card_finish_instagram_jpeg(im)
        except Exception:
            _logger.exception('Failed to downscale supersampled player card')
            return None

    def _card_finish_instagram_jpeg(self, im):
        """Crop to 9:16 and save a 1080×1920 JPEG at 72 DPI.

        A missing DPI tag makes some apps treat the file as 1 pixel per inch
        and report a print height of 1920 inches.
        """
        from io import BytesIO
        from PIL import Image, ImageEnhance, ImageFilter

        try:
            resample = Image.Resampling.LANCZOS
        except AttributeError:
            resample = Image.LANCZOS
        im = im.convert('RGB')
        tw, th = self._CARD_W, self._CARD_H
        w, h = im.size
        if w and h:
            target_ratio = tw / float(th)
            ratio = w / float(h)
            if abs(ratio - target_ratio) > 0.01:
                if ratio > target_ratio:
                    new_w = int(round(h * target_ratio))
                    left = max(0, (w - new_w) // 2)
                    im = im.crop((left, 0, left + new_w, h))
                else:
                    new_h = int(round(w / target_ratio))
                    top = max(0, (h - new_h) // 2)
                    im = im.crop((0, top, w, top + new_h))
        if im.size != (tw, th):
            im = im.resize((tw, th), resample)
        im = ImageEnhance.Sharpness(im).enhance(1.15)
        im = im.filter(ImageFilter.UnsharpMask(radius=1.1, percent=130, threshold=2))
        out = BytesIO()
        im.save(
            out, format='JPEG', quality=92, optimize=True, progressive=False,
            subsampling=0, dpi=(72, 72),
        )
        return out.getvalue()

    def render_instagram_status_jpg(self):
        """Render one player's vertical Instagram Status card (1080×1920 JPG).

        Same template / pipeline as *Download Player Cards (ZIP)*.
        Returns raw JPEG bytes, or ``None`` if rendering fails.
        """
        self.ensure_one()
        import shutil

        binary = self._card_render_binary()
        if not binary:
            _logger.warning('wkhtmltoimage missing — cannot render Instagram status card')
            return None

        workdir = self._card_workdir()
        try:
            html = self._render_card_html(self)
            return self._card_html_to_png(html, workdir, binary)
        except Exception:
            _logger.exception(
                'Instagram status card render failed for player %s', self.id)
            return None
        finally:
            shutil.rmtree(workdir, ignore_errors=True)

    def action_download_player_cards(self):
        import io
        import shutil
        import zipfile
        from datetime import datetime
        from concurrent.futures import ThreadPoolExecutor, as_completed

        players = self.exists()
        if not players:
            raise UserError(_('Please select at least one player to export.'))

        binary = self._card_render_binary()
        if not binary:
            raise UserError(_(
                'The wkhtmltoimage tool was not found on the server, which is '
                'required to render the player cards. Please install wkhtmltox.'))

        workdir = self._card_workdir()
        failed, used_names = [], set()
        zip_buf = io.BytesIO()

        # ── Step 1: pre-render all HTML in the main thread (ORM not thread-safe) ──
        render_jobs = []   # [(fname, html)]
        for player in players:
            try:
                html = self._render_card_html(player)
                fname = self._card_safe_filename(
                    player.name or ('player_%s' % player.id), used_names)
                render_jobs.append((fname, html))
            except Exception:
                _logger.exception('Card HTML render failed for player %s', player.id)
                failed.append(player.name or ('#%s' % player.id))

        # ── Step 2: run wkhtmltoimage in parallel (subprocess is thread-safe) ──
        def _render_one(job):
            fname, html = job
            try:
                jpg = self._card_html_to_png(html, workdir, binary)
                return fname, jpg
            except Exception:
                _logger.exception('wkhtmltoimage failed for %s', fname)
                return fname, None

        workers = min(6, max(1, len(render_jobs)))
        results = []
        try:
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futures = {pool.submit(_render_one, job): job for job in render_jobs}
                for fut in as_completed(futures):
                    results.append(fut.result())

            with zipfile.ZipFile(zip_buf, 'w', zipfile.ZIP_DEFLATED) as zf:
                for fname, jpg in results:
                    if jpg:
                        zf.writestr(fname, jpg)
                    else:
                        failed.append(fname)
                if failed:
                    note = (u'%d card(s) failed to generate:\n\n%s'
                            % (len(failed), u'\n'.join(failed)))
                    zf.writestr('_FAILED_CARDS.txt', note.encode('utf-8'))
        finally:
            shutil.rmtree(workdir, ignore_errors=True)

        if not results or all(jpg is None for _, jpg in results):
            raise UserError(_('All player cards failed to generate. Please check the server logs.'))

        tournament = players[0].tournament_id
        tname = re.sub(r'[^A-Za-z0-9]+', '_',
                       (tournament.name if tournament else 'Players')).strip('_') or 'Players'
        zipname = 'Player_Cards_%s_%s.zip' % (tname, datetime.now().strftime('%Y%m%d_%H%M%S'))
        attachment = self.env['ir.attachment'].create({
            'name': zipname,
            'type': 'binary',
            'datas': base64.b64encode(zip_buf.getvalue()),
            'mimetype': 'application/zip',
            'res_model': 'auction.team.player',
        })
        return {
            'type': 'ir.actions.act_url',
            'url': '/web/content/%s?download=true' % attachment.id,
            'target': 'self',
        }

    # def print_player_card(self):
    #     players = self.search([])
    #     return self.env.ref('auction_module.action_player_card_auction').report_action(players.ids)

    @api.model
    def action_player_card_report(self):
        # Kept for backward compatibility – delegates to print_player_cards
        return self.print_player_cards()

    @api.model
    def _get_report_values(self, docids, data=None):
        docs = self.browse(docids)
        print(f"Report docs: {docs}")  # Debugging statement
        return {
            'doc_ids': docids,
            'doc_model': 'your.model',
            'docs': docs,
            'tournament': self.env['auction.tournament'].search([('active', '=', True)], limit=1)
        }
    def get_base64_from_url(self,image_url):
        try:
            # Download the image
            response = requests.get(image_url)
            response.raise_for_status()  # Ensure we notice bad responses

            # Encode the image content in base64
            image_base64 = base64.b64encode(response.content).decode('utf-8')

            return image_base64

        except requests.exceptions.RequestException as e:
            # Handle any errors that occur during the download
            return None


    def get_image_base64_from_google_url(self, url):
        """
        Converts a Google Drive 'open?id=' URL into a direct download URL
        and returns Base64 encoded binary.
        """

        try:
            if not url:
                return False

            parsed = urlparse(url)
            query = parse_qs(parsed.query)
            file_id = query.get("id", [None])[0]

            if not file_id:
                return False

            # Convert to direct download URL
            download_url = f"https://drive.google.com/uc?export=download&id={file_id}"

            # Download the file
            response = requests.get(download_url, allow_redirects=True, timeout=20)
            response.raise_for_status()

            # Must be an image
            if "image" not in response.headers.get("Content-Type", ""):
                print("Not an image, Google returned:", response.headers.get("Content-Type"))
                return False

            return base64.b64encode(response.content)

        except Exception as e:
            print("Google Drive image fetch error:", e)
            return False


    @api.model
    def _ensure_default_tier_vals(self, vals):
        """If no tier was chosen, assign the first tier of the player's tournament."""
        if vals.get('tier_id'):
            return
        tid = vals.get('tournament_id') or self.env.context.get('default_tournament_id')
        if not tid:
            return
        Tier = self.env['auction.player.tier']
        # Prefer a normal (non-icon) tier; fall back to any tier on the tournament.
        tier = Tier.search([
            ('tournament_id', '=', tid),
            ('is_an_icon_tier', '=', False),
        ], order='id asc', limit=1)
        if not tier:
            tier = Tier.search([('tournament_id', '=', tid)], order='id asc', limit=1)
        if tier:
            vals['tier_id'] = tier.id

    @api.model
    def create(self, vals):
        # Only fall back to the active tournament when no tournament was explicitly provided.
        # If vals already carries tournament_id (e.g. from the public registration form via
        # the URL slug), preserve it — overwriting it caused players to be mapped to the
        # wrong tournament when multiple tournaments exist in the database.
        if not vals.get('tournament_id'):
            tournament_id = self.env['auction.tournament'].search([('active', '=', True)], limit=1)
            if tournament_id:
                vals.update({'tournament_id': tournament_id.id})

        self._ensure_default_tier_vals(vals)

        if vals.get('photo_url', False):
            image_base64 = self.get_base64_from_url(vals.get('photo_url', False))
            if image_base64:
               vals.update({'photo': image_base64})

        # A receipt upload is payment, same as a payment link. Without either,
        # a new registration stays unpaid.
        if vals.get('payment_url') or vals.get('payment_proof'):
            vals['amount_paid'] = True
        else:
            vals['amount_paid'] = False
        vals = self._apply_kabaddi_role_label(vals)
        player = super(AuctionTeamPlayer, self).create(vals)
        player._sync_other_attributes_from_tournament()
        return player

    def write(self, vals):
        if 'photo_url' in vals:
            image_base64 = self.get_base64_from_url(vals.get('photo_url', False))
            if image_base64:
                vals.update({'photo': image_base64})
        # Keep role label in sync with badminton category for generic displays
        if 'badminton_category' in vals and vals.get('badminton_category'):
            cat_map = dict(self._fields['badminton_category'].selection or [])
            vals = dict(vals)
            vals['role'] = cat_map.get(vals['badminton_category'], vals['badminton_category'])
        vals = self._apply_kabaddi_role_label(vals)
        if vals.get('payment_proof') and 'amount_paid' not in vals:
            vals = dict(vals)
            vals['amount_paid'] = True
        res = super(AuctionTeamPlayer, self).write(vals)
        if 'tournament_id' in vals:
            self._sync_other_attributes_from_tournament()
        return res

    @api.model
    def _resequence_tournament_players(self, tournament_ids):
        """Renumber ``sl_no`` to contiguous 1..n per tournament (current order).

        Called after player delete so organisers do not need a manual Resequence.
        Two-pass write avoids transient serial collisions.
        """
        ids = [int(t) for t in (tournament_ids or []) if t]
        if not ids:
            return
        Player = self.env['auction.team.player'].sudo()
        for tid in set(ids):
            players = Player.search(
                [('tournament_id', '=', tid)],
                order='sl_no asc, id asc',
            )
            if not players:
                continue
            offset = 100000
            for i, player in enumerate(players, start=1):
                if player.sl_no != offset + i:
                    player.sl_no = offset + i
            for i, player in enumerate(players, start=1):
                if player.sl_no != i:
                    player.sl_no = i

    def unlink(self):
        """Delete the live player after copying it to the tournament recycle bin.

        Remaining players in each affected tournament are resequenced to 1..n
        automatically (preserve relative order by previous serial).
        """
        if self and not self.env.context.get('skip_player_delete_archive'):
            self.env['auction.team.player.deleted'].sudo()._archive_players(self)
        tournament_ids = self.mapped('tournament_id').ids
        res = super(AuctionTeamPlayer, self).unlink()
        if tournament_ids and not self.env.context.get('skip_player_sl_resequence'):
            self._resequence_tournament_players(tournament_ids)
            self.env['auction.tournament'].browse(tournament_ids)._auto_open_registration_if_under_limit()
        return res

    def get_icon_players(self, team_id):
        players_domain = [('icon_player', '=', True), ('assigned_team_id', '=', team_id)]
        players = self.search(players_domain, order='sl_no asc')
        return players

    def get_auction_players(self, tournament_id=False):
        players_domain = [('icon_player', '=', False), ('state', '=', 'auction')]
        if tournament_id:
            players_domain.append(('tournament_id', '=', tournament_id.id if hasattr(tournament_id, 'id') else tournament_id))
        players = self.search(players_domain, order='sl_no asc')
        return players

    def get_random_player(self, exclude_id=0, tournament_id=False, commit_stage=True):
        """Pick the next auction player.

        :param commit_stage: When False (preview/prefetch), select the player for
            HTML rendering without mutating ``is_on_stage``. The operator UI
            commits the stage later via ``action_set_on_stage`` when the countdown
            ends, so the projector does not jump early.
        """
        tournament = tournament_id or self.env['auction.tournament'].search([('active', '=', True)], limit=1)
        random_player = False

        players = self.get_auction_players(tournament_id=tournament)
        if players:
            player_ids = players.ids

            # Prefer the client-supplied exclude_id (avoids is_on_stage sync issues);
            # fall back to the is_on_stage flag when no explicit hint is given.
            current_id = int(exclude_id) if exclude_id else False
            if not current_id:
                on_stage_domain = [('is_on_stage', '=', True)]
                if tournament:
                    on_stage_domain.append(('tournament_id', '=', tournament.id))
                current_on_stage = self.search(on_stage_domain, limit=1)
                current_id = current_on_stage.id if current_on_stage else False
            candidates = (
                [pid for pid in player_ids if pid != current_id]
                if current_id and len(player_ids) > 1
                else player_ids
            )

            if tournament and tournament.player_appearance_algorithm == 'random':
                random_player = self.browse(random.choice(candidates))
            else:
                random_player = self.browse(candidates[0])

        if not commit_stage:
            return random_player

        # ── Stage tracking: clear previous on-stage for this tournament only ──
        on_stage_domain = [('is_on_stage', '=', True)]
        if tournament:
            on_stage_domain.append(('tournament_id', '=', tournament.id))
        on_stage = self.search(on_stage_domain)
        if on_stage:
            on_stage.sudo().write({'is_on_stage': False})
        if random_player:
            random_player.sudo().write({'is_on_stage': True, 'mystery_revealed': False})
            random_player._warm_projector_thumbs()
            if tournament:
                try:
                    tournament.action_dismiss_projector_board()
                except Exception:
                    pass

        # ── Clear stamp only when it has already expired ──
        # A still-valid SOLD/UNSOLD stamp MUST survive here: the sold screen
        # fires a "next player" prefetch (?exclude=) within ~0.5s of a sale,
        # which lands in this method. Wiping the stamp then makes the public
        # live board skip the SOLD/UNSOLD animation and jump straight to the
        # next player. The data endpoint already prioritises the stamp player
        # over is_on_stage, so leaving a valid stamp lets the board finish the
        # animation for its full duration; it clears itself on stamp_expires_at.
        if tournament and tournament.stamp_player_id:
            now_dt = fields.Datetime.now()
            if not tournament.stamp_expires_at or tournament.stamp_expires_at <= now_dt:
                tournament.sudo().write({
                    'stamp_player_id': False,
                    'stamp_state': False,
                    'stamp_expires_at': False,
                })

        return random_player

    def _warm_projector_thumbs(self):
        """Fill this worker's sz=pj cache from stored photo_card (no original decode)."""
        for player in self:
            try:
                from odoo.addons.auction_module.controllers import main as pj_img
                tournament = player.tournament_id
                nxt = self.search([
                    ('tournament_id', '=', tournament.id),
                    ('icon_player', '=', False),
                    ('state', '=', 'auction'),
                    ('id', '!=', player.id),
                ], order='sl_no asc, name asc', limit=2) if tournament else self.browse()
                pj_img.warm_pj_stage_photos(self.env, player | nxt)
            except Exception:
                _logger.debug(
                    'projector thumb warm failed player=%s', player.id, exc_info=True,
                )
        return True

    def action_set_on_stage(self):
        """Mark this player as the current on-stage player for the live board.

        Clears ``is_on_stage`` only within the same tournament. On a shared SaaS
        database, a global clear would touch other tenants (and can raise if any
        of those accounts are frozen), which silently broke projector updates.
        """
        for player in self:
            tournament = player.tournament_id
            domain = [('is_on_stage', '=', True)]
            if tournament:
                domain.append(('tournament_id', '=', tournament.id))
            else:
                domain.append(('id', 'in', player.ids))
            others = self.search(domain) - player
            if others:
                others.sudo().with_context(saas_skip_freeze=True).write(
                    {'is_on_stage': False}
                )
            vals = {'is_on_stage': True}
            # Reset mystery mask only for a fresh auction appearance.
            # Sold + already-revealed players must stay revealed.
            if player.state != 'sold':
                vals['mystery_revealed'] = False
            # Runtime stage flag must not be blocked by SaaS freeze of *other*
            # tenants; freeze for *this* tournament is still enforced below via
            # normal write when the account itself is expired.
            player.sudo().write(vals)
            player._warm_projector_thumbs()
            # Opening a player ends the dice broadcast so the projector can
            # switch to the card immediately (no wait for client idle timeout).
            if tournament and tournament.dice_state and tournament.dice_state != 'idle':
                try:
                    tournament.set_dice_state('idle', 0)
                except Exception:
                    pass
            # Player on stage → dismiss pool/fixture board on the projector
            if tournament:
                try:
                    tournament.action_dismiss_projector_board()
                except Exception:
                    pass
            # Clear stamp only when it has already expired — same rule as
            # get_random_player. An active SOLD/UNSOLD stamp must survive so the
            # projector/live board finish the celebration even after the next
            # player is committed underneath.
            if tournament and tournament.stamp_player_id:
                now_dt = fields.Datetime.now()
                if not tournament.stamp_expires_at or tournament.stamp_expires_at <= now_dt:
                    tournament.sudo().with_context(saas_skip_freeze=True).write({
                        'stamp_player_id': False,
                        'stamp_state': False,
                        'stamp_expires_at': False,
                    })
        return {'success': True}

    def action_clear_stage(self):
        """Called when the auctioneer closes the player drawer.
        Clears is_on_stage and the tournament stamp so the projector and
        live board immediately return to the waiting state."""
        for player in self:
            player.sudo().write({'is_on_stage': False})
            tournament = player.tournament_id
            if tournament:
                # Keep SOLD stamp for unrevealed mystery so projector/live board
                # continue showing ??? until Reveal is pressed.
                keep_mystery_stamp = (
                    player.tier_id and player.tier_id.mystery
                    and not player.mystery_revealed
                    and player.state == 'sold'
                    and tournament.stamp_player_id
                    and tournament.stamp_player_id.id == player.id
                )
                if keep_mystery_stamp:
                    continue
                tournament.sudo().write({
                    'stamp_player_id': False,
                    'stamp_state': False,
                    'stamp_expires_at': False,
                })
        return True

    def action_unsold(self):
        for player in self:
            if player.state == 'auction':
                player.state = 'unsold'
                # is_on_stage stays True so the live board shows the UNSOLD stamp
                # until the next player is called via get_random_player()
                message = player.name + ' is Unsold!'
                player.create_unsold_auction_history( message, tournament_id=player.tournament_id.id,
                                              player=player)
                self.env.user.notify_success(message)
                # ── Stamp: record on tournament for the live board ──
                if player.tournament_id:
                    from datetime import timedelta
                    stamp_secs = player.tournament_id.result_stamp_hold_seconds()
                    player.tournament_id.sudo().write({
                        'stamp_player_id': player.id,
                        'stamp_state': 'unsold',
                        'stamp_expires_at': fields.Datetime.now() + timedelta(seconds=stamp_secs),
                    })
        display_seconds = self[0].tournament_id.sold_display_seconds if self and self[0].tournament_id else 5
        return {
            'success': True,
            'display_seconds': display_seconds if display_seconds and display_seconds > 0 else 5,
        }

    def _clear_live_bid(self):
        """Drop any live-bid leftover before a player returns to auction."""
        vals = {}
        if 'current_bid' in self._fields:
            vals['current_bid'] = 0
        if 'current_bid_team_id' in self._fields:
            vals['current_bid_team_id'] = False
        if vals:
            self.write(vals)

    def _reopen_live_after_recall(self, tournaments=None):
        """Clear Thank You / complete state. Do not steal a live showcase.

        Recalling a sold/unsold player used to always call ``get_random_player``,
        which clears ``is_on_stage`` and puts someone else on the projector.
        That is only needed when the live queue is empty (Thank You / complete).
        """
        tournaments = tournaments or self.mapped('tournament_id')
        if not tournaments:
            return
        Player = self.env['auction.team.player'].sudo()
        now_dt = fields.Datetime.now()
        for tournament in tournaments:
            on_stage = Player.search([
                ('tournament_id', '=', tournament.id),
                ('is_on_stage', '=', True),
            ], limit=1)
            stamp_live = bool(
                tournament.stamp_player_id
                and tournament.stamp_expires_at
                and tournament.stamp_expires_at > now_dt
            )
            vals = {'auction_declared_complete': False}
            if on_stage or stamp_live:
                # Live showcase or SOLD/UNSOLD stamp is in progress — leave it.
                tournament.sudo().write(vals)
                continue
            vals.update({
                'stamp_player_id': False,
                'stamp_state': False,
                'stamp_expires_at': False,
            })
            tournament.sudo().write(vals)
            try:
                Player.get_random_player(tournament_id=tournament)
            except Exception:
                pass

    def _restore_sold_player_to_auction(self, restore_state='auction', context=None):
        """Clear the sale on this player. Caller removes auction.auction.player lines."""
        context = context if context is not None else self.env.context
        if restore_state not in ('draft', 'auction'):
            restore_state = 'auction'
        for player in self:
            player._clear_live_bid()
            team = player.assigned_team_id
            if not context.get('skip_recall_history'):
                try:
                    player.create_auction_history(
                        team.id if team else False,
                        '%s recalled to auction' % (player.name or 'Player'),
                        tournament_id=player.tournament_id.id if player.tournament_id else False,
                        player=player,
                    )
                except Exception:
                    _logger.warning('recall history failed for player %s', player.id, exc_info=True)
            player.write({
                'assigned_team_id': False,
                'state': restore_state,
            })
            if not context.get('mass_update', False):
                try:
                    if hasattr(self.env.user, 'notify_success'):
                        self.env.user.notify_success(
                            (player.name or 'Player')
                            + ' brought back to auction successfully!. The player will be available in the auction'
                        )
                except Exception:
                    _logger.warning('recall notify failed for player %s', player.id, exc_info=True)
        return self

    def action_recall_auction_sold(self):
        context = self.env.context.copy()
        restore_state = context.get('restore_to_state') or 'auction'
        if restore_state not in ('draft', 'auction'):
            restore_state = 'auction'
        recalled = self.env['auction.team.player']
        line_ctx = dict(context, skip_reopen_live=True)
        for player in self:
            if player.state != 'sold':
                continue
            auction_player = self.env['auction.auction.player'].search(
                [('player_id', '=', player.id)]
            )
            if auction_player:
                auction_player.with_context(**line_ctx).action_recall_to_auction()
            else:
                player._restore_sold_player_to_auction(restore_state, context)
            recalled |= player
        tournaments = (recalled | self).mapped('tournament_id')
        if not context.get('skip_reopen_live'):
            self._reopen_live_after_recall(tournaments)
        if context.get('mass_update', False):
            if context.get('restore_to_state') == 'draft':
                message = 'Selected players restored to Draft successfully.'
            else:
                message = 'Selected players brought back to auction successfully!. The player will be available in the auction'
            if hasattr(self.env.user, 'notify_success') and not context.get('revoke_wizard'):
                self.env.user.notify_success(message)
        return True

    def action_auction(self):
        """Move draft/unsold players into In Auction (manual or mass reopen)."""
        context = self.env.context.copy()
        opened = self.env['auction.team.player']
        for player in self:
            if player.icon_player:
                continue
            if player.state in ('draft', 'unsold'):
                player._clear_live_bid()
                player.state = 'auction'
                opened |= player
                if not context.get('mass_update', False) and len(self) == 1:
                    message = player.name + ' brought to auction successfully!'
                    try:
                        self.env.user.notify_success(message)
                    except Exception:
                        pass
        tournaments = opened.mapped('tournament_id')
        if not context.get('skip_reopen_live'):
            self._reopen_live_after_recall(tournaments)
        if opened and (context.get('mass_update', False) or len(opened) > 1):
            if not context.get('revoke_wizard') and hasattr(self.env.user, 'notify_success'):
                try:
                    self.env.user.notify_success(
                        'Selected players brought to auction successfully!'
                    )
                except Exception:
                    pass
        return {'success': True, 'opened': len(opened)}

    def action_revoke_key_player(self):
        for player in self:
            if player.icon_player:
                team_id = player.assigned_team_id
                player.write({
                    'assigned_team_id': False,
                    'state': 'auction',
                    'icon_player': False,
                    'tier_id': player.previous_tier_id.id if player.previous_tier_id else False,
                    'previous_tier_id': False,
                })
                team_id.key_player_ids = [(3, player.id)]
                message = player.name + ' has been revoked from icon player list and brought back to auction successfully!'
                self.env.user.notify_success(message)

    def get_all_teams_for_correction(self):
        """Return all teams for this player's tournament, for the sale-correction panel."""
        player = self[0] if self else False
        if not player:
            return []
        tournament = player.tournament_id
        tournament_slabs = []
        if tournament:
            splits = tournament.points_split_ids.sorted('points')
            split_list = list(splits)
            for i, split in enumerate(split_list):
                to_amt = (split_list[i + 1].points - 1) if i + 1 < len(split_list) else 99999999
                tournament_slabs.append({
                    'from_amount': split.points,
                    'to_amount': to_amt,
                    'increment': split.no_of_calls,
                })
        auction_domain = [('tournament_id', '=', tournament.id)] if tournament else []
        auctions = self.env['auction.auction'].search(auction_domain)
        result = []
        for a in auctions:
            if not a.team_id:
                continue
            auction_slabs = [
                {'from_amount': s.from_amount, 'to_amount': s.to_amount, 'increment': s.increment}
                for s in a.auction_bid_slab_ids.sorted('from_amount')
            ]
            result.append({
                'team_id': a.team_id.id,
                'team_name': a.team_id.name,
                'team_logo': a.team_id.logo.decode('utf-8') if a.team_id.logo else '',
                'is_current': a.team_id.id == player.assigned_team_id.id,
                'slabs': auction_slabs if auction_slabs else tournament_slabs,
            })
        return result

    def action_update_sale(self, new_points, new_team_id):
        """Correct a sale: update points and/or change team. Used from the web correction panel."""
        player = self[0] if self else False
        if not player or player.state != 'sold':
            return {'success': False, 'error': 'Player is not in sold state'}
        new_team_id = int(new_team_id)
        new_points  = int(new_points)
        old_line = self.env['auction.auction.player'].search(
            [('player_id', '=', player.id)], limit=1)
        if not old_line:
            return {'success': False, 'error': 'Sale record not found'}
        old_team     = player.assigned_team_id
        team_changed = (old_team.id != new_team_id)
        if team_changed:
            new_auction = self.env['auction.auction'].search(
                [('team_id', '=', new_team_id),
                 ('tournament_id', '=', player.tournament_id.id)], limit=1)
            if not new_auction:
                return {'success': False, 'error': 'Selected team is not part of this tournament'}
            old_line.unlink()
            self.env['auction.auction.player'].create({
                'auction_id': new_auction.id,
                'player_id': player.id,
                'points': new_points,
            })
            player.assigned_team_id = new_team_id
            new_team_name = new_auction.team_id.name
            new_team_logo = new_auction.team_id.logo.decode('utf-8') if new_auction.team_id.logo else ''
        else:
            old_line.points = new_points
            new_team_name = old_team.name
            new_team_logo = old_team.logo.decode('utf-8') if old_team.logo else ''
        message = '%s sale corrected: sold to %s for %s' % (
            player.name, new_team_name, player._history_value(new_points)
        )
        player.create_auction_history(
            new_team_id, message,
            tournament_id=player.tournament_id.id if player.tournament_id else False,
            player=player,
        )
        self.env.user.notify_success(message=message, title='Sale Updated')
        return {
            'success': True,
            'message': message,
            'new_points': new_points,
            'new_team_id': new_team_id,
            'new_team_name': new_team_name,
            'new_team_logo': new_team_logo,
        }

    def action_update_sale_points(self, new_points):
        """Update the sold points for a player (corrects typo in final bid). Points-only edit, team unchanged."""
        player = self[0] if self else False
        if not player or player.state != 'sold':
            return {'success': False, 'error': 'Player is not in sold state'}
        player_line = self.env['auction.auction.player'].search(
            [('player_id', '=', player.id)], limit=1)
        if not player_line:
            return {'success': False, 'error': 'Sale record not found'}
        old_points = player_line.points
        player_line.points = int(new_points)
        message = 'Points updated for %s: %s → %s' % (
            player.name,
            player._history_value(old_points),
            player._history_value(int(new_points)),
        )
        team = player.assigned_team_id
        player.create_auction_history(
            team.id if team else False, message,
            tournament_id=player.tournament_id.id if player.tournament_id else False,
            player=player,
        )
        self.env.user.notify_success(message=message, title='Points Updated')
        return {'success': True, 'message': message, 'old_points': old_points, 'new_points': int(new_points)}

    def button_sell_player(self, player_id, other_data):
        team_id = self.env['auction.team'].browse(int(team_id))
        player = self.env['auction.team.player'].browse(int(player_id))
        auction = self.env['auction.auction'].search([('team_id', '=', int(team_id))])
        auction_line_data = {
            'player_id': player.id,
            'points': points,

        }
        message = '%s sold to %s for %s!' % (
            player.name, auction.team_id.name, player._history_value(points)
        )

        auction.player_ids = [(0, 0, auction_line_data)]
        player.assigned_team_id = auction.team_id and auction.team_id.id or False
        player.state = 'sold'
        # is_on_stage stays True — cleared on next player call
        self.create_auction_history(team_id.id, message, tournament_id=player.tournament_id.id, player=player)
        self.env.user.notify_success(message)

    def _history_value(self, amount):
        """Format an amount with the tournament unit for history / notify text."""
        tournament = self.tournament_id
        if tournament:
            return tournament.format_points(amount or 0)
        return '{:,}'.format(int(amount or 0))

    def create_auction_history(self, team_id, message, tournament_id, player):
        is_mystery_hidden = bool(
            player.tier_id and player.tier_id.mystery and not player.mystery_revealed
        )
        self.env['auction.history'].create(
            {
                'team_id': team_id,
                'player_id': player.id,
                'message': message,
                'tournament_id': tournament_id,
                # Hide photo on live board until mystery reveal
                'player_photo': False if is_mystery_hidden else player.photo,
            }
        )

    def create_unsold_auction_history(self, message, tournament_id, player):
        self.env['auction.history'].create(
            {
                'player_id': player.id,
                'message': message,
                'tournament_id': tournament_id,
                'player_photo': player.photo,
            }
        )
