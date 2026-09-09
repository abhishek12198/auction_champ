# -*- coding: utf-8 -*-
from odoo.http import request

from odoo.addons.auction_champ_website.controllers.main import AuctionChampHomepage


class AuctionChampHomepageSignup(AuctionChampHomepage):
    """Replace Contact Us with Get Started when online signup is available."""

    def _get_public_pricing_plans(self):
        cards = super()._get_public_pricing_plans()
        Signup = request.env['ac.saas.signup.payment'].sudo()
        if not Signup.website_signup_active():
            return cards

        Plan = request.env['ac.saas.plan'].sudo()
        for card in cards:
            plan_id = card.get('plan_id')
            if not plan_id:
                continue
            plan = Plan.browse(plan_id)
            if Signup.plan_is_purchasable(plan):
                card['contact_url'] = '/saas/signup/%s' % plan.id
                card['cta_label'] = 'Get Started'
                card['cta_buy'] = True
        return cards
