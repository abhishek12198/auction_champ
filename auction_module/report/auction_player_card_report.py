# -*- coding: utf-8 -*-

import json

from odoo import api, models, _
from odoo.tools import float_round

class PlayerCardAuction(models.AbstractModel):
    _name = 'report.auction_module.player_card_template'
    _description = 'Player Card Template'

    @api.model
    def _get_report_values(self, docids, data=None):
        docs = []
        docs = self.env['auction.team.player'].browse(docids)

        return {
            'doc_ids': docids,
            'doc_model': 'auction.team.player',
            'docs': docs,
            'tournament': self.env['auction.tournament'].search([('active', '=', True)], limit=1)
        }

