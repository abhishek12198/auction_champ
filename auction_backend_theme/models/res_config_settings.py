from odoo import api, fields, models

PARAM_KEY = 'auction.backend.title'
DEFAULT_TITLE = 'AuctionChamp'


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    auction_backend_title = fields.Char(
        string='Backend App Title',
        help='Name shown in the browser tab instead of "Odoo" (e.g. AuctionChamp).',
        config_parameter=PARAM_KEY,
    )

    @api.model
    def get_values(self):
        res = super().get_values()
        res['auction_backend_title'] = (
            self.env['ir.config_parameter'].sudo().get_param(PARAM_KEY, DEFAULT_TITLE)
        )
        return res
