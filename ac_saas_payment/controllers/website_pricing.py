# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request

from odoo.addons.auction_champ_website.controllers.main import AuctionChampHomepage
from odoo.addons.ac_saas_payment.models.visitor_country import (
    AUTO_TOKEN,
    apply_country_cookie,
)


class AuctionChampHomepageSignup(AuctionChampHomepage):
    """Show the regional package price and open signup when it can be bought."""

    def _get_public_pricing_plans(self):
        cards = super()._get_public_pricing_plans()
        Signup = request.env['ac.saas.signup.payment'].sudo()
        price_ctx = Signup.website_price_context(AUTO_TOKEN)
        country = price_ctx['country']
        signup_on = Signup.website_signup_active()
        Plan = request.env['ac.saas.plan'].sudo()
        for card in cards:
            plan_id = card.get('plan_id')
            if not plan_id:
                continue
            plan = Plan.browse(plan_id)
            info = plan.get_website_price_display(country)
            card['price_amount'] = info.get('amount') or ''
            card['price_per_tournament'] = info.get('per_tournament') or ''
            card['price_validity'] = info.get('validity') or ''
            if signup_on and Signup.plan_is_purchasable(plan, country or None):
                card['contact_url'] = '/saas/signup/%s' % plan.id
                card['cta_label'] = 'Get Started'
                card['cta_buy'] = True
            else:
                card['cta_buy'] = False
        return cards

    @http.route(
        '/saas/pricing/country',
        type='http', auth='public', website=True, sitemap=False, methods=['GET'],
    )
    def saas_pricing_country(self, code=None, **kw):
        """Remember the country used for public plan prices."""
        token = (code or '').strip()
        if token and token not in (AUTO_TOKEN, '__default__'):
            country = request.env['res.country'].sudo().search([
                ('code', '=', token.upper()),
            ], limit=1)
            token = country.code if country else ''
        response = request.redirect('/#pricing', 303)
        return apply_country_cookie(response, token or '__default__')
