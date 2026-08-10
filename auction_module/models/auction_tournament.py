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

import json
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
    player_appearance_algorithm = fields.Selection(
        [
            ('linear', 'Roll Call'),
            ('random', 'Lucky Dip'),
        ],
        string='Player Call-Up Mode',
        default='linear',
        help='How the next player is brought into the auction: '
             'Roll Call — pick from the set list or roll the dice for a squad number; '
             'Lucky Dip — draw the next player at random.',
    )
    team_max_points = fields.Integer(string="Max points alloted for a team")
    point_unit_id = fields.Many2one(
        'auction.point.unit',
        string='Player Value Unit',
        ondelete='restrict',
        # No Python default here: during module upgrade `_init_column` would
        # query auction.point.unit before that table exists. Defaults are
        # applied in create() and `_ensure_default_point_units`.
        help='Unit / sign shown with player values on live boards, consoles, '
             'and reports (e.g. PTS, ₹, $). Defaults to PTS.',
    )
    organizer_uid = fields.Many2one('res.users', 'Organizer')
    points_split_ids = fields.One2many('auction.tournament.point.split', 'tournament_id', 'Points Split')

    organizer_uids = fields.Many2many('res.users', 'auction_tournament_user_rel', 'tournament_id', 'user_id',
                                      'Organizers')

    team_ids = fields.One2many('auction.team', 'tournament_id', 'Teams')
    tier_ids = fields.One2many(
        'auction.player.tier', 'tournament_id',
        string='Player Tiers',
        help='Player tiers for this tournament (e.g. DEFAULT, A, B). '
             'A DEFAULT tier is created automatically when the tournament is created.',
    )
    other_attribute_label_ids = fields.One2many(
        'auction.tournament.attribute.label', 'tournament_id',
        string='Other Attribute Labels',
        help='Football only: define Att-Labels for this tournament. They appear as '
             'Excel template columns and as Label/Value rows on each player form.')
    template_image = fields.Binary('Template Image')
    report_footer = fields.Binary('Footer')
    rules_regulations = fields.Html("Rules and Regulations")
    tournament_type = fields.Selection(
        [
            ('cricket', 'Cricket'),
            ('football', 'Football'),
            ('kabaddi', 'Kabaddi (Coming Soon)'),
        ],
        default='cricket',
        string='Game / Sport',
    )
    kanban_color = fields.Char(
        string='Kanban Color',
        default='#4f46e5',
        help='Hex color used to visually identify this tournament in kanban/list views.'
    )
    player_display_template = fields.Selection([
        ('lemon', 'Lemon'),
        ('vanilla', 'Vanilla'),
        ('butterscotch', 'Butterscotch'),
        ('strawberry', 'Strawberry'),
        ('cherry', 'Cherry'),
        ('pistah', 'Pistah'),
        ('blackberry', 'Blackberry'),
    ], string='Theme'
              '', default='lemon', required=True)
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
    tournament_date_ids = fields.One2many(
        'auction.tournament.date',
        'tournament_id',
        string='Tournament Dates (Lines)',
        help='Internal date lines. Prefer editing Tournament Dates.',
    )
    tournament_dates = fields.Char(
        string='Tournament Dates',
        help='One or more tournament days. Pick dates from the calendar; each appears as a tag.',
    )
    tournament_date = fields.Date(
        string='Tournament Date',
        help='Earliest tournament date (kept for sorting / compatibility). '
             'Add all days under Tournament Dates.',
    )
    tournament_date_display = fields.Char(
        string='Tournament Dates (Display)',
        compute='_compute_tournament_date_display',
        help='Formatted multi-day label used on registration forms, cards, and shares.',
    )
    expose_player_contact = fields.Boolean(
        string="Unmask Player Contact?",
        default=False,
        help="When enabled, players' full mobile numbers are shown on player cards and the "
             "auction display. When disabled (default), the numbers are masked (e.g. 9XXXXXXXX8). "
             "Enabling requires accepting the privacy policy; the agreement is stored with "
             "user and timestamp.",
    )
    expose_player_contact_privacy_agreed = fields.Boolean(
        string="Contact Unmask Privacy Agreed",
        default=False,
        copy=False,
        readonly=True,
        help="True after the organizer accepted the privacy policy to unmask player contacts.",
    )
    expose_player_contact_agreed_user_id = fields.Many2one(
        'res.users',
        string="Agreed By",
        copy=False,
        readonly=True,
        help="User who accepted the privacy policy to unmask player contacts.",
    )
    expose_player_contact_agreed_date = fields.Datetime(
        string="Agreed On",
        copy=False,
        readonly=True,
        help="When the privacy policy was accepted for unmasking player contacts.",
    )
    expose_player_contact_policy_version = fields.Char(
        string="Privacy Policy Version",
        copy=False,
        readonly=True,
        help="Policy version / effective date acknowledged when unmasking was enabled.",
    )
    enable_jersey_section = fields.Boolean(
        "Jersy Included?",
        default=False,
        help="Show jersey customization fields (jersey name, number, size) in the public player registration form."
    )
    enable_org_id_registration = fields.Boolean(
        string="Show Org ID# in Registration",
        default=False,
        help="Show the optional organisation unique ID field on the public player registration form.",
    )
    payment_instruction = fields.Text(
        string='Payment Instructions',
        help='Instructions shown in the Payment section of the player registration form. '
             'E.g. "Pay ₹500 via UPI to 9876543210@paytm and attach the screenshot below."',
    )
    payment_proof_required = fields.Boolean(
        string='Payment Attachment Required',
        default=False,
        help='When enabled, players must upload a payment proof attachment on the '
             'public registration form. When disabled, the upload is optional.',
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
        index=True,
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
    live_board_code_protected = fields.Boolean(
        string='Protect Live Board with Tournament Code',
        default=True,
        help='When enabled, public viewers must enter the Tournament Code once before '
             'they can open the live board. After a successful unlock, that browser is '
             'remembered (session + cookie) so they do not need to re-enter the code. '
             'When disabled, anyone with the live board URL can view it without a code.',
    )
    pool_draw_json = fields.Text(
        string='Saved Pool Draw',
        copy=False,
        help='JSON of the last saved pool draw from the Pool Generator.',
    )
    fixture_schedule_json = fields.Text(
        string='Saved Fixture Schedule',
        copy=False,
        help='JSON of the last saved fixture schedule from the Pool Generator.',
    )
    pool_draw_snapshot = fields.Binary(
        string='Pool Draw Snapshot',
        copy=False,
        attachment=True,
        help='PNG snapshot of the saved pool draw board.',
    )
    fixture_schedule_snapshot = fields.Binary(
        string='Fixture Snapshot',
        copy=False,
        attachment=True,
        help='PNG snapshot of the saved fixture schedule board.',
    )
    pool_draw_user_id = fields.Many2one(
        'res.users',
        string='Pool Generated By',
        copy=False,
        readonly=True,
        help='User who last generated or saved the pool draw.',
    )
    pool_draw_datetime = fields.Datetime(
        string='Pool Generated On',
        copy=False,
        readonly=True,
        help='When the pool draw was last generated or saved.',
    )
    fixture_schedule_user_id = fields.Many2one(
        'res.users',
        string='Fixture Generated By',
        copy=False,
        readonly=True,
        help='User who last generated or saved the fixture schedule.',
    )
    fixture_schedule_datetime = fields.Datetime(
        string='Fixture Generated On',
        copy=False,
        readonly=True,
        help='When the fixture schedule was last generated or saved.',
    )
    projector_board_mode = fields.Selection(
        [
            ('idle', 'Hidden'),
            ('pools', 'Pool Draw'),
            ('fixtures', 'Fixtures'),
        ],
        string='Projector Board',
        default='idle',
        copy=False,
        help='When set to pools/fixtures, the projector shows that board live '
             '(updated when pools or fixtures are generated).',
    )
    projector_board_reveal_until = fields.Datetime(
        string='Projector Reveal Until',
        copy=False,
        help='While in the future, projector shows a loading/reveal animation '
             'before displaying the pool or fixture board.',
    )

    def _snapshot_download_filename(self, kind):
        """Safe PNG filename for pool/fixture snapshot downloads."""
        self.ensure_one()
        base = (self.slug or self.name or 'tournament').strip()
        base = re.sub(r'[^\w\-]+', '_', base).strip('_') or 'tournament'
        return '%s_%s.png' % (base, kind)

    def action_download_pool_draw_snapshot(self):
        """Download the saved pool draw PNG from Pools & Fixtures."""
        self.ensure_one()
        if not self.pool_draw_snapshot:
            raise UserError(_('No pool draw snapshot is saved yet. '
                              'Save from the Pool Generator first.'))
        filename = self._snapshot_download_filename('pool_draw')
        return {
            'type': 'ir.actions.act_url',
            'url': '/web/content/auction.tournament/%d/pool_draw_snapshot/%s?download=true' % (
                self.id, filename,
            ),
            'target': 'self',
        }

    def action_download_fixture_schedule_snapshot(self):
        """Download the saved fixture schedule PNG from Pools & Fixtures."""
        self.ensure_one()
        if not self.fixture_schedule_snapshot:
            raise UserError(_('No fixture snapshot is saved yet. '
                              'Save from the Pool Generator first.'))
        filename = self._snapshot_download_filename('fixture_schedule')
        return {
            'type': 'ir.actions.act_url',
            'url': '/web/content/auction.tournament/%d/fixture_schedule_snapshot/%s?download=true' % (
                self.id, filename,
            ),
            'target': 'self',
        }

    def action_dismiss_projector_board(self):
        """Hide live pool/fixture overlay so the projector returns to auction view.

        Generating pools/fixtures sets ``projector_board_mode`` to pools/fixtures.
        Opening Player Showcase / putting a player on stage must clear that mode,
        otherwise the projector keeps showing the old board instead of the player.
        """
        to_clear = self.filtered(
            lambda t: (t.projector_board_mode and t.projector_board_mode != 'idle')
            or bool(t.projector_board_reveal_until)
        )
        if to_clear:
            to_clear.sudo().write({
                'projector_board_mode': 'idle',
                'projector_board_reveal_until': False,
            })
        return True

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
    show_registration_capacity = fields.Boolean(
        string='Show Registration Capacity',
        default=True,
        help='When enabled, the public player registration form shows the '
             'Registration Capacity slab (slots left / progress). '
             'Turn off to hide that slab from players while still enforcing Max Registrations.',
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
    admin_registration_url = fields.Char(
        string='Admin Registration URL',
        compute='_compute_urls',
        store=False,
        help='Organiser-only registration link. Unlock once with the tournament code; '
             'stays available until Max Registrations is reached even if public registration is closed.',
    )
    projector_url = fields.Char(
        string='Projector View URL',
        compute='_compute_urls',
        store=False,
        help='Open on the audience screen. Updates live while operators run '
             'display_auction (Random) or player_selector (Manual). '
             'Available only after auction rules are set for this tournament.',
    )
    live_board_url = fields.Char(
        string='Live Board URL',
        compute='_compute_urls',
        store=False,
        help='Public share link for outsiders to watch the auction live '
             '(/…/auction/live-board). Board must be Live; optional Tournament Code gate applies.',
    )
    has_auction_rules = fields.Boolean(
        string='Auction Rules Set',
        compute='_compute_has_auction_rules',
        help='True when at least one auction rule (team purse / limits) exists '
             'for this tournament. Required before Player Console and Projector.',
    )
    auction_rule_ids = fields.One2many(
        'auction.auction', 'tournament_id', string='Auction Rules',
    )
    payment_tracker_url = fields.Char(
        string='Payment Tracker URL',
        compute='_compute_urls',
        store=False,
        help='Direct link to the Payment Tracker page for this tournament.',
    )
    bid_summary_url = fields.Char(
        string='Bid Summary URL',
        compute='_compute_urls',
        store=False,
        help='Public live bid summary / team balance dashboard '
             '(/…/auction/show/team/balance).',
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

    @api.depends('slug', 'player_appearance_algorithm', 'auction_rule_ids')
    def _compute_urls(self):
        # Both URL fields share one get_param() call to avoid two DB hits per form load.
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url', '')
        db_name = self.env.cr.dbname
        for rec in self:
            if rec.slug:
                rec.registration_url = '{}/{}/{}/player/register'.format(base_url, db_name, rec.slug)
                rec.admin_registration_url = '{}/{}/{}/player/register/admin'.format(
                    base_url, db_name, rec.slug)
            else:
                rec.registration_url = '{}/{}/player/register'.format(base_url, db_name)
                rec.admin_registration_url = False

            # Projector is only useful once team auction rules exist.
            if rec.slug and rec.auction_rule_ids:
                rec.projector_url = '{}/{}/auction/projector/{}/'.format(base_url, db_name, rec.slug)
            else:
                rec.projector_url = False

            # Public live board — shareable with outsiders (no auction-rules gate)
            if rec.slug:
                rec.live_board_url = '{}/{}/{}/auction/live-board'.format(
                    base_url, db_name, rec.slug)
            else:
                rec.live_board_url = False

            if rec.slug:
                rec.payment_tracker_url = '{}/{}/{}/auction/payment-marker'.format(base_url, db_name, rec.slug)
            else:
                rec.payment_tracker_url = False

            if rec.slug:
                rec.bid_summary_url = '{}/{}/{}/auction/show/team/balance'.format(
                    base_url, db_name, rec.slug)
            else:
                rec.bid_summary_url = False

    @api.depends('auction_rule_ids')
    def _compute_has_auction_rules(self):
        for rec in self:
            rec.has_auction_rules = bool(rec.auction_rule_ids)

    def has_auction_rules_ready(self):
        """True when this tournament has at least one auction.auction rule row."""
        self.ensure_one()
        return bool(self.env['auction.auction'].sudo().search_count([
            ('tournament_id', '=', self.id),
        ]))

    @api.depends('tournament_date_ids.date', 'tournament_date', 'tournament_dates')
    def _compute_tournament_date_display(self):
        for rec in self:
            rec.tournament_date_display = rec.format_tournament_dates()

    def _parse_tournament_dates_char(self, value=None):
        """Parse comma-separated ISO dates from tournament_dates Char field."""
        self.ensure_one()
        raw = value if value is not None else (self.tournament_dates or '')
        dates = []
        seen = set()
        for part in str(raw).split(','):
            part = (part or '').strip()
            if not part or part in seen:
                continue
            try:
                date_val = fields.Date.to_date(part)
            except Exception:
                continue
            seen.add(part)
            dates.append(date_val)
        return sorted(dates)

    def _tournament_dates_to_char(self, dates):
        return ','.join(fields.Date.to_string(d) for d in sorted(d for d in dates if d))

    def format_tournament_dates(self, fmt='%d %b %Y', joiner=' & '):
        """Return a human-readable label for one or more tournament dates."""
        self.ensure_one()
        dates = sorted(d for d in self.tournament_date_ids.mapped('date') if d)
        if not dates:
            dates = self._parse_tournament_dates_char()
        if not dates and self.tournament_date:
            dates = [self.tournament_date]
        if not dates:
            return ''
        if len(dates) == 1:
            return dates[0].strftime(fmt)
        consecutive = all((dates[i] - dates[i - 1]).days == 1 for i in range(1, len(dates)))
        if consecutive:
            first, last = dates[0], dates[-1]
            if first.month == last.month and first.year == last.year:
                return '{} – {}'.format(first.strftime('%d'), last.strftime(fmt))
            return '{} – {}'.format(first.strftime(fmt), last.strftime(fmt))
        return joiner.join(d.strftime(fmt) for d in dates)

    def _sync_tournament_date_from_lines(self):
        """Keep tournament_date + tournament_dates in sync with date lines."""
        if self.env.context.get('skip_tournament_date_sync'):
            return
        for rec in self:
            dates = sorted(d for d in rec.tournament_date_ids.mapped('date') if d)
            earliest = dates[0] if dates else False
            dates_char = rec._tournament_dates_to_char(dates) or False
            vals = {}
            if rec.tournament_date != earliest:
                vals['tournament_date'] = earliest
            if (rec.tournament_dates or False) != dates_char:
                vals['tournament_dates'] = dates_char
            if vals:
                super(AuctionTournament, rec).with_context(
                    skip_tournament_date_sync=True
                ).write(vals)

    def _sync_date_lines_from_dates_char(self):
        """Rebuild date lines from the tournament_dates Char field."""
        DateLine = self.env['auction.tournament.date'].with_context(
            skip_tournament_date_sync=True
        )
        for rec in self:
            wanted = set(rec._parse_tournament_dates_char())
            existing = {line.date: line for line in rec.tournament_date_ids}
            to_unlink = [line.id for date_val, line in existing.items() if date_val not in wanted]
            if to_unlink:
                DateLine.browse(to_unlink).unlink()
            for date_val in wanted:
                if date_val not in existing:
                    DateLine.create({
                        'tournament_id': rec.id,
                        'date': date_val,
                    })
            # Sync earliest date without re-entering char→lines sync
            earliest = min(wanted) if wanted else False
            dates_char = rec._tournament_dates_to_char(wanted) or False
            vals = {}
            if rec.tournament_date != earliest:
                vals['tournament_date'] = earliest
            if (rec.tournament_dates or False) != dates_char:
                vals['tournament_dates'] = dates_char
            if vals:
                super(AuctionTournament, rec).with_context(
                    skip_tournament_date_sync=True
                ).write(vals)

    def _ensure_tournament_date_line(self, date_val):
        """Create/update a single date line when only tournament_date is written."""
        self.ensure_one()
        if not date_val:
            if self.tournament_dates:
                self.with_context(skip_tournament_date_sync=True).write({
                    'tournament_dates': False,
                })
                self._sync_date_lines_from_dates_char()
            return
        iso = fields.Date.to_string(date_val)
        current = self._parse_tournament_dates_char()
        if len(current) <= 1:
            self.with_context(skip_tournament_date_sync=True).write({
                'tournament_dates': iso,
            })
            self._sync_date_lines_from_dates_char()
        elif date_val not in current:
            current.append(date_val)
            self.with_context(skip_tournament_date_sync=True).write({
                'tournament_dates': self._tournament_dates_to_char(current),
            })
            self._sync_date_lines_from_dates_char()

    def init(self):
        """Schema self-heal + legacy tournament date migration.

        ``show_registration_capacity`` is created here so production can pick it
        up on registry/restart without requiring ``-u`` module upgrade.
        """
        cr = self.env.cr
        self._ensure_show_registration_capacity_column()

        # Migrate legacy single tournament_date values into date lines + char.
        cr.execute("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_name = 'auction_tournament_date'
            )
        """)
        if not cr.fetchone()[0]:
            return
        cr.execute("""
            INSERT INTO auction_tournament_date
                (tournament_id, date, create_uid, write_uid, create_date, write_date)
            SELECT t.id, t.tournament_date, 1, 1,
                   (now() AT TIME ZONE 'UTC'), (now() AT TIME ZONE 'UTC')
              FROM auction_tournament t
             WHERE t.tournament_date IS NOT NULL
               AND NOT EXISTS (
                    SELECT 1 FROM auction_tournament_date d
                     WHERE d.tournament_id = t.id
               )
        """)
        cr.execute("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'auction_tournament'
                  AND column_name = 'tournament_dates'
            )
        """)
        if not cr.fetchone()[0]:
            return
        cr.execute("""
            UPDATE auction_tournament t
               SET tournament_dates = sub.dates
              FROM (
                    SELECT tournament_id,
                           string_agg(to_char(date, 'YYYY-MM-DD'), ',' ORDER BY date) AS dates
                      FROM auction_tournament_date
                     GROUP BY tournament_id
                   ) sub
             WHERE t.id = sub.tournament_id
               AND (t.tournament_dates IS NULL OR t.tournament_dates = '')
        """)

    def _ensure_show_registration_capacity_column(self):
        """Create missing column without module upgrade (hot-deploy / restart)."""
        cr = self.env.cr
        cr.execute("""
            SELECT 1
              FROM information_schema.columns
             WHERE table_name = 'auction_tournament'
               AND column_name = 'show_registration_capacity'
        """)
        if cr.fetchone():
            return
        cr.execute("""
            ALTER TABLE auction_tournament
                ADD COLUMN show_registration_capacity boolean
                DEFAULT TRUE
        """)
        cr.execute("""
            UPDATE auction_tournament
               SET show_registration_capacity = TRUE
             WHERE show_registration_capacity IS NULL
        """)

    def _register_hook(self):
        super()._register_hook()
        # Self-heal on every registry load (restart without -u).
        self._ensure_show_registration_capacity_column()

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

    def _assert_tournament_type_available(self, tournament_type):
        """Kabaddi is listed but not yet supported — force Cricket/Football."""
        if tournament_type == 'kabaddi':
            raise UserError(
                'Kabaddi is coming soon!\n\n'
                'Please go back and select Cricket or Football. '
                'Kabaddi tournaments will be available in a future update.'
            )

    @api.onchange('tournament_type')
    def _onchange_tournament_type_coming_soon(self):
        if self.tournament_type == 'kabaddi':
            return {
                'warning': {
                    'title': 'Kabaddi — Coming Soon',
                    'message': (
                        'Kabaddi support is coming soon.\n\n'
                        'Please switch back to Cricket or Football to continue '
                        'creating or editing this tournament.'
                    ),
                }
            }

    # Effective date shown on the public privacy policy page — bump when policy text changes.
    CONTACT_UNMASK_PRIVACY_POLICY_VERSION = '21 July 2026'

    def _assert_expose_player_contact_privacy(self, vals, creating=False):
        """Block enabling contact unmask unless privacy agreement was just recorded."""
        if not vals.get('expose_player_contact'):
            return
        if self.env.context.get('expose_contact_privacy_ack'):
            return
        if creating:
            raise UserError(_(
                "Unmasking player contact numbers requires accepting the privacy policy. "
                "Leave this disabled when creating the tournament, then enable it from "
                "Tournament Master using “Agree & Unmask Contacts”."
            ))
        enabling_recs = self.filtered(lambda t: not t.expose_player_contact)
        if enabling_recs:
            raise UserError(_(
                "Unmasking player contact numbers requires accepting the privacy policy. "
                "Use the “Agree & Unmask Contacts” button to review and accept before enabling."
            ))

    def action_open_expose_contact_privacy_wizard(self):
        """Open the privacy-agreement wizard required to unmask player contacts."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Privacy Policy — Unmask Player Contact'),
            'res_model': 'auction.expose.contact.privacy.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_tournament_id': self.id,
            },
        }

    def action_remask_player_contact(self):
        """Turn contact unmasking off (keeps the privacy agreement audit stamp)."""
        self.write({'expose_player_contact': False})
        return True

    @api.model
    def create(self, vals):
        self._assert_tournament_type_available(vals.get('tournament_type'))
        self._assert_expose_player_contact_privacy(vals, creating=True)
        if not vals.get('tournament_code'):
            vals['tournament_code'] = _generate_tournament_code(self.env)
        if not vals.get('point_unit_id'):
            unit = self.env['auction.point.unit'].default_unit()
            if unit:
                vals['point_unit_id'] = unit.id
        # Prefer char multi-dates; fall back to single tournament_date
        if vals.get('tournament_dates') and not vals.get('tournament_date'):
            try:
                parsed = []
                for part in str(vals['tournament_dates']).split(','):
                    part = part.strip()
                    if part:
                        parsed.append(fields.Date.to_date(part))
                if parsed:
                    vals['tournament_date'] = min(parsed)
            except Exception:
                pass
        date_val = vals.get('tournament_date')
        dates_char = vals.get('tournament_dates')
        record = super().create(vals)
        if dates_char:
            record._sync_date_lines_from_dates_char()
        elif date_val and not record.tournament_date_ids:
            record._ensure_tournament_date_line(date_val)
        elif record.tournament_date_ids:
            record._sync_tournament_date_from_lines()
        record._ensure_default_tier()
        return record

    def copy(self, default=None):
        default = dict(default or {})
        default.setdefault('expose_player_contact', False)
        default.setdefault('expose_player_contact_privacy_agreed', False)
        default.setdefault('expose_player_contact_agreed_user_id', False)
        default.setdefault('expose_player_contact_agreed_date', False)
        default.setdefault('expose_player_contact_policy_version', False)
        new = super().copy(default)
        new._ensure_default_tier()
        return new

    def _ensure_default_tier(self):
        """Create a linked DEFAULT tier when the tournament has none yet."""
        Tier = self.env['auction.player.tier'].sudo()
        for tournament in self:
            exists = Tier.search([
                ('tournament_id', '=', tournament.id),
                ('name', '=ilike', 'DEFAULT'),
            ], limit=1)
            if exists:
                continue
            Tier.create({
                'name': 'DEFAULT',
                'description': 'Default player tier',
                'color': '#3498db',
                'tournament_id': tournament.id,
            })

    @api.model
    def _ensure_default_point_units(self):
        """Assign the master PTS unit to every tournament that has none."""
        unit = self.env['auction.point.unit'].default_unit()
        if not unit:
            return True
        missing = self.sudo().search([('point_unit_id', '=', False)])
        if missing:
            # Bypass non-admin write restrictions during module data load.
            missing.sudo().write({'point_unit_id': unit.id})
        return True

    def get_point_unit(self):
        """Return the tournament's point unit, falling back to PTS."""
        self.ensure_one()
        return self.point_unit_id or self.env['auction.point.unit'].default_unit()

    def format_points(self, amount, use_locale=True, for_pdf=False):
        """Format a numeric player/purse value with the tournament unit."""
        self.ensure_one()
        unit = self.get_point_unit()
        if not unit:
            try:
                num = int(amount or 0)
            except (TypeError, ValueError):
                num = 0
            num_str = '{:,}'.format(num) if use_locale else str(num)
            return '%s PTS' % num_str
        return unit.format_value(amount, use_locale=use_locale, for_pdf=for_pdf)

    def format_points_pdf(self, amount, use_locale=True):
        """PDF formatter: Unicode symbols as HTML entities + DejaVu font."""
        return self.format_points(amount, use_locale=use_locale, for_pdf=True)

    def get_point_unit_js(self):
        """JS-ready dict for live boards and consoles."""
        self.ensure_one()
        unit = self.get_point_unit()
        if not unit:
            return {
                'id': False,
                'name': 'Points',
                'symbol': 'PTS',
                'position': 'after',
                'with_space': True,
            }
        return unit.to_js_dict()

    def get_point_unit_js_json(self):
        """JSON string safe to embed in a &lt;script&gt; tag."""
        self.ensure_one()
        return json.dumps(self.get_point_unit_js())

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        if 'point_unit_id' in fields_list and not res.get('point_unit_id'):
            unit = self.env['auction.point.unit'].default_unit()
            if unit:
                res['point_unit_id'] = unit.id
        return res

    def write(self, vals):
        """Restrict non-admin users to only modifying operational/balance fields.

        sudo() calls (env.su=True) bypass this check entirely — internal model
        methods that use sudo() must never be blocked here.
        """
        if 'tournament_type' in vals:
            self._assert_tournament_type_available(vals.get('tournament_type'))
        self._assert_expose_player_contact_privacy(vals, creating=False)
        if (not self.env.su
                and not self.env.user.has_group('auction_module.group_auction_group_admin')):
            _ALLOWED = {
                # team balance & payment config
                'team_max_points', 'payment_qr_image', 'payment_instruction',
                'payment_proof_required',
                # live-board stamp — written during SOLD / UNSOLD / NEXT-PLAYER
                'stamp_player_id', 'stamp_state', 'stamp_expires_at',
                # live-board controls
                'live_board_active', 'break_time_active', 'live_board_code_protected',
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
        if self.env.context.get('skip_tournament_date_sync'):
            return res
        if 'tournament_dates' in vals and 'tournament_date_ids' not in vals:
            self._sync_date_lines_from_dates_char()
        elif 'tournament_date' in vals and 'tournament_date_ids' not in vals and 'tournament_dates' not in vals:
            for rec in self:
                rec._ensure_tournament_date_line(vals.get('tournament_date'))
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
            'view_mode': 'kanban,tree,form',
            'views': [
                (self.env.ref('auction_module.view_auction_auction_kanban').id, 'kanban'),
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

    def action_toggle_live_board_code_protected(self):
        """Toggle whether the public live board requires the Tournament Code."""
        for rec in self:
            # Write via sudo so SaaS / non-admin organisers persist the change
            # even when the form save path is restricted.
            rec.sudo().write({
                'live_board_code_protected': not bool(rec.live_board_code_protected),
            })
        return True

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

    def action_open_admin_registration_link(self):
        """Open the organiser admin registration form (tournament-code unlock)."""
        self.ensure_one()
        if not self.slug:
            raise UserError(_('Tournament slug is required before opening admin registration.'))
        url = '/{}/{}/player/register/admin'.format(self.env.cr.dbname, self.slug)
        return {
            'type': 'ir.actions.act_url',
            'url': url,
            'target': 'new',
        }

    def action_open_projector_link(self):
        """Open the public projector screen in a new browser tab."""
        self.ensure_one()
        url = self.projector_url
        if not url:
            raise UserError(_(
                'Projector URL is not available. Set auction rules and ensure '
                'the tournament has a slug first.'
            ))
        return {
            'type': 'ir.actions.act_url',
            'url': url,
            'target': 'new',
        }

    def action_open_live_board(self):
        """Open the public Live Board URL in a new tab (share link for outsiders)."""
        self.ensure_one()
        url = self.live_board_url
        if not url:
            if self.slug:
                url = '/%s/%s/auction/live-board' % (self.env.cr.dbname, self.slug)
            else:
                raise UserError(_(
                    'Live Board URL is not available until the tournament has a name/slug.'
                ))
        return {
            'type': 'ir.actions.act_url',
            'url': url,
            'target': 'new',
        }

    def action_open_payment_tracker(self):
        """Open Payment Tracker as a backend client action (no URL redirect)."""
        self.ensure_one()
        return {
            'type': 'ir.actions.client',
            'tag': 'auction_module.payment_marker',
            'name': 'Payment Tracker',
            'target': 'current',
            'context': {'tournament_id': self.id},
            'params': {'tournament_id': self.id},
        }

    def action_open_bid_summary(self):
        """Open the public Bid Summary (team balance) page in a new tab."""
        self.ensure_one()
        url = self.bid_summary_url
        if not url:
            if self.slug:
                url = '/%s/%s/auction/show/team/balance' % (self.env.cr.dbname, self.slug)
            else:
                raise UserError(_(
                    'Bid Summary URL is not available until the tournament has a name/slug.'
                ))
        return {
            'type': 'ir.actions.act_url',
            'url': url,
            'target': 'new',
        }

    def action_open_pool_generator(self):
        """Open Pool & Fixture Generator scoped to this tournament."""
        self.ensure_one()
        return {
            'type': 'ir.actions.client',
            'tag': 'auction_module.pool_generator',
            'name': 'Pool & Fixture Generator — %s' % (self.name or 'Tournament'),
            'target': 'current',
            'context': {
                'tournament_id': self.id,
                'active_id': self.id,
                'active_model': 'auction.tournament',
            },
            'params': {'tournament_id': self.id},
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

        date_label = self.format_tournament_dates(fmt='%d %B %Y')
        if date_label:
            lines.append('📅 *Date:* {}'.format(date_label))

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

    def action_upload_teams(self):
        """Open the Excel + logo ZIP team uploader for this tournament."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Upload Teams & Tiers',
            'res_model': 'auction.team.upload.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_tournament_id': self.id},
        }

    def action_export_sold_unsold(self):
        """Open Excel export wizard for Registered / Sold / Unsold / Jersey."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Export Players',
            'res_model': 'auction.player.stage.export.wizard',
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
