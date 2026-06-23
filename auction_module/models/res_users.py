# -*- coding: utf-8 -*-
import base64

from odoo import api, models, fields, _
from odoo.exceptions import UserError
from odoo.tools.image import image_data_uri

import werkzeug
import werkzeug.exceptions

class AuctionTeam(models.Model):
    _inherit = 'res.users'

    tournament_ids = fields.Many2many(
        'auction.tournament',
        'auction_tournament_user_rel',
        'user_id', 'tournament_id',
        'Tournaments',
    )
    # The single tournament this user operates in.
    # Non-admin users get this auto-injected into every record they create.
    tournament_id = fields.Many2one(
        'auction.tournament',
        string='Active Tournament',
        help='The tournament this user belongs to. '
             'Used to automatically scope records and QWeb templates. '
             'Visible and assignable only by Administrators.',
    )
    # For Team Owner users — their assigned team within the tournament.
    team_id = fields.Many2one(
        'auction.team',
        string='Team',
        help='The team this user manages (Owner role only).',
    )
    