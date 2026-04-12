# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import re
import werkzeug
import itertools
import pytz
import babel.dates
from collections import OrderedDict
import base64
import tempfile
import os
import subprocess
import json
from odoo import http, fields
from odoo.addons.http_routing.models.ir_http import slug, unslug
from odoo.addons.website.controllers.main import QueryURL
from odoo.addons.portal.controllers.portal import _build_url_w_params
from odoo.http import request
from odoo.osv import expression
from odoo.tools import html2plaintext
from odoo.tools.misc import get_lang
from odoo.tools import sql



class Auction(http.Controller):

    @http.route('/auction/player_selector', type='http', auth='public', website=True)
    def player_selector(self, **kw):
        tournament = request.env['auction.tournament'].sudo().search(
            [('active', '=', True)], limit=1)
        theme = (tournament.player_display_template or 'vanilla') if tournament else 'vanilla'
        return request.render(
            'auction_module.player_sequence_selector',
            {'tournament': tournament, 'theme': theme}
        )

    #sequence_template_part
    @http.route('/auction/get_players_queue', type='json', auth='public', website=True)
    def get_players_queue(self):
        tournament = request.env['auction.tournament'].sudo().search(
            [('active', '=', True)], limit=1
        )
        domain = [('icon_player', '=', False)]
        if tournament:
            domain.append(('tournament_id', '=', tournament.id))
        players = request.env['auction.team.player'].sudo().search(domain, order='sl_no asc')
        return [
            {'serial': p.sl_no, 'id': p.id, 'state': p.state}
            for p in players
        ]

    @http.route('/auction/get_player_data', type='json', auth='public', website=True)
    def get_player_data(self, player_id):
        """Fetch full player data for modal display"""
        player = request.env['auction.team.player'].sudo().browse(int(player_id))

        if not player.exists():
            return {}

        # Convert photo to base64 if exists
        photo_base64 = ""
        if player.photo:
            photo_base64 = player.photo.decode('utf-8') if isinstance(player.photo, bytes) else player.photo

        return {
            'id': player.id,
            'sl_no': player.sl_no,
            'name': player.name,
            'role': player.role or 'N/A',
            'batting_style': player.batting_style or 'N/A',
            'bowling_style': player.bowling_style or 'N/A',
            'contact': player.contact or 'N/A',
            'blood_group': player.blood_group or 'N/A',
            'address': player.address or 'N/A',
            'photo': photo_base64,
            'tournament_id': player.tournament_id.id if player.tournament_id else None,
            'tournament_name': player.tournament_id.name if player.tournament_id else '',
        }

    @http.route('/auction/player_card/<int:player_id>', type='http', auth='public', website=True)
    def get_player_card(self, player_id):
        """Render the full themed player card page for iframe embedding in the selector drawer."""
        player = request.env['auction.team.player'].sudo().browse(int(player_id))
        if not player.exists():
            return request.not_found()

        tournament = request.env['auction.tournament'].sudo().search(
            [('active', '=', True)], limit=1)
        theme = (tournament.player_display_template or 'vanilla') if tournament else 'vanilla'
        auction_ids = request.env['auction.auction'].sudo().search(
            [('tournament_id', '=', tournament.id)] if tournament else [])

        template_map = {
            'vanilla':      'auction_module.player_template_new',
            'butterscotch': 'auction_module.player_template_butterscotch',
            'strawberry':   'auction_module.player_template_strawberry',
            'cherry':       'auction_module.player_template_cherry',
            'pistah':       'auction_module.player_template_pistah',
        }
        template_ref = template_map.get(theme, 'auction_module.player_template_new')
        return request.render(template_ref, {
            'player':      player,
            'tournament':  tournament,
            'auction_ids': auction_ids,
        })

    @http.route('/auction/player_modal/<int:player_id>', type='http', auth='public', website=True)
    def get_player_modal(self, player_id):
        """Render themed player card for the sequence-selector drawer."""
        player = request.env['auction.team.player'].sudo().browse(int(player_id))
        if not player.exists():
            return request.make_response('{"error": "Player not found"}',
                                         headers=[('Content-Type', 'application/json')])

        tournament = request.env['auction.tournament'].sudo().search(
            [('active', '=', True)], limit=1)

        theme = (tournament.player_display_template or 'vanilla') if tournament else 'vanilla'

        _unsold_color = {
            'cherry':       '#DC143C',
            'butterscotch': '#F5C842',
            'strawberry':   '#C2185B',
            'pistah':       '#6BBF4E',
        }.get(theme, '#b71c1c')

        _unsold_text = '#090912' if theme == 'butterscotch' else '#fff'

        sold_points = 0
        if player.state == 'sold':
            auction_line = request.env['auction.auction.player'].sudo().search(
                [('player_id', '=', player.id)], limit=1)
            sold_points = auction_line.points if auction_line else 0

        html_content = request.env['ir.ui.view']._render_template(
            'auction_module.player_template_modal_content', {
                'player':               player,
                'tournament':           tournament,
                'theme':                theme,
                'unsold_color':         _unsold_color,
                'unsold_text_color':    _unsold_text,
                'sold_display_seconds': tournament.sold_display_seconds if tournament else 5,
                'sold_points':          sold_points,
            })

        return request.make_response(html_content,
                                     headers=[('Content-Type', 'text/html; charset=utf-8')])

    # @http.route('/auction/get_players_queue', type='http', auth='public', website=True)
    # def get_players_queue(self):
    #
    #     players = request.env['auction.team.player'].sudo().get_auction_players(
    #     )
    #
    #     result = [
    #         {'serial': p.serial_number}
    #         for p in players
    #     ]
    #
    #     return json.dumps(result)
    #history part
    @http.route('/live_updates', type='http', auth='public', website=True)
    def live_updates_page(self):
        tournament_id = request.env['auction.tournament'].sudo().search([('active', '=', True)], limit=1)
        return request.render('auction_module.live_updates_template', {'tournament': tournament_id})

    @http.route('/get_live_updates', type='json', auth='public')
    def get_live_updates(self):
        records = request.env['auction.history'].sudo().search([], order='create_date desc', limit=100)
        return [
            {
                'message': rec.message,
                'timestamp': rec.create_date.strftime('%d-%m-%Y %H:%M:%S'),
                'avatar_base64':rec.player_photo,
                'avatar_team':  rec.team_id and rec.team_id.logo or False,
                # 'author': rec.author
            }
            for rec in records
        ]

    @http.route(['''/auction/show/team/balance1'''], type='http', auth="public", website=True, sitemap=True)
    def auction_team_balance_test(self, **kwargs):
        auctions = request.env['auction.auction'].sudo().search([])
        tournament = auctions.mapped('tournament_id')
        # result = request.render("auction_module.auction_details_show", {'teams': auctions, 'tournament': tournament})
        data = json.dumps({'team_name': 'KCB Machismo', 'balance': 1000})
        headers = [('Content-Type', 'application/json'),
                   ('Cache-Control', 'no-store')]
        return request.make_response(data, headers)



    @http.route(['''/auction/show/team/balance'''], type='http', auth="public", website=True)
    def auction_team_balance(self, **kwargs):
        tournament = request.env['auction.tournament'].sudo().search([('active', '=', True)], limit=1)
        domain = [('tournament_id', '=', tournament.id)] if tournament else []
        auctions = request.env['auction.auction'].sudo().search(domain)
        theme = (tournament.player_display_template or 'vanilla') if tournament else 'vanilla'
        access_type = 'internal'
        if request.env.user.login == 'public':
            access_type = 'public'
        balance_template_map = {
            'pistah': 'auction_module.auction_details_show_pistah',
        }
        template_ref = balance_template_map.get(theme, 'auction_module.auction_details_show')
        result = request.render(template_ref, {
            'teams': auctions,
            'tournament': tournament,
            'type': access_type,
            'theme': theme,
        })
        return result

    @http.route(['''/auction/show/team/balance/json'''], type='http', auth="public", website=True)
    def auction_team_balance_json(self, **kwargs):
        tournament = request.env['auction.tournament'].sudo().search([('active', '=', True)], limit=1)
        domain = [('tournament_id', '=', tournament.id)] if tournament else []
        auctions = request.env['auction.auction'].sudo().search(domain)
        teams_data = []
        for auction in auctions:
            teams_data.append({
                'id': auction.id,
                'remaining_players_count': auction.remaining_players_count,
                'remaining_points': auction.remaining_points,
                'max_call': auction.max_call,
            })
        data = json.dumps({'teams': teams_data})
        headers = [('Content-Type', 'application/json'), ('Cache-Control', 'no-store')]
        return request.make_response(data, headers)

    @http.route(['''/auction/display_auction/'''], type='http', auth="public", website=True, sitemap=True)
    def display_auction(self,**kwargs):

        player = request.env['auction.team.player'].sudo().get_random_player()
        tournament_id = request.env['auction.tournament'].sudo().search([('active', '=', True)], limit=1)
        if player:
            auction_ids = request.env['auction.auction'].sudo().search(
                [('tournament_id', '=', tournament_id.id)] if tournament_id else []
            )
            template_map = {
                'vanilla':       'auction_module.player_template_new',
                'butterscotch':  'auction_module.player_template_butterscotch',
                'strawberry':    'auction_module.player_template_strawberry',
                'cherry':        'auction_module.player_template_cherry',
                'pistah':        'auction_module.player_template_pistah',
            }
            chosen = tournament_id.player_display_template if tournament_id else 'vanilla'
            template_ref = template_map.get(chosen, 'auction_module.player_template_new')
            r = request.render(template_ref, {'player': player, 'tournament': tournament_id, 'auction_ids': auction_ids})
        else:
            r = request.render("auction_module.welcome_message_template", {
                'tournament': tournament_id,
                'theme': tournament_id.player_display_template if tournament_id else 'vanilla',
            })
        return r

    @http.route('/auction/get/players/team/<int:team_id>', type='http', auth='public', website=True)
    def get_team_players(self, team_id):
        player_data_list = []
        team_players = request.env['auction.auction.player'].search([('auction_id.team_id', '=', team_id)])

        team = request.env['auction.team'].browse(team_id)
        tournament = request.env['auction.tournament'].sudo().search([('active', '=', True)], limit=1)
        theme = (tournament.player_display_template or 'vanilla') if tournament else 'vanilla'
        icon_players = request.env['auction.team.player'].get_icon_players(team_id)
        if icon_players:
            for icon in icon_players:
                player_data = {
                    'name': icon.name,
                    'photo': icon.photo,
                    'point': 'ICON',
                    'role': icon.role,
                    'batting_style': icon.batting_style,
                    'bowling_style': icon.bowling_style,
                    'contact': icon.contact,
                    'p_type': icon.p_type,
                    'p_category': icon.p_category,
                    'tier_color': icon.tier_id.color if icon.tier_id else '#01cfff',
                    'tier_name': icon.tier_id.name if icon.tier_id else 'Icon',
                    'is_icon': True,
                }
                player_data_list.append(player_data)
        if team_players:
            for player in team_players:
                player_data = {
                    'name': player.player_id.name,
                    'photo': player.player_id.photo,
                    'point': player.points,
                    'role': player.player_id.role,
                    'batting_style': player.player_id.batting_style,
                    'bowling_style': player.player_id.bowling_style,
                    'contact': player.player_id.contact,
                    'p_type': player.player_id.p_type,
                    'p_category': player.player_id.p_category,
                    'tier_color': player.player_id.tier_id.color if player.player_id.tier_id else '#01cfff',
                    'tier_name': player.player_id.tier_id.name if player.player_id.tier_id else '',
                    'is_icon': False,
                }
                player_data_list.append(player_data)
        players_template_map = {
            'pistah': 'auction_module.auction_team_players_template_pistah',
        }
        template_ref = players_template_map.get(theme, 'auction_module.auction_team_players_template')
        return request.render(template_ref, {
            'players': player_data_list,
            'team': team,
            'tournament': tournament,
            'theme': theme,
        })

    @http.route('/get_players/<int:team_id>', type='json', auth="user", methods=['POST'], csrf=False)
    def get_players(self, team_id):
        team = request.env['auction.team'].browse(team_id)
        try:

            players = request.env['auction.auction.player'].search([('auction_id.team_id', '=', team_id)])


            player_data = []
            icon_players = team.key_player_ids
            if icon_players:
                for icon_player in icon_players:
                        player_data.append({
                            'name': icon_player.name,
                            'points': 'ICON PLAYER',
                            'role': icon_player.role,
                            'contact': icon_player.contact,
                            'c': icon_player.photo
                        })
            if players:
                for player in players:
                    player_data.append({
                        'name': player.player_id.name,
                        'points': player.points,
                        'role': player.player_id.role,
                        'contact': player.contact,
                        'photo': player.player_id.photo
                    })
            else:
                return {'status': 'error', 'message': 'No players found', 'team': team.name}
            return {'status': 'success', 'players': player_data, 'team': team.name, 'team_obj': team}

        except Exception as e:
            # Log the exception
            return {'status': 'error', 'message': str(e), 'team': team.name}

    # @http.route('/get_players/<int:team_id>', type='http', auth="user", csrf=False)
    # def get_players(self, team_id):
    #     players = request.env['auction.auction.player'].search([('auction_id.team_id', '=', team_id)])
    #     team = request.env['auction.team'].browse(team_id)
    #
    #     player_data = []
    #     print(players, "===============>")
    #     for player in players:
    #         player_data.append({
    #             'name': player.player_id.name,
    #             'points': player.points,
    #             'role': player.player_id.role,
    #             'contact': player.contact
    #         })
    #
    #     return {'status': 'success', 'players': player_data, 'team': team.name}

    @http.route('/player_card/download', type='http', auth="public", website=True)
    def download_player_card(self,  **kwargs):

        tournament = request.env['auction.tournament'].search([('active', '=', True)], limit=1)

        players = request.env['auction.team.player'].sudo().search([('state', 'in', ['draft', 'auction'])], limit=3)
        html_content = ''
        if players:
            for player in players:
                html_content += request.env['ir.ui.view']._render_template('auction_module.player_card_template', {
                    'player': player,
                    'tournament': tournament
                })
                # Add a page break after each player card
        # Convert HTML to PDF
        # paper_format = request.env.ref('auction_module.paperformat_euro_landscaoe')
        report_obj = request.env.ref('auction_module.action_player_card_print_template')
        pdf = report_obj._run_wkhtmltopdf(
            [html_content], header=None, footer=None
        )

        pdfhttpheaders = [
            ('Content-Type', 'application/pdf'),
            ('Content-Length', len(pdf)),
            ('Content-Disposition', 'attachment; filename="Player Cards.pdf"')
        ]
        return request.make_response(pdf, headers=pdfhttpheaders)

    @http.route('/player_card/download_images', type='http', auth="public", website=True)
    def download_player_cards_as_images(self, **kwargs):
        tournament = request.env['auction.tournament'].search([('active', '=', True)] ,limit=1)


        # Fetch all players related to the tournament
        players = request.env['auction.team.player'].sudo().get_auction_players()

        image_paths = []
        with tempfile.TemporaryDirectory() as tmpdirname:
            for player in players:
                # Render the HTML for the player
                html_content = request.env['ir.ui.view']._render_template('auction_module.player_card_template', {
                    'player': player,
                    'tournament': tournament
                })
                # Save the HTML to a temporary file
                html_file = os.path.join(tmpdirname, f"player_{player.id}.html")
                with open(html_file, 'w') as f:
                    f.write(html_content)

                # Convert the HTML to an image using wkhtmltoimage
                image_file = os.path.join(tmpdirname, f"player_{player.id}.jpg")
                command = [
                    'wkhtmltoimage',
                    '--quality', '100',
                    '--width', '50',  # Set the desired width
                    '--height', '500',  # Set the desired height
                    '--format', 'jpg',
                    html_file, image_file
                ]
                # command = ['wkhtmltoimage', '--quality', '100', '--format', 'jpg', html_file, image_file]
                subprocess.run(command, check=True)

                image_paths.append(image_file)

            # Create a ZIP file containing all the images
            zip_file_path = os.path.join(tmpdirname, "player_cards.zip")
            command = ['zip', '-j', zip_file_path] + image_paths
            subprocess.run(command, check=True)

            with open(zip_file_path, 'rb') as f:
                zip_data = f.read()

        # Serve the ZIP file for download
        response = request.make_response(
            zip_data,
            headers=[
                ('Content-Type', 'application/zip'),
                ('Content-Disposition', 'attachment; filename="player_cards.zip"'),
            ]
        )
        return response

    @http.route('/auction/live', type='http', auth='public', website=True)
    def auction_live_page(self, **kw):
        return request.render('auction_module.auction_live_page')

    @http.route('/auction/showcase', type='http', auth='user', website=True)
    def auction_showcase(self, **kw):
        """Redirect to the correct player showcase based on tournament algorithm."""
        tournament = request.env['auction.tournament'].sudo().search(
            [('active', '=', True)], limit=1
        )
        if tournament and tournament.player_appearance_algorithm == 'linear':
            return request.redirect('/auction/player_selector')
        return request.redirect('/auction/display_auction')

    @http.route('/auction/status/data', type='http', auth='public', website=True, csrf=False)
    def auction_status_data(self, last_id=0, **kw):

        last_id = int(last_id or 0)

        records = request.env['auction.history'].sudo().search(
            [('id', '>', last_id)],
            order='id asc',
            limit=20
        )

        data = []
        for rec in records:
            data.append({
                'id': int(rec.id),
                'message': str(rec.message or ''),
                'image_url': f"/web/image/auction.history/{rec.id}/player_photo",
            })

        payload = {
            'records': data,
            'last_id': int(data[-1]['id']) if data else last_id
        }

        return request.make_response(
            json.dumps(payload),
            headers=[('Content-Type', 'application/json')]
        )

    # ─────────────────────────────────────────────────────────────────
    #  PUBLIC LIVE AUCTION BOARD
    # ─────────────────────────────────────────────────────────────────

    # Whitelist of models and fields that public users may fetch images from.
    _PUBLIC_IMAGE_FIELDS = {
        'auction.team.player': ['photo'],
        'auction.team':        ['logo'],
        'auction.tournament':  ['logo'],
        'auction.history':     ['player_photo'],
    }

    @http.route('/auction/public/image/<string:model>/<int:record_id>/<string:field>',
                type='http', auth='public', website=True, csrf=False)
    def auction_public_image(self, model, record_id, field, **kw):
        """Serve binary images to unauthenticated users for the public live-board."""
        allowed_fields = self._PUBLIC_IMAGE_FIELDS.get(model)
        if not allowed_fields or field not in allowed_fields:
            return request.not_found()

        record = request.env[model].sudo().browse(record_id)
        if not record.exists():
            return request.not_found()

        binary = getattr(record, field, None)
        if not binary:
            return request.not_found()

        image_bytes = base64.b64decode(binary)
        return request.make_response(image_bytes, headers=[
            ('Content-Type', 'image/png'),
            ('Cache-Control', 'public, max-age=300'),  # 5-min browser cache
        ])

    @http.route('/auction/live-board', type='http', auth='public', website=True)
    def auction_live_board(self, **kw):
        env = request.env
        tournament = env['auction.tournament'].sudo().search(
            [('active', '=', True)], limit=1
        )
        theme = (tournament.player_display_template or 'vanilla') if tournament else 'vanilla'

        # Serve a static welcome page (no JS polling / no JSON payloads) when the
        # auction is not yet ready: either there is no active tournament, no auction
        # rules have been configured (auction.auction records), or no players have
        # been added to the player pool.
        auction_ready = False
        if tournament:
            has_rules = env['auction.auction'].sudo().search_count(
                [('tournament_id', '=', tournament.id)]
            ) > 0
            has_players = env['auction.team.player'].sudo().search_count([]) > 0
            auction_ready = has_rules and has_players

        if not auction_ready:
            return request.render('auction_module.welcome_message_template', {
                'tournament': tournament,
                'theme': theme,
            })

        return request.render('auction_module.public_live_board_template', {
            'tournament': tournament,
            'theme': theme,
        })

    @http.route('/auction/live-board/data', type='http', auth='public', website=True, csrf=False)
    def auction_live_board_data(self, **kw):
        env = request.env
        tournament = env['auction.tournament'].sudo().search(
            [('active', '=', True)], limit=1
        )

        def pub_img(model, record_id, field):
            return '/auction/public/image/%s/%d/%s' % (model, record_id, field)

        result = {
            'tournament': {},
            'current_player': None,
            'sold_info': None,
            'recent_history': [],
            'top_players': [],
            'teams': [],
            'theme': 'vanilla',
            'no_auction': True,
        }

        if tournament:
            result['theme'] = tournament.player_display_template or 'vanilla'
            result['tournament'] = {
                'name': tournament.name or '',
                'description': tournament.description or '',
                'logo_url': pub_img('auction.tournament', tournament.id, 'logo') if tournament.logo else '',
            }

        # ── Current player: ONLY show the player explicitly flagged as on stage ──
        current_player = env['auction.team.player'].sudo().search([
            ('is_on_stage', '=', True),
        ], limit=1)

        if current_player:
            result['no_auction'] = False

            # Base price: check all auctions (no tournament filter to be safe)
            base_price = 0
            t_id = tournament.id if tournament else False
            auc_domain = [('tournament_id', '=', t_id)] if t_id else []
            auctions_all = env['auction.auction'].sudo().search(auc_domain)
            if not auctions_all:
                auctions_all = env['auction.auction'].sudo().search([])
            for auc in auctions_all:
                base = auc.base_point or 0
                if current_player.tier_id and auc.tier_limit_ids:
                    tl = auc.tier_limit_ids.filtered(
                        lambda l: l.tier_id.id == current_player.tier_id.id
                    )
                    if tl and tl[0].base_point > 0:
                        base = tl[0].base_point
                if base > base_price:
                    base_price = base

            result['current_player'] = {
                'id': current_player.id,
                'name': current_player.name or '',
                'photo_url': pub_img('auction.team.player', current_player.id, 'photo') if current_player.photo else '',
                'role': current_player.role or '',
                'tier_name': current_player.tier_id.name if current_player.tier_id else '',
                'tier_color': current_player.tier_color or '#2252b5',
                'state': current_player.state,
                'sl_no': current_player.sl_no or 0,
                'icon_player': current_player.icon_player,
                'base_price': base_price,
                'batting_style': current_player.batting_style or '',
                'bowling_style': current_player.bowling_style or '',
            }

            # ── If sold, get final points from auction line ──
            if current_player.state == 'sold' and current_player.assigned_team_id:
                auc_line = env['auction.auction.player'].sudo().search(
                    [('player_id', '=', current_player.id)], limit=1
                )
                team = current_player.assigned_team_id
                result['sold_info'] = {
                    'team_name': team.name or '',
                    'team_logo_url': pub_img('auction.team', team.id, 'logo') if team.logo else '',
                    'amount': auc_line.points if auc_line else 0,
                }

        # ── Recent history (last 5 transactions) ──
        hist_domain = [('tournament_id', '=', tournament.id)] if tournament else []
        history = env['auction.history'].sudo().search(
            hist_domain, order='create_date desc', limit=5
        )
        if not history:
            history = env['auction.history'].sudo().search(
                [], order='create_date desc', limit=5
            )
        result['recent_history'] = [
            {
                'message': rec.message or '',
                'team_logo_url': pub_img('auction.team', rec.team_id.id, 'logo') if rec.team_id and rec.team_id.logo else '',
                'player_photo_url': pub_img('auction.history', rec.id, 'player_photo') if rec.player_photo else '',
                'timestamp': rec.create_date.strftime('%H:%M') if rec.create_date else '',
            }
            for rec in history
        ]

        # ── Top 5 most expensive sold players (MVP board) ──
        top_domain = [('auction_id.tournament_id', '=', tournament.id)] if tournament else []
        top_sold = env['auction.auction.player'].sudo().search(
            top_domain, order='points desc', limit=5
        )
        if not top_sold:
            top_sold = env['auction.auction.player'].sudo().search(
                [], order='points desc', limit=5
            )
        result['top_players'] = [
            {
                'rank': idx + 1,
                'player_name': rec.player_id.name or '',
                'player_photo_url': pub_img('auction.team.player', rec.player_id.id, 'photo') if rec.player_id and rec.player_id.photo else '',
                'role': rec.player_id.role or '',
                'team_name': rec.auction_id.team_id.name if rec.auction_id and rec.auction_id.team_id else '',
                'team_logo_url': pub_img('auction.team', rec.auction_id.team_id.id, 'logo') if rec.auction_id and rec.auction_id.team_id and rec.auction_id.team_id.logo else '',
                'points': rec.points,
            }
            for idx, rec in enumerate(top_sold)
        ]

        # ── Teams (from auctions in this tournament) ──
        auc_domain = [('tournament_id', '=', tournament.id)] if tournament else []
        auctions = env['auction.auction'].sudo().search(auc_domain)
        if not auctions:
            auctions = env['auction.auction'].sudo().search([])
        for auc in auctions:
            team = auc.team_id
            if team:
                result['teams'].append({
                    'id': team.id,
                    'name': team.name or '',
                    'logo_url': pub_img('auction.team', team.id, 'logo') if team.logo else '',
                    'remaining_points': auc.remaining_points,
                    'manager': team.manager or '',
                })

        return request.make_response(
            json.dumps(result),
            headers=[('Content-Type', 'application/json'), ('Cache-Control', 'no-store')]
        )

    # ── Player Registration Form ──────────────────────────────────────────────

    @http.route('/player/register', type='http', auth='public', website=True,
                methods=['GET', 'POST'], csrf=False)
    def player_register(self, **kw):
        """Public player self-registration form. Creates a draft player record."""
        tournament = request.env['auction.tournament'].sudo().search(
            [('active', '=', True)], limit=1
        )
        theme = (tournament.player_display_template or 'vanilla') if tournament else 'vanilla'

        # Gate: registration must be explicitly opened by the admin
        if not tournament or not tournament.registration_open:
            return request.render('auction_module.player_registration_form', {
                'tournament': tournament,
                'tiers': request.env['auction.player.tier'].sudo().search([], order='name asc'),
                'theme': theme,
                'registration_closed': True,
            })

        tiers = request.env['auction.player.tier'].sudo().search([], order='name asc')

        if request.httprequest.method == 'POST':
            try:
                vals = _build_player_vals_from_post(request, tournament)
                player = request.env['auction.team.player'].sudo().create(vals)
                return request.render('auction_module.player_registration_form', {
                    'tournament': tournament,
                    'tiers': tiers,
                    'theme': theme,
                    'success': True,
                    'player_id': player.id,
                })
            except Exception as e:
                return request.render('auction_module.player_registration_form', {
                    'tournament': tournament,
                    'tiers': tiers,
                    'theme': theme,
                    'error': str(e),
                })

        return request.render('auction_module.player_registration_form', {
            'tournament': tournament,
            'tiers': tiers,
            'theme': theme,
        })

    @http.route('/player/card/<int:player_id>', type='http', auth='public', sitemap=False)
    def player_card_download(self, player_id, **kw):
        """Stream the themed player-card PDF for the given player (public, read-only)."""
        player = request.env['auction.team.player'].sudo().browse(player_id)
        if not player.exists():
            return request.not_found()

        tournament = player.tournament_id
        theme = (tournament.player_display_template or 'vanilla') if tournament else 'vanilla'

        report_map = {
            'vanilla':      'auction_module.action_report_player_card',
            'butterscotch': 'auction_module.action_report_player_card_butterscotch',
            'strawberry':   'auction_module.action_report_player_card_strawberry',
            'cherry':       'auction_module.action_report_player_card_cherry',
            'pistah':       'auction_module.action_report_player_card_pistah',
        }
        report_ref = report_map.get(theme, 'auction_module.action_report_player_card')

        report = request.env.ref(report_ref).sudo()
        pdf_content, _mime = report._render_qweb_pdf([player_id])
        filename = 'PlayerCard_%s.pdf' % (player.name or player_id)
        return request.make_response(
            pdf_content,
            headers=[
                ('Content-Type', 'application/pdf'),
                ('Content-Length', len(pdf_content)),
                ('Content-Disposition', 'attachment; filename="%s"' % filename),
            ]
        )


def _build_player_vals_from_post(request, tournament):
    """Extract and validate POST form data into a dict for auction.team.player.create()."""
    post = request.httprequest.form
    files = request.httprequest.files

    name = (post.get('name') or '').strip()
    if not name:
        raise ValueError("Player name is required.")

    # Determine next sl_no
    last = request.env['auction.team.player'].sudo().search(
        [], limit=1, order='sl_no desc'
    )
    sl_no = (last.sl_no + 1) if last else 1

    tier_id = False
    raw_tier = post.get('tier_id')
    if raw_tier and raw_tier.isdigit():
        tier_id = int(raw_tier)

    # Photo upload
    photo_data = False
    photo_file = files.get('photo')
    if photo_file and photo_file.filename:
        photo_data = base64.b64encode(photo_file.read())

    # Payment proof upload
    payment_proof_data = False
    proof_file = files.get('payment_proof')
    if proof_file and proof_file.filename:
        payment_proof_data = base64.b64encode(proof_file.read())

    vals = {
        'sl_no':         sl_no,
        'name':          name,
        'role':          post.get('role') or '',
        'batting_style': post.get('batting_style') or 'Right Handed',
        'bowling_style': post.get('bowling_style') or 'Right Arm',
        'contact':       (post.get('contact') or '').strip(),
        'address':       (post.get('address') or '').strip(),
        'blood_group':   (post.get('blood_group') or '').strip(),
        'current_team':  (post.get('current_team') or '').strip(),
        'state':         'draft',
        'photo':         photo_data,
        'payment_proof': payment_proof_data,
    }
    if tier_id:
        vals['tier_id'] = tier_id
    if tournament:
        vals['tournament_id'] = tournament.id

    # Jersey section (only if enabled for this tournament)
    if tournament and tournament.enable_jersey_section:
        vals['jersy_name']   = (post.get('jersy_name') or '').strip()
        vals['jersy_number'] = (post.get('jersy_number') or '').strip()
        vals['jersy_size']   = (post.get('jersy_size') or '').strip()

    return vals
