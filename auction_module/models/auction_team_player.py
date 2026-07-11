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
_CARD_CSS = """
*{margin:0;padding:0;box-sizing:border-box;-webkit-print-color-adjust:exact;}
html,body{width:1080px;height:1920px;background:#000;overflow:hidden;}

@font-face{
  font-family:'AtlantaCollege';
  src:url('/auction_module/static/src/assets/fonts/Atlanta-College.ttf') format('truetype');
  font-weight:normal;font-style:normal;
}

/* ══════════════════════════════════════════════════════
   AUCTIONCHAMP INSTAGRAM STATUS CARD — 1080 × 1920 px (9:16)
   Full-bleed vertical Stories / Status format.
   Heights: head(170)+stage(1280)+panel(420)+pad(50)=1920
   ══════════════════════════════════════════════════════ */

.pc{
  position:relative;width:1080px;height:1920px;overflow:hidden;
  color:$txt;font-family:Arial,Helvetica,sans-serif;
  background-color:$bg2;
}

/* Stadium background — full bleed */
.pc-bg{
  position:absolute;top:0;left:0;width:1080px;height:1920px;z-index:0;
  background-color:$bg1;
  background-size:cover;background-position:center center;background-repeat:no-repeat;
}
.pc-shade{
  position:absolute;top:0;left:0;width:1080px;height:1920px;z-index:1;pointer-events:none;
  background:-webkit-linear-gradient(top,rgba(4,8,20,.28) 0%,rgba(4,8,20,.08) 28%,rgba(4,10,24,.35) 55%,$bg2 88%);
}
.pc-glow{
  position:absolute;top:80px;left:50%;width:860px;height:700px;margin-left:-430px;z-index:1;pointer-events:none;
  background:-webkit-radial-gradient(50% 30%,ellipse,rgba(255,230,160,.16) 0%,rgba(0,0,0,0) 70%);
}

/* Frame + corner gold ribbons */
.pc-frame{
  position:absolute;top:14px;left:14px;right:14px;bottom:14px;z-index:40;
  border:2px solid $accent;pointer-events:none;
  -webkit-box-shadow:0 0 36px $glow,inset 0 0 50px rgba(0,0,0,.22);
}
.pc-frame-in{
  position:absolute;top:24px;left:24px;right:24px;bottom:24px;z-index:40;
  border:1px solid rgba(255,255,255,.12);pointer-events:none;
}

/* Header: logo left · tournament · player id right */
.pc-head{
  position:relative;z-index:20;display:table;width:1080px;height:170px;
  table-layout:fixed;padding:48px 52px 0;
}
.pc-hcell{display:table-cell;vertical-align:middle;}
.pc-brand{width:300px;}
.pc-brand-logo{
  width:110px;height:110px;border-radius:14px;
  background-size:contain;background-position:center;background-repeat:no-repeat;
  background-color:rgba(0,0,0,.25);
  border:1px solid rgba(255,255,255,.18);
  -webkit-box-shadow:0 4px 18px rgba(0,0,0,.5);
}
.pc-brand-ph{
  width:110px;height:110px;border-radius:14px;border:1px solid $accent;
  background-color:rgba(0,0,0,.35);text-align:center;line-height:110px;
  font-family:'AtlantaCollege','Arial Black',Arial,sans-serif;
  font-size:32px;font-weight:900;color:$accent;
}
.pc-brand-name{
  margin-top:10px;font-size:14px;font-weight:700;letter-spacing:1.5px;
  color:#fff;text-transform:uppercase;text-shadow:0 2px 8px rgba(0,0,0,.8);
  max-width:260px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;
}
.pc-hmid{text-align:center;padding:0 12px;}
.pc-tname{
  font-family:'AtlantaCollege','Arial Black',Arial,sans-serif;font-size:26px;font-weight:900;
  color:rgba(255,255,255,.92);text-transform:uppercase;letter-spacing:1px;
  text-shadow:0 2px 12px rgba(0,0,0,.85);line-height:1.15;
  max-height:72px;overflow:hidden;
}
.pc-hid{width:240px;text-align:right;}
.pc-pid-lbl{
  font-size:14px;font-weight:700;letter-spacing:3px;color:rgba(255,255,255,.78);
  text-transform:uppercase;line-height:1;text-shadow:0 1px 6px rgba(0,0,0,.7);
}
.pc-pid-val{
  font-family:'AtlantaCollege','Arial Black',Arial,sans-serif;font-size:48px;font-weight:900;
  line-height:1.05;color:$accent;letter-spacing:1px;margin-top:8px;
  text-shadow:0 2px 14px rgba(0,0,0,.85),0 0 20px $glow;
}

/* Hero / player stage — tall Stories middle */
.pc-stage{
  position:relative;z-index:10;height:1280px;overflow:hidden;
}
.pc-photo-wrap{
  position:absolute;top:20px;left:90px;width:900px;height:1060px;z-index:4;
  text-align:center;overflow:hidden;line-height:1060px;
}
.pc-photo-img{
  max-width:900px;max-height:1060px;width:auto;height:auto;
  vertical-align:bottom;
  border:0;
}
.pc-photo-ph{
  position:absolute;top:80px;left:0;right:0;bottom:220px;text-align:center;
  font-size:280px;line-height:900px;color:rgba(255,255,255,.08);
}
.pc-pname{
  position:absolute;left:40px;right:40px;bottom:28px;z-index:15;text-align:center;
}
.pc-pfn{
  font-family:'AtlantaCollege','Arial Black',Arial,sans-serif;font-size:40px;font-weight:900;
  line-height:1;letter-spacing:5px;color:#fff;text-transform:uppercase;
  text-shadow:0 3px 18px rgba(0,0,0,.95);
}
.pc-pln{
  font-family:'AtlantaCollege','Arial Black',Arial,sans-serif;font-size:92px;font-weight:900;
  line-height:.92;letter-spacing:1px;color:#fff;text-transform:uppercase;
  text-shadow:0 5px 26px rgba(0,0,0,.95);
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis;padding-top:4px;
}
.pc-role{
  display:inline-block;margin-top:18px;padding:14px 56px;
  font-family:'AtlantaCollege','Arial Black',Arial,sans-serif;
  font-size:26px;font-weight:900;letter-spacing:6px;text-transform:uppercase;color:#fff;
  background:-webkit-linear-gradient(left,$badge1,$badge2);
  -webkit-box-shadow:0 8px 26px rgba(0,0,0,.55),0 0 24px rgba(224,52,155,.35);
}

/* Stage status chip — draft / in-auction only (sold/unsold use stamp) */
.pc-status{
  position:absolute;top:12px;right:52px;z-index:25;
  padding:10px 22px;border-radius:4px;
  font-family:'AtlantaCollege','Arial Black',Arial,sans-serif;
  font-size:18px;font-weight:900;letter-spacing:2px;text-transform:uppercase;color:#fff;
  -webkit-box-shadow:0 4px 16px rgba(0,0,0,.5);
}

/* Rubber-stamp sold / unsold seal — translucent so player stays visible */
.pc-stamp{
  position:absolute;left:50%;bottom:300px;z-index:22;
  width:260px;height:260px;margin-left:-130px;
  border-radius:130px;
  background:rgba(255,248,240,.42);
  border:5px solid rgba(176,28,28,.82);
  -webkit-box-shadow:none;
  text-align:center;overflow:hidden;
  opacity:.88;
  -webkit-transform:rotate(-14deg);
}
.pc-stamp.unsold{
  background:rgba(236,239,241,.40);
  border-color:rgba(84,110,122,.80);
  opacity:.86;
  -webkit-transform:rotate(12deg);
}
.pc-stamp-ring{
  position:absolute;top:12px;left:12px;right:12px;bottom:12px;z-index:1;
  border:3px dashed rgba(176,28,28,.65);border-radius:118px;pointer-events:none;
}
.pc-stamp.unsold .pc-stamp-ring{border-color:rgba(84,110,122,.60);}
.pc-stamp-body{
  position:relative;z-index:2;display:table;width:260px;height:260px;
}
.pc-stamp-inner{display:table-cell;vertical-align:middle;padding:16px 14px 12px;}
.pc-stamp-tag{
  font-family:'AtlantaCollege','Arial Black',Arial,sans-serif;
  font-size:34px;font-weight:900;letter-spacing:5px;text-transform:uppercase;
  color:rgba(176,28,28,.95);line-height:1;margin-bottom:8px;
  text-shadow:0 1px 0 rgba(255,255,255,.25);
}
.pc-stamp.unsold .pc-stamp-tag{
  color:rgba(55,71,79,.95);font-size:36px;letter-spacing:4px;margin-bottom:10px;
}
.pc-stamp-logo{
  width:88px;height:88px;margin:0 auto 8px;
  background-size:contain;background-position:center;background-repeat:no-repeat;
  opacity:.92;
}
.pc-stamp-logo-ph{
  width:72px;height:72px;margin:0 auto 8px;border-radius:36px;
  background-color:transparent;line-height:72px;
  font-family:'AtlantaCollege','Arial Black',Arial,sans-serif;
  font-size:40px;font-weight:900;color:rgba(176,28,28,.70);
}
.pc-stamp.unsold .pc-stamp-logo-ph{color:rgba(55,71,79,.70);font-size:48px;}
.pc-stamp-amt{
  font-family:'AtlantaCollege','Arial Black',Arial,sans-serif;
  font-size:28px;font-weight:900;letter-spacing:1px;
  color:rgba(120,20,20,.95);line-height:1.05;
}
.pc-stamp.unsold .pc-stamp-amt{font-size:32px;color:rgba(55,71,79,.92);letter-spacing:3px;}
.pc-stamp-sub{
  margin-top:5px;font-size:11px;font-weight:700;letter-spacing:1.5px;
  text-transform:uppercase;color:rgba(120,20,20,.85);
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:210px;margin-left:auto;margin-right:auto;
}
.pc-stamp.unsold .pc-stamp-sub{color:rgba(55,71,79,.8);}

/* Info panel — 3×2 table */
.pc-panel-wrap{position:relative;z-index:20;padding:10px 40px 0;}
.pc-panel{
  width:1000px;height:400px;border:1px solid $accent;border-radius:12px;
  background:-webkit-linear-gradient(top,rgba(8,14,32,.96),rgba(4,8,20,.98));
  -webkit-box-shadow:0 12px 34px rgba(0,0,0,.55),inset 0 1px 0 rgba(255,255,255,.08);
  overflow:hidden;
}
.pc-panel table{width:100%;height:400px;border-collapse:collapse;table-layout:fixed;}
.pc-panel td{
  width:50%;height:133px;padding:0 26px;vertical-align:middle;
  border-right:1px solid rgba(233,193,90,.35);
  border-bottom:1px solid rgba(233,193,90,.35);
}
.pc-panel tr td:last-child{border-right:none;}
.pc-panel tr:last-child td{border-bottom:none;}
.pc-cell{display:table;width:100%;height:110px;}
.pc-ic{display:table-cell;width:52px;vertical-align:middle;}
.pc-ibox{
  width:48px;height:48px;border-radius:10px;overflow:hidden;
  background-color:rgba(255,255,255,.06);border:1px solid rgba(233,193,90,.28);
  text-align:center;line-height:46px;color:$accent;
}
.pc-ibox svg{width:26px;height:26px;vertical-align:middle;}
.pc-ilogo{
  width:48px;height:48px;border-radius:10px;
  background-size:contain;background-position:center;background-repeat:no-repeat;
  background-color:rgba(255,255,255,.06);
}
.pc-itxt{display:table-cell;vertical-align:middle;padding-left:16px;}
.pc-lbl{
  font-size:13px;font-weight:700;letter-spacing:2px;color:$sub;
  text-transform:uppercase;line-height:1;
}
.pc-val{
  font-size:24px;font-weight:700;color:$accent;text-transform:uppercase;
  line-height:1.2;margin-top:7px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;
  max-width:400px;
}
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
    _inherit = ['auction.image.compress.mixin', 'auction.tournament.security.mixin']

    # photo: keep near–Stories resolution for sharp Instagram cards.
    _compressible_image_fields = {
        'photo':         (1600, 2200, 98, 'JPEG'),
        'payment_proof': (1200, 1600, 82, 'JPEG'),
    }

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
            draft_count = self.search_count([
                ('tournament_id', '=', tournament.id),
                ('state', '=', 'draft'),
            ])
            if draft_count >= tournament.max_registrations:
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
        string='Preferred Foot')
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
    other_attribute_ids = fields.One2many(
        'auction.player.other.attribute', 'player_id',
        string='Other Attributes',
        help='When values are set, Secondary / Age / Playing Style / Strengths are hidden on '
             'player cards and live displays; these label–value rows are shown instead.')
    use_other_attributes = fields.Boolean(
        string='Use Other Attributes',
        compute='_compute_use_other_attributes',
        help='True when at least one Other Attribute has a value.')
    photo = fields.Binary("Photo", default=_get_default_player_photo)
    photo_card = fields.Binary(
        string='Photo (Card Print)',
        compute='_compute_photo_card',
        store=True,
        help='Resized & compressed JPEG for PDF card printing. Reduces PDF size and generation time.',
    )
    photo_url = fields.Char("Photo URL")
    payment_url = fields.Char("Payment URL")
    state = fields.Selection([('draft', 'Draft'), ('auction', 'In Auction'), ('sold', 'Sold'), ('unsold', 'Unsold')], default='draft')
    amount_paid = fields.Boolean(default=True)
    active = fields.Boolean(default=True)
    tournament_id = fields.Many2one('auction.tournament', 'Tournament')
    tournament_type = fields.Selection(related='tournament_id.tournament_type')
    tournament_color = fields.Char(related='tournament_id.kanban_color', string='Tournament Color')
    assigned_team_id = fields.Many2one('auction.team', 'Team')
    icon_player = fields.Boolean("Key Player")
    is_on_stage = fields.Boolean("Currently on Stage", default=False,
                                  help="True when this player is actively displayed in the auction stage. Only one player should have this True at a time.")
    tier_id = fields.Many2one('auction.player.tier', string='Tier')
    previous_tier_id = fields.Many2one('auction.player.tier', string='Previous Tier', help='Stores the tier before the player was promoted to Icon Player, used to restore on revoke.')
    tier_color = fields.Selection(related='tier_id.color', string='Tier Color')
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
    blood_group = fields.Char("Blood Group")
    p_type =   fields.Char("Type")
    p_category = fields.Char("Category")
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

    @api.depends('other_attribute_ids', 'other_attribute_ids.value', 'other_attribute_ids.label')
    def _compute_use_other_attributes(self):
        for player in self:
            player.use_other_attributes = any(
                (a.label and (a.value or '').strip()) for a in player.other_attribute_ids
            )

    def _sync_other_attributes_from_tournament(self):
        """Ensure football players have Other Attribute rows for each tournament Att-Label."""
        for player in self:
            tournament = player.tournament_id
            if not tournament or tournament.tournament_type != 'football':
                continue
            labels = tournament.other_attribute_label_ids.sorted('sequence')
            if not labels:
                continue
            existing_by_label = {
                (a.label or '').strip().lower(): a for a in player.other_attribute_ids
            }
            commands = []
            for lab in labels:
                key = (lab.label or '').strip().lower()
                if not key or key in existing_by_label:
                    continue
                commands.append((0, 0, {
                    'label': lab.label,
                    'value': '',
                    'sequence': lab.sequence,
                }))
            if commands:
                player.other_attribute_ids = commands

    @api.onchange('tournament_id')
    def _onchange_tournament_id_sync_other_attrs(self):
        self._sync_other_attributes_from_tournament()

    def action_sync_other_attributes(self):
        """Manual sync of tournament Att-Labels onto this player."""
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
        return self.photo or False

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
        teams = []
        for auction in auctions:
            if auction.remaining_players_count <= 0 or auction.remaining_points <= 0:
                continue

            # Compute effective base point for this player's tier
            effective_base = auction.base_point
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
            if player.tier_id and auction.tier_limit_ids:
                tier_limit = auction.tier_limit_ids.filtered(
                    lambda l: l.tier_id.id == player.tier_id.id
                )
                if tier_limit:
                    already_sold = self.env['auction.auction.player'].search_count([
                        ('auction_id', '=', auction.id),
                        ('player_id.tier_id', '=', player.tier_id.id),
                        ('player_id', '!=', player.id),
                    ])
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
        return teams

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
        message = '%s sold to %s for %d points!' % (player.name, auction.team_id.name, final_point)

        auction.player_ids = [(0, 0, auction_line_data)]
        player.assigned_team_id = auction.team_id.id
        player.state = 'sold'
        # is_on_stage stays True so the live board can show the SOLD stamp
        # until the next player is called via get_random_player()
        player.create_auction_history(auction.team_id.id, message, tournament_id=player.tournament_id.id, player=player)

        # ── Stamp: record on tournament for the live board ──
        if player.tournament_id:
            display_secs = player.tournament_id.sold_display_seconds or 5
            from datetime import timedelta
            player.tournament_id.sudo().write({
                'stamp_player_id': player.id,
                'stamp_state': 'sold',
                'stamp_expires_at': fields.Datetime.now() + timedelta(seconds=display_secs + 3),
            })

        self.env.user.notify_success(message=message, title='CONGRATULATIONS!')
        return {
            'success': True,
            'message': message,
            'player_id': player.id,
            'player_name': player.name,
            'team_id': auction.team_id.id,
            'team_name': auction.team_id.name,
            'final_point': final_point,
            'display_seconds': player.tournament_id.sold_display_seconds if player.tournament_id else 5,
        }

    def print_player_cards(self):
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
        if tournament and tournament.tournament_type == 'football':
            return self.env.ref('auction_module.action_report_player_card_football').report_action(self)
        template = tournament.player_display_template if tournament else 'vanilla'
        report_map = {
            'vanilla':       'auction_module.action_report_player_card',
            'butterscotch':  'auction_module.action_report_player_card_butterscotch',
            'strawberry':    'auction_module.action_report_player_card_strawberry',
            'cherry':        'auction_module.action_report_player_card_cherry',
            'pistah':        'auction_module.action_report_player_card_pistah',
        }
        report_ref = report_map.get(template, 'auction_module.action_report_player_card')
        return self.env.ref(report_ref).report_action(self)


    # ══════════════════════════════════════════════════════════════════
    #  Bulk Instagram Stories / Status player-card export (ZIP of JPGs)
    #  Renders a premium 1080×1920 (9:16) stadium-backed social card
    #  per player via wkhtmltoimage and streams a ZIP to the browser.
    # ══════════════════════════════════════════════════════════════════
    _CARD_W = 1080
    _CARD_H = 1920

    _FOOT_LABELS = {'left': 'Left Foot', 'right': 'Right Foot', 'both': 'Both Feet'}

    _CARD_ICONS = {
        'bat': '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M14.5 3.5l6 6"/><path d="M18 6l-9.5 9.5"/><path d="M8.5 15.5l-4.2 4.2a1.5 1.5 0 01-2.1-2.1L6.4 13.4z"/><circle cx="5" cy="19" r="0.6" fill="currentColor"/></svg>',
        'ball': '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><circle cx="12" cy="12" r="8.5"/><path d="M12 3.5v17"/><path d="M9 4.2c1.6 4.8 1.6 10.8 0 15.6M15 4.2c-1.6 4.8-1.6 10.8 0 15.6" stroke-dasharray="2 2"/></svg>',
        'position': '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><circle cx="12" cy="12" r="8.5"/><circle cx="12" cy="12" r="4"/><circle cx="12" cy="12" r="0.8" fill="currentColor"/></svg>',
        'foot': '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"><path d="M8 3c1.6 0 2.5 1.4 2.7 3.2.2 1.8.5 3.3 1.4 4.6.8 1.2 1.9 2 1.9 3.9 0 2.4-1.8 4.3-4.3 4.3-2.2 0-3.7-1.4-3.7-3.6 0-1.3.3-2.2.3-3.6C6.3 12 5 9.4 5 6.8 5 4.6 6.2 3 8 3z"/></svg>',
        'age': '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"><rect x="3.5" y="5" width="17" height="15.5" rx="2.2"/><path d="M3.5 9.5h17M8 3v4M16 3v4"/></svg>',
        'category': '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"><path d="M20.5 12.5l-8 8-9-9V4h7.5z"/><circle cx="8" cy="8" r="1.4" fill="currentColor"/></svg>',
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
        """Return a data-URI for the sport-specific stadium background."""
        key = 'football' if is_football else 'cricket'
        cached = self._STADIUM_CACHE.get(key)
        if cached:
            return cached
        fname = 'stadium_football.jpg' if is_football else 'stadium_cricket.jpg'
        path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'static', 'img', fname)
        try:
            with open(path, 'rb') as fh:
                uri = 'data:image/jpeg;base64,' + base64.b64encode(fh.read()).decode('ascii')
        except Exception:
            uri = ''
        self._STADIUM_CACHE[key] = uri
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

    @staticmethod
    def _card_social_photo(binary_photo):
        """Prepare a crisp source photo for Instagram Status cards.

        Keeps up to 1600×2200 (≈2× display) so 2× supersampled renders stay sharp.
        JPEG quality 100, 4:4:4 chroma, clarity enhance.
        """
        if not binary_photo:
            return binary_photo
        try:
            from io import BytesIO
            from PIL import Image, ImageFilter, ImageOps, ImageEnhance
            raw = base64.b64decode(binary_photo)
            im = Image.open(BytesIO(raw))
            try:
                im = ImageOps.exif_transpose(im)
            except Exception:
                pass
            if im.mode not in ('RGB', 'L'):
                im = im.convert('RGB')
            elif im.mode == 'L':
                im = im.convert('RGB')

            try:
                resample = Image.Resampling.LANCZOS
            except AttributeError:
                resample = Image.LANCZOS

            # ~2× the on-card photo box so zoomed renders stay detailed
            max_w, max_h = 1600, 2200
            w, h = im.size

            if w < 1200 or h < 1600:
                scale = min(max_w / float(w), max_h / float(h), 2.0)
                if scale > 1.05:
                    im = im.resize((int(round(w * scale)), int(round(h * scale))), resample)
                    w, h = im.size

            if w > max_w or h > max_h:
                im.thumbnail((max_w, max_h), resample)

            im = ImageEnhance.Contrast(im).enhance(1.10)
            im = ImageEnhance.Sharpness(im).enhance(1.35)
            im = im.filter(ImageFilter.UnsharpMask(radius=1.8, percent=160, threshold=1))

            out = BytesIO()
            # quality 100 + no chroma subsample = maximum JPEG fidelity
            im.save(out, format='JPEG', quality=100, optimize=False, progressive=False,
                    subsampling=0)
            return base64.b64encode(out.getvalue())
        except Exception:
            _logger.debug('Social photo enhance failed; using original', exc_info=True)
            try:
                return image_process(binary_photo, size=(1600, 2200), quality=100)
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
                     else (player.role or player.p_category or 'PLAYER'))
        else:
            badge = player.role or player.p_category or 'PLAYER'

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

        # ── Instagram info grid: fixed 6 cells matching social mockup ──
        rows = []
        if is_football:
            rows.append((
                'position', 'Position',
                (player.dominant_position_id.name if player.dominant_position_id else (player.role or '—'))
            ))
            rows.append((
                'foot', 'Preferred Foot',
                self._FOOT_LABELS.get(player.preferred_foot, (player.preferred_foot or '—').title())
                if player.preferred_foot else '—'
            ))
            if player.use_other_attributes and player.other_attribute_ids:
                attr = next((a for a in player.other_attribute_ids if (a.value or '').strip()), None)
                rows.append(('category', (attr.label if attr else 'Category') or 'Category',
                             (attr.value if attr else '—') or '—'))
            elif player.height:
                rows.append(('height', 'Height', player.height))
            else:
                rows.append(('nation', 'Nationality', 'India'))
        else:
            bat = (player.batting_style or '').strip() or '—'
            bowl = (player.bowling_style or '').strip() or '—'
            rows.append(('bat', 'Batting Style', bat))
            rows.append(('ball', 'Bowling Style', bowl))
            if player.p_category:
                rows.append(('category', 'Category', player.p_category))
            else:
                rows.append(('nation', 'Nationality', 'India'))

        rows.append(('age', 'Age', ('%d Years' % player.age) if player.age else '—'))
        rows.append(('price', price_label, price_display))
        team_name = (team.name if team else (player.current_team or '')) or 'Unassigned'
        rows.append(('team', 'Team', team_name))

        # Pad to exactly 6 cells for the 3×2 table
        while len(rows) < 6:
            rows.append(('category', '—', '—'))
        rows = [{'icon': i, 'label': l, 'value': v} for i, l, v in rows[:6]]
        row_pairs = [rows[0:2], rows[2:4], rows[4:6]]

        def uri(binary_val):
            try:
                return image_data_uri(binary_val) if binary_val else ''
            except Exception:
                return ''

        # High-quality photo for Instagram Status (avoid print-sized photo_card)
        social_photo = self._card_social_photo(player.photo) or player.photo or player.photo_card

        pal['line'] = 'rgba(255,255,255,0.12)'
        pal['glow'] = (pal['accent'] or '#e9c15a') + '55'
        import string
        from markupsafe import Markup
        css = string.Template(_CARD_CSS).safe_substitute(pal)

        try:
            _fp = os.path.join(
                os.path.dirname(os.path.dirname(__file__)),
                'static', 'src', 'assets', 'fonts', 'Atlanta-College.ttf'
            )
            with open(_fp, 'rb') as _ff:
                _font_b64 = base64.b64encode(_ff.read()).decode('ascii')
            css = css.replace(
                "url('/auction_module/static/src/assets/fonts/Atlanta-College.ttf') format('truetype')",
                "url('data:font/truetype;base64," + _font_b64 + "') format('truetype')"
            )
        except Exception:
            pass

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
            'stadium_uri': self._card_stadium_uri(is_football),
            'brand_name': brand_name,
            'name_first': name_first,
            'name_last': name_last,
            'card_id': card_id,
            'badge': badge,
            'rows': rows,
            'row_pairs': row_pairs,
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
        from io import BytesIO
        from PIL import Image, ImageFilter, ImageEnhance

        base = os.path.join(workdir, _uuid.uuid4().hex)
        hpath, opath = base + '.html', base + '.png'

        # Supersample: double the viewport and scale the card with CSS transform.
        # wkhtmltoimage --zoom is a no-op on some builds; this is reliable.
        scale = 2
        big_w, big_h = self._CARD_W * scale, self._CARD_H * scale
        html_ss = html
        html_ss = html_ss.replace(
            'html,body{width:1080px;height:1920px;',
            'html,body{width:%dpx;height:%dpx;' % (big_w, big_h),
        )
        html_ss = html_ss.replace(
            'position:relative;width:1080px;height:1920px;overflow:hidden;',
            'position:relative;width:1080px;height:1920px;overflow:hidden;'
            '-webkit-transform:scale(%d);-webkit-transform-origin:0 0;' % scale,
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
            # Fallback: 1× high-quality JPEG
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
            with open(opath_jpg, 'rb') as fh:
                return fh.read()

        try:
            try:
                resample = Image.Resampling.LANCZOS
            except AttributeError:
                resample = Image.LANCZOS
            im = Image.open(opath).convert('RGB')
            target = (self._CARD_W, self._CARD_H)
            if im.size != target:
                im = im.resize(target, resample)
            im = ImageEnhance.Sharpness(im).enhance(1.15)
            im = im.filter(ImageFilter.UnsharpMask(radius=1.1, percent=130, threshold=2))
            out = BytesIO()
            im.save(out, format='JPEG', quality=100, optimize=False, progressive=False,
                    subsampling=0)
            return out.getvalue()
        except Exception:
            _logger.exception('Failed to downscale supersampled player card')
            with open(opath, 'rb') as fh:
                return fh.read()

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
    def create(self, vals):
        # Only fall back to the active tournament when no tournament was explicitly provided.
        # If vals already carries tournament_id (e.g. from the public registration form via
        # the URL slug), preserve it — overwriting it caused players to be mapped to the
        # wrong tournament when multiple tournaments exist in the database.
        if not vals.get('tournament_id'):
            tournament_id = self.env['auction.tournament'].search([('active', '=', True)], limit=1)
            if tournament_id:
                vals.update({'tournament_id': tournament_id.id})

        if vals.get('photo_url', False):
            image_base64 = self.get_base64_from_url(vals.get('photo_url', False))
            if image_base64:
               vals.update({'photo': image_base64})

        if not vals.get('payment_url', False):
            vals.update({'amount_paid': False})
        player = super(AuctionTeamPlayer, self).create(vals)
        player._sync_other_attributes_from_tournament()
        return player

    def write(self, vals):
        if 'photo_url' in vals:
            image_base64 = self.get_base64_from_url(vals.get('photo_url', False))
            if image_base64:
                vals.update({'photo': image_base64})
        res = super(AuctionTeamPlayer, self).write(vals)
        if 'tournament_id' in vals:
            self._sync_other_attributes_from_tournament()
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

    def get_random_player(self, exclude_id=0, tournament_id=False):
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

        # ── Stage tracking: clear previous on-stage for this tournament only ──
        on_stage_domain = [('is_on_stage', '=', True)]
        if tournament:
            on_stage_domain.append(('tournament_id', '=', tournament.id))
        on_stage = self.search(on_stage_domain)
        if on_stage:
            on_stage.sudo().write({'is_on_stage': False})
        if random_player:
            random_player.sudo().write({'is_on_stage': True})

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

    def action_set_on_stage(self):
        """Mark this player as the current on-stage player for the live board."""
        all_on_stage = self.search([('is_on_stage', '=', True)])
        if all_on_stage:
            all_on_stage.sudo().write({'is_on_stage': False})
        for player in self:
            player.sudo().write({'is_on_stage': True})
            # Clear any active stamp so the live board switches to this player immediately
            tournament = player.tournament_id
            if tournament and tournament.stamp_player_id:
                tournament.sudo().write({
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
                    display_secs = player.tournament_id.sold_display_seconds or 5
                    from datetime import timedelta
                    player.tournament_id.sudo().write({
                        'stamp_player_id': player.id,
                        'stamp_state': 'unsold',
                        'stamp_expires_at': fields.Datetime.now() + timedelta(seconds=display_secs + 3),
                    })
        display_seconds = self[0].tournament_id.sold_display_seconds if self and self[0].tournament_id else 5
        return {
            'success': True,
            'display_seconds': display_seconds if display_seconds and display_seconds > 0 else 5,
        }

    def action_recall_auction_sold(self):
        context = self.env.context.copy()
        for player in self:
            if player.state == 'sold':
                auction_player = self.env['auction.auction.player'].search([('player_id', '=', player.id)])
                if auction_player:
                    auction_player.action_recall_to_auction()
        if context.get('mass_update', False):
            message =  'Selected players brought back to auction successfully!. The player will be available in the auction'
            self.env.user.notify_success(message)

    def action_auction(self):
        context = self.env.context.copy()
        for player in self:
            if player.state == 'unsold':
                player.state = 'auction'
                if not context.get('mass_update', False):
                    message = player.name + ' brought to auction successfully!'
                    self.env.user.notify_success(message)
        if context.get('mass_update', False):
            message = 'Selected players brought to auction successfully!'
            self.env.user.notify_success(message)

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
        message = '%s sale corrected: sold to %s for %d pts' % (player.name, new_team_name, new_points)
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
        message = 'Points updated for %s: %d → %d pts' % (player.name, old_points, int(new_points))
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
        message = player.name + ' sold to the '+ auction.team_id.name+' for ' + str(points) + ' points successfully!'

        auction.player_ids = [(0, 0, auction_line_data)]
        player.assigned_team_id = auction.team_id and auction.team_id.id or False
        player.state = 'sold'
        # is_on_stage stays True — cleared on next player call
        self.create_auction_history(team_id.id, message, tournament_id=player.tournament_id.id, player=player)
        self.env.user.notify_success(message)

    def create_auction_history(self, team_id, message, tournament_id, player):
        self.env['auction.history'].create(
            {
                'team_id': team_id,
                'message': message,
                'tournament_id': tournament_id,
                'player_photo': player.photo
            }
        )

    def create_unsold_auction_history(self, message, tournament_id, player):
        self.env['auction.history'].create(
            {
                'message': message,
                'tournament_id': tournament_id,
                'player_photo': player.photo
            }
        )
