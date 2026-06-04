from odoo import models, fields


class ResUsers(models.Model):
    _inherit = 'res.users'

    auction_team_id = fields.Many2one(
        'auction.team',
        string='My Auction Team',
        help='Assign this user to a team so they can use the Owner Console.',
    )
