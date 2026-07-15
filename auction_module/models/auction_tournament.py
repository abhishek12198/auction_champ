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

import re
import random
import time
import logging
import unicodedata
import base64

from psycopg2 import OperationalError

from odoo import api, models, fields, _
from odoo.exceptions import UserError
from odoo.tools.image import image_data_uri, image_process
from odoo.exceptions import UserError, ValidationError

import werkzeug
import werkzeug.exceptions

_logger = logging.getLogger(__name__)


def _generate_tournament_code(env):
    """Generate a unique AC#XXXXXXXXXXXX code (12 random digits)."""
    while True:
        digits = ''.join([str(random.randint(0, 9)) for _ in range(12)])
        code = 'AC#' + digits
        if not env['auction.tournament'].sudo().search([('tournament_code', '=', code)], limit=1):
            return code


def _slugify(text):
    """Convert a tournament name to a URL-friendly slug.
    E.g. 'SAKTHI BROTHERS PREMIER LEAGUE' → 'sakthi-brothers-premier-league'
    """
    value = unicodedata.normalize('NFKD', text or '').encode('ascii', 'ignore').decode('ascii')
    value = value.lower()
    value = re.sub(r'[^\w\s-]', '', value)
    value = re.sub(r'[\s_]+', '-', value)
    return value.strip('-')


class AuctionTournament(models.Model):
    _name = 'auction.tournament'
    _inherit = ['auction.image.compress.mixin', 'auction.tournament.security.mixin']

    # logo/poster: JPEG portrait; QR code: PNG (lossless) to keep it scannable;
    # template/footer: slightly larger for print quality.
    _compressible_image_fields = {
        'logo':              (400,  400,  82, 'JPEG'),
        'poster_image':      (900,  1200, 82, 'JPEG'),
        'payment_qr_image':  (600,  600,  0,  'PNG'),
        'template_image':    (1200, 900,  85, 'JPEG'),
        'report_footer':     (1200, 300,  85, 'JPEG'),
    }

    name = fields.Char(string="Name", required=True)
    slug = fields.Char(
        string='URL Slug',
        compute='_compute_slug',
        store=True,
        help='Auto-generated URL slug used in the player registration link. '
             'Recomputed automatically when the tournament name changes.',
    )
    description = fields.Char(string="Short Description", required=True)
    venue = fields.Text("Venue")
    auction_date = fields.Date(
        string="Auction Date",
        help="Date of the player auction. Shown on the projector screen.",
    )
    auction_venue = fields.Char(
        string="Auction Venue",
        help="Venue / arena name for the auction day. Shown on the projector screen.",
    )
    logo = fields.Binary('Logo')
    logo_card = fields.Binary(
        string='Logo (Card Print)',
        compute='_compute_logo_card',
        store=True,
        help='Small JPEG logo for player-card PDFs to keep bulk prints light.',
    )
    active = fields.Boolean(default=True)
    player_appearance_algorithm = fields.Selection([('linear', 'Manual'), ('random', 'Random')], default="linear")
    team_max_points = fields.Integer(string="Max points alloted for a team")
    organizer_uid = fields.Many2one('res.users', 'Organizer')
    points_split_ids = fields.One2many('auction.tournament.point.split', 'tournament_id', 'Points Split')

    organizer_uids = fields.Many2many('res.users', 'auction_tournament_user_rel', 'tournament_id', 'user_id',
                                      'Organizers')

    team_ids = fields.One2many('auction.team', 'tournament_id', 'Teams')
    other_attribute_label_ids = fields.One2many(
        'auction.tournament.attribute.label', 'tournament_id',
        string='Other Attribute Labels',
        help='Football only: define Att-Labels for this tournament. They appear as '
             'Excel template columns and as Label/Value rows on each player form.')
    template_image = fields.Binary('Template Image')
    report_footer = fields.Binary('Footer')
    rules_regulations = fields.Html("Rules and Regulations")
    tournament_type = fields.Selection([('cricket', 'Cricket'), ('football', 'Football'),('kabaddi', 'Kabaddi')], default='cricket')
    kanban_color = fields.Char(
        string='Kanban Color',
        default='#4f46e5',
        help='Hex color used to visually identify this tournament in kanban/list views.'
    )
    player_display_template = fields.Selection([
        ('vanilla', 'Vanilla'),
        ('butterscotch', 'Butterscotch'),
        ('strawberry', 'Strawberry'),
        ('cherry', 'Cherry'),
        ('pistah', 'Pistah'),
        ('lemon', 'Lemon'),
    ], string='Theme'
              '', default='vanilla', required=True)
    sold_display_seconds = fields.Integer(
        string='Sold Screen Duration (seconds)',
        default=5,
        help='How many seconds to show the SOLD celebration screen before advancing to the next player.'
    )
    # ── Live-board stamp tracking (set on sell/unsold, read by live-board endpoint) ──
    stamp_player_id   = fields.Many2one('auction.team.player', string='Stamp Player', copy=False)
    stamp_state       = fields.Char(string='Stamp State', copy=False)   # 'sold' | 'unsold'
    stamp_expires_at  = fields.Datetime(string='Stamp Expires At', copy=False)
    next_player_countdown = fields.Integer(
        string='Next Player Countdown (seconds)',
        default=5,
        help='How many seconds to count down on the "Next player out of the deck" overlay before revealing the new player.'
    )
    preset_points = fields.Char(
        string='Quick-Select Points',
        help='Comma-separated point values shown as quick-select buttons in the Sell Player modal. '
             'Example: 100,200,500,1000,1500'
    )
    tournament_date = fields.Date("Tournament Date", help="The date of the tournament, displayed on the player registration form.")
    expose_player_contact = fields.Boolean(
        string="Unmask Player Contact?",
        default=False,
        help="When enabled, players' full mobile numbers are shown on player cards and the "
             "auction display. When disabled (default), the numbers are masked (e.g. 9XXXXXXXX8).",
    )
    enable_jersey_section = fields.Boolean(
        "Jersy Included?",
        default=False,
        help="Show jersey customization fields (jersey name, number, size) in the public player registration form."
    )
    payment_instruction = fields.Text(
        string='Payment Instructions',
        help='Instructions shown in the Payment section of the player registration form. '
             'E.g. "Pay ₹500 via UPI to 9876543210@paytm and attach the screenshot below."',
    )
    payment_qr_image = fields.Binary(
        string='Payment QR / Scanner',
        help='Upload a UPI QR code or payment scanner image (PNG recommended). '
             'Players can scan it directly from the registration page to complete payment.',
    )
    poster_image = fields.Binary(
        string='Tournament Poster',
        help='Upload a tournament poster image. It will be displayed on the player registration page '
             'in the sidebar, above the "Why Register?" section.',
    )
    organizer_name = fields.Char(
        string='Organizer Name',
        help='Name of the person or organization running this tournament.',
    )
    organizer_contact = fields.Char(
        string='Organizer Contact',
        help='Mobile number or contact info for the tournament organizer.',
    )
    tournament_code = fields.Char(
        string='Tournament Code',
        readonly=True,
        copy=False,
        help='Unique identifier for this tournament, auto-generated on creation. '
             'Format: AC# followed by 12 digits.',
    )
    registration_open = fields.Boolean(
        "Registration Open",
        default=False,
        help="When enabled, the public player self-registration form is accessible. "
             "Disable this to close registrations at any point.",
    )
    whatsapp_group_link = fields.Char(
        string="WhatsApp Group Link",
        help="Paste the WhatsApp group invite link here. "
             "Players will see a 'Join WhatsApp Group' button on the registration success screen.",
    )
    live_board_active = fields.Boolean(
        string='Live Board Active',
        default=False,
        help='When enabled, the public /auction/live-board page streams live auction data. '
             'When disabled, visitors see an offline holding page instead.',
    )
    break_time_active = fields.Boolean(
        string='Break Time',
        default=False,
        help='When enabled, the live board shows a "Break Time" screen to viewers. '
             'The auction can continue in the background. Disable to resume the live display.',
    )
    auction_declared_complete = fields.Boolean(
        string='Auction Declared Complete',
        default=False,
        copy=False,
        help='When set, the display auction page shows the Thank You screen even if '
             'Draft or Unsold players remain. Cleared automatically when players are '
             'opened back into auction from the resume screen.',
    )
    advertiser_ids = fields.One2many(
        'auction.advertiser', 'tournament_id', string='Advertisers / Sponsors',
        help='Upload sponsor or advertiser images. They rotate on the live board '
             'and are displayed prominently during break time.',
    )
    max_registrations = fields.Integer(
        string='Max Registrations',
        default=0,
        help='Maximum number of players that can self-register (draft state). '
             'Set to 0 for unlimited. Registration closes automatically when this limit is reached.',
    )
    registered_player_count = fields.Integer(
        string='Registered Players',
        compute='_compute_player_state_counts',
        store=False,
        help='Current number of players in Draft state for this tournament.',
    )
    auction_player_count = fields.Integer(
        string='In Auction',
        compute='_compute_player_state_counts',
        store=False,
    )
    sold_player_count = fields.Integer(
        string='Sold',
        compute='_compute_player_state_counts',
        store=False,
    )
    unsold_player_count = fields.Integer(
        string='Unsold',
        compute='_compute_player_state_counts',
        store=False,
    )
    registration_url = fields.Char(
        string='Player Registration URL',
        compute='_compute_urls',
        store=False,
        help='Share this public link with players so they can self-register for the tournament.',
    )
    projector_url = fields.Char(
        string='Projector View URL',
        compute='_compute_urls',
        store=False,
        help='Open on the audience screen. Updates live while operators run '
             'display_auction (Random) or player_selector (Manual).',
    )
    payment_tracker_url = fields.Char(
        string='Payment Tracker URL',
        compute='_compute_urls',
        store=False,
        help='Direct link to the Payment Tracker page for this tournament.',
    )
    dice_state = fields.Selection(
        [('idle', 'Idle'), ('rolling', 'Rolling'), ('result', 'Result')],
        string='Dice State', default='idle',
        help='Live state of the dice roll broadcast to the projector.',
    )
    dice_result = fields.Integer(string='Dice Result', default=0)

    def _compute_player_state_counts(self):
        """Compute all four player-state counts in a single read_group call.

        Uses active_test=False so that players belonging to a deactivated
        (archived) tournament — which are themselves archived — are still
        counted. This keeps the stat buttons accurate for inactive tournaments.
        """
        groups = self.env['auction.team.player'].sudo().with_context(active_test=False).read_group(
            [('tournament_id', 'in', self.ids)],
            ['tournament_id', 'state'],
            ['tournament_id', 'state'],
            lazy=False,
        )
        # Build nested dict: {tournament_id: {state: count}}
        counts = {}
        for g in groups:
            tid = g['tournament_id'][0]
            state = g['state']
            counts.setdefault(tid, {})[state] = g['__count']
        for rec in self:
            c = counts.get(rec.id, {})
            rec.registered_player_count = c.get('draft', 0)
            rec.auction_player_count    = c.get('auction', 0)
            rec.sold_player_count       = c.get('sold', 0)
            rec.unsold_player_count     = c.get('unsold', 0)

    @api.depends('name')
    @api.depends('logo')
    def _compute_logo_card(self):
        for tournament in self:
            if tournament.logo:
                try:
                    tournament.logo_card = image_process(
                        tournament.logo,
                        size=(96, 96),
                        quality=60,
                        output_format='JPEG',
                    )
                except Exception:
                    tournament.logo_card = tournament.logo
            else:
                tournament.logo_card = False

    @api.depends('name')
    def _compute_slug(self):
        for rec in self:
            rec.slug = _slugify(rec.name or '')

    @api.depends('slug', 'player_appearance_algorithm')
    def _compute_urls(self):
        # Both URL fields share one get_param() call to avoid two DB hits per form load.
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url', '')
        db_name = self.env.cr.dbname
        for rec in self:
            if rec.slug:
                rec.registration_url = '{}/{}/{}/player/register'.format(base_url, db_name, rec.slug)
            else:
                rec.registration_url = '{}/{}/player/register'.format(base_url, db_name)

            if rec.slug:
                rec.projector_url = '{}/{}/auction/projector/{}/'.format(base_url, db_name, rec.slug)
            else:
                rec.projector_url = False

            if rec.slug:
                rec.payment_tracker_url = '{}/{}/{}/auction/payment-marker'.format(base_url, db_name, rec.slug)
            else:
                rec.payment_tracker_url = False

    def set_dice_state(self, state, number=0):
        """Broadcast dice state to the projector.

        Uses a narrow SQL update with short retries so concurrent tournament
        writes (sell/unsold stamp, etc.) do not fail the dice roll with
        ``could not serialize access due to concurrent update``.
        """
        valid = {'idle', 'rolling', 'result'}
        if state not in valid:
            state = 'idle'
        number = int(number or 0)
        ids = tuple(self.ids)
        if not ids:
            return True
        uid = self.env.uid or 1
        for attempt in range(6):
            try:
                with self.env.cr.savepoint():
                    self.env.cr.execute(
                        """
                        UPDATE auction_tournament
                           SET dice_state = %s,
                               dice_result = %s,
                               write_uid = %s,
                               write_date = (now() AT TIME ZONE 'UTC')
                         WHERE id IN %s
                        """,
                        (state, number, uid, ids),
                    )
                self.invalidate_cache(['dice_state', 'dice_result'])
                return True
            except OperationalError as err:
                msg = str(err).lower()
                if 'could not serialize' not in msg and 'deadlock' not in msg:
                    raise
                if attempt >= 5:
                    _logger.warning(
                        'set_dice_state(%s, %s) skipped after concurrent '
                        'updates on tournament %s: %s',
                        state, number, ids, err,
                    )
                    return False
                time.sleep(0.05 * (attempt + 1))
        return False

    @api.model
    def create(self, vals):
        if not vals.get('tournament_code'):
            vals['tournament_code'] = _generate_tournament_code(self.env)
        return super().create(vals)

    def write(self, vals):
        """Restrict non-admin users to only modifying operational/balance fields.

        sudo() calls (env.su=True) bypass this check entirely — internal model
        methods that use sudo() must never be blocked here.
        """
        if (not self.env.su
                and not self.env.user.has_group('auction_module.group_auction_group_admin')):
            _ALLOWED = {
                # team balance & payment config
                'team_max_points', 'payment_qr_image', 'payment_instruction',
                # live-board stamp — written during SOLD / UNSOLD / NEXT-PLAYER
                'stamp_player_id', 'stamp_state', 'stamp_expires_at',
                # live-board controls
                'live_board_active', 'break_time_active',
                # registration toggle
                'registration_open',
                # dice / player-selector
                'dice_state', 'dice_result',
            }
            disallowed = set(vals.keys()) - _ALLOWED
            if disallowed:
                raise UserError(
                    _("You do not have permission to modify: %s")
                    % ', '.join(sorted(disallowed))
                )
        res = super().write(vals)
        # When organizers are assigned, ensure each user has Active Tournament set
        # so record rules / dashboard scoping work (rules use tournament_id + tournament_ids).
        if 'organizer_uids' in vals:
            for tournament in self:
                for user in tournament.organizer_uids:
                    updates = {}
                    if not user.tournament_id:
                        updates['tournament_id'] = tournament.id
                    if tournament not in user.tournament_ids:
                        updates.setdefault('tournament_ids', [])
                        updates['tournament_ids'] = [(4, tournament.id)]
                    if updates:
                        user.with_context(skip_tournament_sync=True).sudo().write(updates)
        return res

    def action_toggle_registration(self):
        """Toggle the registration open/closed state."""
        for rec in self:
            rec.registration_open = not rec.registration_open

    def _player_state_action(self, state, label):
        """Generic helper — returns an act_window filtered by player state."""
        self.ensure_one()
        ctx = {'default_tournament_id': self.id}
        # A deactivated tournament has archived players; show them so the list
        # matches the stat-button count instead of appearing empty.
        if not self.active:
            ctx['active_test'] = False
        return {
            'type': 'ir.actions.act_window',
            'name': '%s — %s' % (label, self.name),
            'res_model': 'auction.team.player',
            'view_mode': 'tree,form,kanban',
            'views': [
                (self.env.ref('auction_module.view_auction_team_player_tree').id, 'tree'),
                (self.env.ref('auction_module.view_auction_team_player_form').id, 'form'),
                (self.env.ref('auction_module.view_auction_team_player_kanban').id, 'kanban'),
            ],
            'domain': [('tournament_id', '=', self.id), ('state', '=', state)],
            'context': ctx,
        }

    def action_view_registered_players(self):
        return self._player_state_action('draft', 'Registered Players')

    def action_view_auction_players(self):
        return self._player_state_action('auction', 'In Auction Players')

    def action_view_sold_players(self):
        return self._player_state_action('sold', 'Sold Players')

    def action_view_unsold_players(self):
        return self._player_state_action('unsold', 'Unsold Players')

    def action_set_auction_rules(self):
        """Open the Auction Rules wizard scoped to this tournament."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Set Auction Rules — %s') % self.name,
            'res_model': 'auction.start.auction',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_tournament_id': self.id},
        }

    def action_view_auction_rules(self):
        """Open the auction (team rule) records belonging to this tournament."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Auction Rules — %s') % self.name,
            'res_model': 'auction.auction',
            'view_mode': 'tree,form',
            'views': [
                (self.env.ref('auction_module.view_auction_auction_tree').id, 'tree'),
                (self.env.ref('auction_module.view_auction_auction_form').id, 'form'),
            ],
            'domain': [('tournament_id', '=', self.id)],
            'context': {'default_tournament_id': self.id},
        }

    def action_view_jersey_players(self):
        """Open the jersey view for sold/in-auction players in this tournament."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Jersey View — %s' % self.name,
            'res_model': 'auction.team.player',
            'view_mode': 'kanban,tree,form',
            'views': [
                (self.env.ref('auction_module.view_auction_team_player_jersy_kanban').id, 'kanban'),
                (self.env.ref('auction_module.view_auction_team_player_jersy_tree').id, 'tree'),
                (self.env.ref('auction_module.view_auction_team_player_form').id, 'form'),
            ],
            'domain': [('tournament_id', '=', self.id), ('state', 'not in', ['draft', 'unsold'])],
            'context': {'default_tournament_id': self.id},
        }

    def action_toggle_live_board(self):
        """Toggle the live board active/stopped state."""
        for rec in self:
            rec.live_board_active = not rec.live_board_active

    def action_toggle_break_time(self):
        """Toggle the break time screen on the live board."""
        for rec in self:
            rec.break_time_active = not rec.break_time_active

    def action_set_break_time(self, active=True):
        """Explicitly enable/disable break time (projector + live board)."""
        active = bool(active)
        for rec in self:
            rec.break_time_active = active
        return active

    def action_clear_stage(self):
        """Clear the is_on_stage flag from all players in this tournament."""
        for rec in self:
            self.env['auction.team.player'].sudo().search([
                ('tournament_id', '=', rec.id),
                ('is_on_stage', '=', True),
            ]).write({'is_on_stage': False})

    def action_clear_auction_history(self):
        """Permanently delete auction.history rows for this tournament only."""
        History = self.env['auction.history'].sudo().with_context(active_test=False)
        for rec in self:
            history = History.search([('tournament_id', '=', rec.id)])
            count = len(history)
            if history:
                history.unlink()
            message = _(
                'Cleared %(count)s auction history record(s) for "%(name)s".'
            ) % {'count': count, 'name': rec.name}
            if hasattr(self.env.user, 'notify_success'):
                self.env.user.notify_success(message)
        return True

    def action_deactivate_tournament(self):
        """Archive the tournament and all its related records.

        Archives in order:
          1. Players   (auction.team.player)
          2. Auctions  (auction.auction)
          3. History   (auction.history)
          4. Teams     (auction.team)
          5. Advertisers/Sponsors (auction.advertiser)
          6. The tournament itself

        Uses sudo() throughout so the operation succeeds regardless of
        which user triggers it (organizer vs admin).
        """
        for rec in self:
            # 1. Players
            self.env['auction.team.player'].sudo().with_context(active_test=False).search([
                ('tournament_id', '=', rec.id),
            ]).write({'active': False})

            # 2. Auction (team auction records — also covers bid slabs / tier limits
            #    through their parent being inactive)
            self.env['auction.auction'].sudo().with_context(active_test=False).search([
                ('tournament_id', '=', rec.id),
            ]).write({'active': False})

            # 3. Auction history
            self.env['auction.history'].sudo().with_context(active_test=False).search([
                ('tournament_id', '=', rec.id),
            ]).write({'active': False})

            # 4. Teams
            self.env['auction.team'].sudo().with_context(active_test=False).search([
                ('tournament_id', '=', rec.id),
            ]).write({'active': False})

            # 5. Advertisers / sponsors
            self.env['auction.advertiser'].sudo().with_context(active_test=False).search([
                ('tournament_id', '=', rec.id),
            ]).write({'active': False})

            # 6. Archive the tournament itself
            rec.sudo().write({'active': False})

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'auction.tournament',
            'view_mode': 'kanban,list,form',
            'target': 'current',
        }

    def action_open_registration_link(self):
        """Open the public player registration form in a new browser tab."""
        db_name = self.env.cr.dbname
        url = '/{}/{}/player/register'.format(db_name, self.slug) if self.slug else '/{}/player/register'.format(db_name)
        return {
            'type': 'ir.actions.act_url',
            'url': url,
            'target': 'new',
        }

    def action_open_payment_tracker(self):
        """Open the Payment Tracker page in a new browser tab."""
        db_name = self.env.cr.dbname
        url = '/{}/{}/auction/payment-marker'.format(db_name, self.slug) if self.slug else '/auction/my/payment-marker'
        return {
            'type': 'ir.actions.act_url',
            'url': url,
            'target': 'new',
        }

    def action_share_whatsapp(self):
        """Open the WhatsApp Share wizard for this tournament.

        Builds a ready-to-send message containing the tournament name, date,
        venue, player registration URL, and WhatsApp group link (if set).
        The wizard lets the organiser preview the poster, copy the message, or
        open WhatsApp directly with the text pre-filled.
        """
        self.ensure_one()
        import urllib.parse

        # ── Compose message ──────────────────────────────────────────────────
        lines = ['🏆 *{}*'.format(self.name)]

        if self.description:
            lines.append(self.description)

        if self.tournament_date:
            lines.append('📅 *Date:* {}'.format(
                self.tournament_date.strftime('%d %B %Y')
            ))

        if self.venue:
            venue_text = self.venue.strip()
            lines.append('📍 *Venue:*\n{}'.format(venue_text))

        if self.registration_url:
            lines.append('\n📝 *Register here:*\n{}'.format(self.registration_url))

        if self.whatsapp_group_link:
            lines.append('💬 *Join our WhatsApp Group:*\n{}'.format(self.whatsapp_group_link))

        message = '\n'.join(lines)
        whatsapp_url = 'https://api.whatsapp.com/send?text={}'.format(
            urllib.parse.quote(message, safe='')
        )

        wizard = self.env['auction.whatsapp.share.wizard'].create({
            'tournament_id': self.id,
            'message': message,
            'whatsapp_url': whatsapp_url,
        })
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'auction.whatsapp.share.wizard',
            'res_id': wizard.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_remove_duplicates(self):
        """Open the Remove Duplicate Players wizard for this tournament."""
        return {
            'type': 'ir.actions.act_window',
            'name': 'Remove Duplicate Players',
            'res_model': 'auction.remove.duplicates.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_tournament_id': self.id},
        }

    def action_upload_players(self):
        """Open the Excel + photo ZIP player uploader for this tournament."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Upload Players',
            'res_model': 'auction.player.upload.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_tournament_id': self.id},
        }
