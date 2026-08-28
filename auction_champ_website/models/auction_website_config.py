# -*- coding: utf-8 -*-
##############################################################################
#
#  AuctionChamp - Professional Sports Auction Management Platform
#
#  Copyright (c) 2026 AuctionChamp.
#  All Rights Reserved.
#
#  CONFIDENTIAL & PROPRIETARY
#
#  This source code, including but not limited to its algorithms, business
#  logic, database structures, models, controllers, views, reports, templates,
#  APIs, documentation, and related materials, constitutes proprietary and
#  confidential information owned exclusively by AuctionChamp.
#
#  This software is protected by applicable copyright laws and international
#  intellectual property treaties. Unauthorized copying, reproduction,
#  modification, distribution, publication, sublicensing, reverse engineering,
#  decompilation, disassembly, disclosure, or use of this software, in whole
#  or in part, is strictly prohibited without the prior written permission of
#  AuctionChamp.
#
#  This software is licensed, not sold. Possession of the source code does not
#  grant any right to copy, modify, redistribute, or create derivative works
#  except as expressly permitted under a valid written license agreement with
#  AuctionChamp.
#
#  Any unauthorized use may result in civil and criminal penalties under
#  applicable intellectual property and copyright laws.
#
#  Company  : AuctionChamp
#  Website  : www.auctionchamp.live
#  Email    : auctionchamp.live@gmail.com
#
#  © 2026 AuctionChamp. All Rights Reserved.
#
##############################################################################

from odoo import api, models, fields


class AuctionWebsiteConfig(models.Model):
    _name = 'auction.website.config'
    _description = 'AuctionChamp Website Configuration'
    _rec_name = 'hero_headline'

    # ── Hero ──────────────────────────────────────────────────────────────
    hero_headline = fields.Char(
        string='Hero Headline',
        default="India's Complete Cricket Auction & Tournament Management Platform",
    )
    hero_subheading = fields.Text(
        string='Hero Sub-heading',
        default=(
            "Manage Player Registrations, Cricket Auctions, Teams, Fixtures, "
            "Points Tables, Live Updates and Tournament Operations from one "
            "powerful platform."
        ),
    )
    demo_url = fields.Char(
        string='Request Demo URL',
        default='#contact',
        help='URL for the "Request Demo" button in the hero section.',
    )
    watch_auction_url = fields.Char(
        string='Watch Live Auction URL',
        default='/auction/showcase',
        help='URL for the "Watch Live Auction" button.',
    )

    # ── Statistics (labels only — values are computed live from the DB) ──
    stat_1_label = fields.Char(string='Stat 1 — Label', default='Tournaments Managed')
    stat_2_label = fields.Char(string='Stat 2 — Label', default='Players Registered')
    stat_3_label = fields.Char(string='Stat 3 — Label', default='Teams Managed')
    stat_4_label = fields.Char(string='Stat 4 — Label', default='Auction Automation')

    # ── Testimonials ──────────────────────────────────────────────────────
    testimonial_1_text = fields.Text(
        string='Testimonial 1 — Text',
        default='Managing our auction became effortless with AuctionChamp. The live bidding dashboard is incredibly smooth.',
    )
    testimonial_1_author = fields.Char(string='Testimonial 1 — Author', default='Rajesh Kumar')
    testimonial_1_role = fields.Char(string='Testimonial 1 — Role', default='Tournament Organizer')

    testimonial_2_text = fields.Text(
        string='Testimonial 2 — Text',
        default='Player registration and auction management saved us countless hours. Highly recommended for every league.',
    )
    testimonial_2_author = fields.Char(string='Testimonial 2 — Author', default='Suresh Patel')
    testimonial_2_role = fields.Char(string='Testimonial 2 — Role', default='League Manager')

    testimonial_3_text = fields.Text(
        string='Testimonial 3 — Text',
        default='Professional auction experience for players and team owners. The live display screen is outstanding.',
    )
    testimonial_3_author = fields.Char(string='Testimonial 3 — Author', default='Anil Sharma')
    testimonial_3_role = fields.Char(string='Testimonial 3 — Role', default='Team Owner')

    # ── Final CTA ─────────────────────────────────────────────────────────
    book_demo_url = fields.Char(
        string='Book Free Demo URL',
        default='#contact',
    )
    contact_sales_url = fields.Char(
        string='Contact Sales URL',
        default='mailto:sales@auctionchamp.in',
    )

    # ── Contact ───────────────────────────────────────────────────────────
    contact_email = fields.Char(string='Contact Email', default='support@auctionchamp.in')
    contact_phone = fields.Char(string='Contact Phone', default='+91 XXXXX XXXXX')

    # ── Social Media ──────────────────────────────────────────────────────
    social_facebook = fields.Char(string='Facebook URL')
    social_twitter = fields.Char(string='Twitter / X URL')
    social_instagram = fields.Char(string='Instagram URL')
    social_youtube = fields.Char(string='YouTube URL')

    # ── Footer ────────────────────────────────────────────────────────────
    footer_tagline = fields.Char(
        string='Footer Tagline',
        default='Powering the Future of Cricket Auctions & Tournament Management',
    )
    about_us_text = fields.Text(
        string='About Us Text',
        default=(
            "AuctionChamp is India's leading cricket auction and tournament "
            "management platform, trusted by hundreds of organizers across "
            "the country."
        ),
    )

    @api.model
    def get_singleton(self):
        """Return the single config record, creating it with defaults if absent."""
        record = self.search([], limit=1)
        if not record:
            record = self.create({})
        return record

    @staticmethod
    def _format_stat_count(count):
        """Format a DB count for the hero strip (e.g. 1234 → '1,234+')."""
        count = int(count or 0)
        if count <= 0:
            return '0'
        return '{:,}+'.format(count)

    @api.model
    def get_hero_stats(self):
        """Build hero statistics from live database counts.

        Includes archived (inactive) tournaments/teams/players so the strip
        reflects everything managed on the platform, not only current season.
        """
        config = self.get_singleton()
        env = self.env

        tournaments = env['auction.tournament'].sudo().with_context(
            active_test=False
        ).search_count([])
        players = env['auction.team.player'].sudo().with_context(
            active_test=False
        ).search_count([])
        teams = env['auction.team'].sudo().with_context(
            active_test=False
        ).search_count([])
        live_auctions = env['auction.tournament'].sudo().search_count([
            ('live_board_active', '=', True),
            ('active', '=', True),
        ])

        return {
            'stat_1_value': self._format_stat_count(tournaments),
            'stat_1_label': config.stat_1_label or 'Tournaments Managed',
            'stat_2_value': self._format_stat_count(players),
            'stat_2_label': config.stat_2_label or 'Players Registered',
            'stat_3_value': self._format_stat_count(teams),
            'stat_3_label': config.stat_3_label or 'Teams Managed',
            # Live auction count when boards are active; "Live" when idle.
            'stat_4_value': str(live_auctions) if live_auctions else 'Live',
            'stat_4_label': config.stat_4_label or 'Auction Automation',
        }
