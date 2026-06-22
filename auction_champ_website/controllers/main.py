# -*- coding: utf-8 -*-
import logging
from datetime import date

from odoo import http
from odoo.http import request
from odoo.addons.website.controllers.main import Website

_logger = logging.getLogger(__name__)


class AuctionChampHomepage(Website):
    """Override the website root to serve the AuctionChamp marketing page."""

    @http.route('/', type='http', auth='public', website=True, sitemap=True)
    def index(self, **kw):
        try:
            config = request.env['auction.website.config'].sudo().get_singleton()
            faq_items = request.env['auction.website.faq'].sudo().search(
                [('active', '=', True)], order='sequence asc'
            )
            pricing_plans = request.env['auction.website.pricing'].sudo().search(
                [('active', '=', True)], order='sequence asc'
            )
            return request.render('auction_champ_website.homepage', {
                'config': config,
                'faq_items': faq_items,
                'pricing_plans': pricing_plans,
                'current_year': date.today().year,
            })
        except Exception:
            _logger.exception("AuctionChamp homepage render error — falling back to default")
            return super().index(**kw)
