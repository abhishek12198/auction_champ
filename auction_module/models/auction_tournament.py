# -*- coding: utf-8 -*-
import re
import unicodedata
import base64

from odoo import api, models, fields, _
from odoo.exceptions import UserError
from odoo.tools.image import image_data_uri
from odoo.exceptions import UserError, ValidationError

import werkzeug
import werkzeug.exceptions


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
    logo = fields.Binary('Logo')
    active = fields.Boolean(default=True)
    player_appearance_algorithm = fields.Selection([('linear', 'Manual'), ('random', 'Random')], default="linear")
    team_max_points = fields.Integer(string="Max points alloted for a team")
    organizer_uid = fields.Many2one('res.users', 'Organizer')
    points_split_ids = fields.One2many('auction.tournament.point.split', 'tournament_id', 'Points Split')

    organizer_uids = fields.Many2many('res.users', 'auction_tournament_user_rel', 'tournament_id', 'user_id',
                                      'Organizers')

    team_ids = fields.One2many('auction.team', 'tournament_id', 'Teams')
    template_image = fields.Binary('Template Image')
    report_footer = fields.Binary('Footer')
    rules_regulations = fields.Html("Rules and Regulations")
    tournament_type = fields.Selection([('cricket', 'Cricket'), ('football', 'Football')], default='cricket')
    player_display_template = fields.Selection([
        ('vanilla', 'Vanilla'),
        ('butterscotch', 'Butterscotch'),
        ('strawberry', 'Strawberry'),
        ('cherry', 'Cherry'),
        ('pistah', 'Pistah'),
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
    enable_jersey_section = fields.Boolean(
        "Enable Jersey Section in Registration",
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
    registration_open = fields.Boolean(
        "Registration Open",
        default=False,
        help="When enabled, the public player self-registration form is accessible. "
             "Disable this to close registrations at any point.",
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
        compute='_compute_registered_player_count',
        store=False,
        help='Current number of players in Draft state for this tournament.',
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
        help='Share this URL with the projector/screen operator to display players during a Manual auction.',
    )
    dice_state = fields.Selection(
        [('idle', 'Idle'), ('rolling', 'Rolling'), ('result', 'Result')],
        string='Dice State', default='idle',
        help='Live state of the dice roll broadcast to the projector.',
    )
    dice_result = fields.Integer(string='Dice Result', default=0)

    def _compute_registered_player_count(self):
        # Single aggregated query instead of one search_count() per record.
        groups = self.env['auction.team.player'].read_group(
            [('tournament_id', 'in', self.ids), ('state', '=', 'draft')],
            ['tournament_id'],
            ['tournament_id'],
        )
        count_map = {g['tournament_id'][0]: g['tournament_id_count'] for g in groups}
        for rec in self:
            rec.registered_player_count = count_map.get(rec.id, 0)

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

            if rec.slug and rec.player_appearance_algorithm == 'linear':
                rec.projector_url = '{}/{}/auction/projector/{}/'.format(base_url, db_name, rec.slug)
            else:
                rec.projector_url = False

    def set_dice_state(self, state, number=0):
        """Called from player_selector JS to broadcast dice state to the projector."""
        valid = {'idle', 'rolling', 'result'}
        if state not in valid:
            state = 'idle'
        self.sudo().write({'dice_state': state, 'dice_result': int(number or 0)})
        return True

    def action_toggle_registration(self):
        """Toggle the registration open/closed state."""
        for rec in self:
            rec.registration_open = not rec.registration_open

    def action_toggle_live_board(self):
        """Toggle the live board active/stopped state."""
        for rec in self:
            rec.live_board_active = not rec.live_board_active

    def action_toggle_break_time(self):
        """Toggle the break time screen on the live board."""
        for rec in self:
            rec.break_time_active = not rec.break_time_active

    def action_clear_stage(self):
        """Clear the is_on_stage flag from all players in this tournament."""
        for rec in self:
            self.env['auction.team.player'].sudo().search([
                ('tournament_id', '=', rec.id),
                ('is_on_stage', '=', True),
            ]).write({'is_on_stage': False})

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
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url', '')
        db_name = self.env.cr.dbname
        url = '{}/{}/{}/player/register'.format(base_url, db_name, self.slug) if self.slug else '{}/{}/player/register'.format(base_url, db_name)
        return {
            'type': 'ir.actions.act_url',
            'url': url,
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