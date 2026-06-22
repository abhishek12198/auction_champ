# -*- coding: utf-8 -*-
from odoo import models, fields


class AuctionWebsiteFAQ(models.Model):
    _name = 'auction.website.faq'
    _description = 'AuctionChamp Website FAQ'
    _order = 'sequence asc, id asc'

    question = fields.Char(string='Question', required=True)
    answer = fields.Text(string='Answer', required=True)
    sequence = fields.Integer(string='Sequence', default=10)
    active = fields.Boolean(default=True)
