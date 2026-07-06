# -*- coding: utf-8 -*-
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

# Stylesheet for the premium portrait player-card image, rendered by
# wkhtmltoimage (Qt WebKit). Kept Qt-WebKit-safe: -webkit- prefixed gradients,
# no CSS custom properties, no CSS grid, no object-fit, no backdrop-filter.
# Palette values are substituted via string.Template ($name placeholders).
_CARD_CSS = """
*{margin:0;padding:0;box-sizing:border-box;-webkit-print-color-adjust:exact;}
html,body{width:1080px;height:1350px;}
.pc{position:relative;width:1080px;height:1350px;overflow:hidden;color:$txt;font-family:'Barlow',sans-serif;
 background:
  -webkit-radial-gradient(50% 0%, ellipse, $bg3 0%, rgba(0,0,0,0) 55%),
  -webkit-radial-gradient(12% 24%, circle, rgba(255,255,255,0.10) 0%, rgba(0,0,0,0) 30%),
  -webkit-radial-gradient(88% 22%, circle, rgba(255,255,255,0.12) 0%, rgba(0,0,0,0) 30%),
  -webkit-linear-gradient(top, $bg1 0%, $bg2 62%, #02060f 100%);}
.pc-acc{position:absolute;z-index:6;height:8px;background:-webkit-linear-gradient(left,$accentD,$accent2);}
.pc-acc.tl{top:150px;left:-70px;width:520px;-webkit-transform:rotate(-32deg);opacity:.85;}
.pc-acc.br{bottom:250px;right:-70px;width:520px;-webkit-transform:rotate(-32deg);opacity:.85;}
.pc-acc.br2{bottom:212px;right:-120px;width:420px;height:5px;-webkit-transform:rotate(-32deg);opacity:.55;}

.pc-head{position:relative;z-index:8;height:150px;display:table;width:100%;padding:40px 52px 0;table-layout:fixed;}
.pc-cell{display:table-cell;vertical-align:middle;}
.pc-badge{width:104px;height:104px;border-radius:52px;overflow:hidden;background-color:$bg2;
 background-size:cover;background-position:center;background-repeat:no-repeat;
 border:3px solid $accent;box-shadow:0 0 26px $glow;text-align:center;line-height:98px;color:$accent;font-size:46px;}
.pc-mid{padding-left:22px;}
.pc-team{font-family:'Bebas Neue',sans-serif;font-size:44px;line-height:1;color:#fff;text-transform:uppercase;
 letter-spacing:1px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;text-shadow:0 2px 10px rgba(0,0,0,.5);}
.pc-tour{font-family:'Oswald',sans-serif;font-size:15px;font-weight:600;letter-spacing:4px;color:$accent2;
 text-transform:uppercase;margin-top:5px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
.pc-id{text-align:right;width:240px;}
.pc-id small{display:block;font-family:'Oswald',sans-serif;font-size:13px;font-weight:600;letter-spacing:4px;
 color:$sub;text-transform:uppercase;}
.pc-id b{display:block;font-family:'Bebas Neue',sans-serif;font-size:52px;line-height:1;color:$accent;
 letter-spacing:2px;text-shadow:0 2px 12px $glow;}

.pc-stage{position:relative;z-index:5;height:660px;overflow:hidden;}
.pc-photo{position:absolute;top:0;left:0;right:0;bottom:0;background-size:cover;background-position:top center;background-repeat:no-repeat;}
.pc-photo-ph{position:absolute;top:0;left:0;right:0;bottom:0;background-color:$bg2;text-align:center;
 color:rgba(255,255,255,.10);font-size:220px;line-height:660px;}
.pc-fade{position:absolute;top:0;left:0;right:0;bottom:0;
 background:-webkit-linear-gradient(top, rgba(0,0,0,0) 42%, rgba(0,0,0,.30) 66%, $bg2 99%);}
.pc-name{position:absolute;left:0;right:0;bottom:0;z-index:3;padding:0 40px 16px;text-align:center;}
.pc-fn{font-family:'Bebas Neue',sans-serif;font-size:48px;line-height:.9;letter-spacing:2px;color:$accent2;
 text-transform:uppercase;text-shadow:0 3px 12px rgba(0,0,0,.75);}
.pc-ln{font-family:'Bebas Neue',sans-serif;font-size:110px;line-height:.86;letter-spacing:1px;color:#fff;
 text-transform:uppercase;text-shadow:0 6px 20px rgba(0,0,0,.78);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
.pc-pill{display:inline-block;margin-top:12px;padding:9px 42px;border-radius:30px;font-family:'Oswald',sans-serif;
 font-size:22px;font-weight:700;letter-spacing:4px;text-transform:uppercase;color:#fff;
 background:-webkit-linear-gradient(left,$badge1,$badge2);box-shadow:0 8px 22px rgba(0,0,0,.45);}

.pc-grid{position:relative;z-index:8;padding:20px 40px 0;overflow:hidden;}
.pc-tile{float:left;width:48%;height:104px;margin:0 0 14px 0;padding:0 16px;
 border-radius:16px;border:1px solid $line;
 background:-webkit-linear-gradient(top left, rgba(255,255,255,0.08), rgba(255,255,255,0.02));box-shadow:0 6px 18px rgba(0,0,0,.35);}
.pc-tile.nomr{float:right;margin-right:0;}
.pc-tin{display:table;width:100%;height:104px;}
.pc-ic{display:table-cell;width:52px;vertical-align:middle;}
.pc-ibox{width:52px;height:52px;border-radius:13px;background-color:rgba(0,0,0,.28);border:1px solid $line;
 text-align:center;line-height:50px;overflow:hidden;color:$accent;}
.pc-ibox svg{width:30px;height:30px;vertical-align:middle;}
.pc-ilogo{width:52px;height:52px;background-size:contain;background-position:center;background-repeat:no-repeat;}
.pc-txt{display:table-cell;vertical-align:middle;padding-left:14px;}
.pc-lbl{font-family:'Oswald',sans-serif;font-size:14px;font-weight:600;letter-spacing:2px;color:$sub;
 text-transform:uppercase;line-height:1.1;}
.pc-val{font-family:'Rajdhani',sans-serif;font-size:26px;font-weight:700;color:$accent2;text-transform:uppercase;
 line-height:1.1;margin-top:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:250px;}

.pc-foot{position:relative;z-index:8;height:120px;padding:22px 52px 0;}
.pc-foot .ln{position:absolute;top:0;left:52px;right:52px;height:2px;
 background:-webkit-linear-gradient(left, rgba(255,255,255,0) 0%, $accent 50%, rgba(255,255,255,0) 100%);}
.pc-brand{display:inline-block;font-family:'Bebas Neue',sans-serif;font-size:30px;letter-spacing:3px;color:#fff;text-transform:uppercase;}
.pc-brand b{color:$accent;}
.pc-fsub{float:right;font-family:'Oswald',sans-serif;font-size:14px;font-weight:600;letter-spacing:3px;color:$sub;
 text-transform:uppercase;line-height:30px;max-width:520px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
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
    photo = fields.Binary("Photo", default=_get_default_player_photo)
    photo_card = fields.Binary(
        string='Photo (Card Print)',
        compute='_compute_photo_card',
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

    @api.depends('photo')
    def _compute_photo_card(self):
        """Return a resized, JPEG-compressed copy of the player photo for card PDF printing.
        Reduces per-page image size from ~200KB to ~15-30KB, significantly cutting PDF size and wkhtmltopdf time."""
        for player in self:
            if player.photo:
                try:
                    player.photo_card = image_process(
                        player.photo,
                        size=(400, 500),
                        quality=70,
                        output_format='JPEG',
                    )
                except Exception:
                    player.photo_card = player.photo
            else:
                player.photo_card = False

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
        # Use the player's own tournament theme, not the globally "active" tournament
        tournament = self[0].tournament_id if self else None
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
    #  Bulk portrait player-card image export (ZIP of PNGs)
    #  Replaces the old portrait PDF report. Renders a premium 1080x1350
    #  IPL-style card per selected player via headless Chromium and streams
    #  a single ZIP archive back to the browser.
    # ══════════════════════════════════════════════════════════════════
    _CARD_W = 1080
    _CARD_H = 1350

    _FOOT_LABELS = {'left': 'Left Foot', 'right': 'Right Foot', 'both': 'Both Feet'}

    _CARD_ICONS = {
        'bat': '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M14.5 3.5l6 6"/><path d="M18 6l-9.5 9.5"/><path d="M8.5 15.5l-4.2 4.2a1.5 1.5 0 01-2.1-2.1L6.4 13.4z"/><circle cx="5" cy="19" r="0.6" fill="currentColor"/></svg>',
        'ball': '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><circle cx="12" cy="12" r="8.5"/><path d="M12 3.5v17"/><path d="M9 4.2c1.6 4.8 1.6 10.8 0 15.6M15 4.2c-1.6 4.8-1.6 10.8 0 15.6" stroke-dasharray="2 2"/></svg>',
        'position': '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><circle cx="12" cy="12" r="8.5"/><circle cx="12" cy="12" r="4"/><circle cx="12" cy="12" r="0.8" fill="currentColor"/></svg>',
        'foot': '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"><path d="M8 3c1.6 0 2.5 1.4 2.7 3.2.2 1.8.5 3.3 1.4 4.6.8 1.2 1.9 2 1.9 3.9 0 2.4-1.8 4.3-4.3 4.3-2.2 0-3.7-1.4-3.7-3.6 0-1.3.3-2.2.3-3.6C6.3 12 5 9.4 5 6.8 5 4.6 6.2 3 8 3z"/></svg>',
        'age': '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"><rect x="3.5" y="5" width="17" height="15.5" rx="2.2"/><path d="M3.5 9.5h17M8 3v4M16 3v4"/></svg>',
        'category': '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"><path d="M20.5 12.5l-8 8-9-9V4h7.5z"/><circle cx="8" cy="8" r="1.4" fill="currentColor"/></svg>',
        'location': '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"><path d="M12 21.5c4.5-4.8 7-8.3 7-11.5a7 7 0 10-14 0c0 3.2 2.5 6.7 7 11.5z"/><circle cx="12" cy="10" r="2.6"/></svg>',
        'price': '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="8.5"/><path d="M9 8h6M9 11h6M14 8c0 3-2 4-4.5 4L15 16.5"/></svg>',
        'team': '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"><path d="M12 3l7 2.5v5c0 4.5-3 8-7 9.5-4-1.5-7-5-7-9.5v-5z"/><path d="M9.5 12l1.8 1.8 3.5-3.6"/></svg>',
        'blood': '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"><path d="M12 3s6 6.4 6 10.5A6 6 0 016 13.5C6 9.4 12 3 12 3z"/></svg>',
        'height': '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"><path d="M12 3v18M8 6l4-3 4 3M8 18l4 3 4-3"/></svg>',
    }

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
        """A private temp working dir for the HTML/PNG intermediates."""
        import tempfile
        return tempfile.mkdtemp(prefix='ac_cards_')

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
    def _card_safe_filename(name, used):
        base = re.sub(r'[^A-Za-z0-9]+', '_', (name or 'Player').strip()).strip('_') or 'Player'
        candidate = base
        i = 1
        while candidate.lower() in used:
            i += 1
            candidate = '%s_%d' % (base, i)
        used.add(candidate.lower())
        return candidate + '.png'

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

        prefix = ''
        source = (team.name if team and team.name else (tournament.name if tournament else '')) or ''
        prefix = ''.join(w[0] for w in source.split()[:2]).upper() or 'PL'
        card_id = '%s-%03d' % (prefix, player.sl_no or 0)

        if is_football:
            badge = (player.dominant_position_id.name if player.dominant_position_id
                     else (player.role or player.p_category or 'PLAYER'))
        else:
            badge = player.role or player.p_category or 'PLAYER'

        rows = []
        if is_football:
            if player.dominant_position_id:
                rows.append(('position', 'Position', player.dominant_position_id.name))
            if player.preferred_foot:
                rows.append(('foot', 'Preferred Foot', self._FOOT_LABELS.get(player.preferred_foot, player.preferred_foot.title())))
        else:
            if player.batting_style:
                rows.append(('bat', 'Batting Style', player.batting_style))
            if player.bowling_style:
                rows.append(('ball', 'Bowling Style', player.bowling_style))
        if player.age:
            rows.append(('age', 'Age', '%s Years' % player.age))
        if player.p_category:
            rows.append(('category', 'Category', player.p_category))
        if len(rows) < 5 and player.address:
            rows.append(('location', 'Location', (player.address or '').strip().splitlines()[0] if player.address else ''))
        rows.append(('price', 'Base Price', u'\u20B9 %s' % self._card_indian_amount(player.base_price)))
        rows.append(('team', 'Team', team.name if team else 'Unsold'))
        # 2-column grid, keep the six most relevant tiles
        rows = [{'icon': i, 'label': l, 'value': v, 'nomr': (idx % 2 == 1)}
                for idx, (i, l, v) in enumerate(rows[:6])]

        def uri(binary_val):
            try:
                return image_data_uri(binary_val) if binary_val else ''
            except Exception:
                return ''

        pal['line'] = 'rgba(255,255,255,0.12)'
        pal['glow'] = (pal['accent'] or '#e9c15a') + '55'
        import string
        css = string.Template(_CARD_CSS).safe_substitute(pal)

        return {
            'player': player,
            'tournament': tournament,
            'team': team,
            'is_football': is_football,
            'pal': pal,
            'css': css,
            'icons': self._CARD_ICONS,
            'photo_uri': uri(player.photo),
            'team_logo_uri': uri(team.logo) if team else '',
            'tournament_logo_uri': uri(tournament.logo) if tournament else '',
            'name_first': name_first,
            'name_last': name_last,
            'card_id': card_id,
            'badge': badge,
            'rows': rows,
        }

    def _render_card_html(self, player):
        values = self._card_values(player)
        html = self.env['ir.qweb']._render('auction_module.player_card_portrait_image', values)
        if isinstance(html, bytes):
            html = html.decode('utf-8')
        return str(html)

    def _card_html_to_png(self, html, workdir, binary):
        import subprocess
        import uuid as _uuid
        base = os.path.join(workdir, _uuid.uuid4().hex)
        hpath, opath = base + '.html', base + '.png'
        with open(hpath, 'w', encoding='utf-8') as fh:
            fh.write(html)
        cmd = [
            binary, '--format', 'png',
            '--width', str(self._CARD_W), '--disable-smart-width',
            '--enable-local-file-access', '--javascript-delay', '1800',
            '--quiet', hpath, opath,
        ]
        try:
            proc = subprocess.run(cmd, timeout=120, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except subprocess.TimeoutExpired:
            _logger.warning('wkhtmltoimage timed out rendering a player card')
            return None
        if os.path.exists(opath) and os.path.getsize(opath) > 0:
            with open(opath, 'rb') as fh:
                return fh.read()
        _logger.warning('wkhtmltoimage produced no image (rc=%s). stderr: %s',
                        proc.returncode, (proc.stderr or b'')[-800:].decode('utf-8', 'replace'))
        return None

    def action_download_player_cards(self):
        import io
        import shutil
        import zipfile
        from datetime import datetime

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
        try:
            with zipfile.ZipFile(zip_buf, 'w', zipfile.ZIP_DEFLATED) as zf:
                for player in players:
                    try:
                        html = self._render_card_html(player)
                        png = self._card_html_to_png(html, workdir, binary)
                        if not png:
                            raise ValueError('empty render output')
                        fname = self._card_safe_filename(player.name or ('player_%s' % player.id), used_names)
                        zf.writestr(fname, png)
                    except Exception:
                        _logger.exception('Player card export failed for player %s', player.id)
                        failed.append(player.name or ('#%s' % player.id))
                if failed:
                    note = (u'%d card(s) failed to generate:\n\n%s' % (len(failed), u'\n'.join(failed)))
                    zf.writestr('_FAILED_CARDS.txt', note.encode('utf-8'))
        finally:
            shutil.rmtree(workdir, ignore_errors=True)

        if len(failed) == len(players):
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
        print(vals, "After printing vals")
        return player

    def write(self, vals):
        if 'photo_url' in vals:
            image_base64 = self.get_base64_from_url(vals.get('photo_url', False))
            if image_base64:
                vals.update({'photo': image_base64})
        res = super(AuctionTeamPlayer, self).write(vals)
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
