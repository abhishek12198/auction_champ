# -*- coding: utf-8 -*-
import base64

from odoo import api, models, fields, _
from odoo.exceptions import UserError
from odoo.tools.image import image_data_uri
from odoo.exceptions import UserError, ValidationError

import werkzeug
import werkzeug.exceptions


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
    registration_url = fields.Char(
        string='Player Registration URL',
        compute='_compute_registration_url',
        store=False,
        help='Share this public link with players so they can self-register for the tournament.',
    )

    def _compute_registration_url(self):
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url', '')
        for rec in self:
            rec.registration_url = '{}/player/register'.format(base_url)

    def action_toggle_registration(self):
        """Toggle the registration open/closed state."""
        for rec in self:
            rec.registration_open = not rec.registration_open

    def action_open_registration_link(self):
        """Open the public player registration form in a new browser tab."""
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url', '')
        return {
            'type': 'ir.actions.act_url',
            'url': '{}/player/register'.format(base_url),
            'target': 'new',
        }