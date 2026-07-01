from odoo import models
from odoo.http import request

PARAM_KEY = 'auction.backend.title'
DEFAULT_TITLE = 'AuctionChamp'


class IrHttp(models.AbstractModel):
    _inherit = 'ir.http'

    def session_info(self):
        result = super().session_info()
        result['app_title'] = (
            request.env['ir.config_parameter'].sudo().get_param(PARAM_KEY, DEFAULT_TITLE)
        )
        return result
