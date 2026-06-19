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

    @api.model
    def default_get(self, fields):
        defaults = super(AuctionTournament, self).default_get(fields)
        existing_tournament = self.search([])
        if existing_tournament:
            raise ValidationError("Current Tournament is active. Please deactivate and create a new one.")

        return defaults

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
        compute='_compute_registration_url',
        store=False,
        help='Share this public link with players so they can self-register for the tournament.',
    )

    def _compute_registered_player_count(self):
        Player = self.env['auction.team.player']
        for rec in self:
            rec.registered_player_count = Player.search_count([
                ('tournament_id', '=', rec.id),
                ('state', '=', 'draft'),
            ])

    @api.depends('name')
    def _compute_slug(self):
        for rec in self:
            rec.slug = _slugify(rec.name or '')

    def _compute_registration_url(self):
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url', '')
        db_name = self.env.cr.dbname
        for rec in self:
            if rec.slug:
                rec.registration_url = '{}/{}/{}/player/register'.format(base_url, db_name, rec.slug)
            else:
                rec.registration_url = '{}/{}/player/register'.format(base_url, db_name)

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