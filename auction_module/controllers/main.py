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
        return request.render(
            'auction_module.player_sequence_selector'
        )

    #sequence_template_part
    @http.route('/auction/get_players_queue', type='json', auth='public', website=True)
    def get_players_queue(self):

        players = request.env['auction.team.player'].sudo().get_auction_players(
        )

        return [
            {'serial': p.sl_no, 'id': p.id}
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

    @http.route('/auction/player_modal/<int:player_id>', type='http', auth='public', website=True)
    def get_player_modal(self, player_id):
        """Render player template for modal display"""
        player = request.env['auction.team.player'].sudo().browse(int(player_id))

        if not player.exists():
            return request.make_response('{"error": "Player not found"}', headers=[('Content-Type', 'application/json')])

        tournament_id = request.env['auction.tournament'].sudo().search([('active', '=', True)], limit=1)

        html_content = request.env['ir.ui.view']._render_template('auction_module.player_template_modal_content', {
            'player': player,
            'tournament': tournament_id
        })

        return request.make_response(html_content, headers=[('Content-Type', 'text/html; charset=utf-8')])

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
        auctions = request.env['auction.auction'].sudo().search([])
        tournament = auctions.mapped('tournament_id')
        type = 'internal'
        if request.env.user.login == 'public':
            type = 'public'
        result = request.render("auction_module.auction_details_show", {'teams': auctions, 'tournament': tournament, 'type': type})

        return result

    @http.route(['''/auction/display_auction/'''], type='http', auth="public", website=True, sitemap=True)
    def display_auction(self,**kwargs):

        player = request.env['auction.team.player'].sudo().get_random_player()
        tournament_id = request.env['auction.tournament'].sudo().search([('active', '=', True)], limit=1)
        if player:
            auction_ids = request.env['auction.auction'].sudo().search([])
            template_map = {
                'vanilla':       'auction_module.player_template_new',
                'butterscotch':  'auction_module.player_template_butterscotch',
                'strawberry':    'auction_module.player_template_strawberry',
                'cherry':        'auction_module.player_template_cherry',
            }
            chosen = tournament_id.player_display_template if tournament_id else 'vanilla'
            template_ref = template_map.get(chosen, 'auction_module.player_template_new')
            r = request.render(template_ref, {'player': player, 'tournament': tournament_id, 'auction_ids': auction_ids})
        else:
            r = request.render("auction_module.welcome_message_template", {'tournament': tournament_id})
        return r

    @http.route('/auction/get/players/team/<int:team_id>', type='http', auth='public', website=True)
    def get_team_players(self, team_id):
        player_data_list = []
        team_players = request.env['auction.auction.player'].search([('auction_id.team_id', '=', team_id)])

        team = request.env['auction.team'].browse(team_id)
        icon_players = request.env['auction.team.player'].get_icon_players(team_id)
        if icon_players:
            for icon in icon_players:
                player_data = {
                    'name': icon.name,
                    'photo': icon.photo,
                    'point': 'ICON',
                    'role': icon.role,
                    'batting_style': icon.batting_style,
                    'bowling_style': icon.batting_style,
                    'contact': icon.contact,
                    'p_type': icon.p_type,
                    'p_category': icon.p_category,
                    'tier_color': icon.tier_id.color if icon.tier_id else '#01cfff',
                    'tier_name': icon.tier_id.name if icon.tier_id else '',
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
                    'bowling_style': player.player_id.batting_style,
                    'contact': player.player_id.contact,
                    'p_type': player.player_id.p_type,
                    'p_category': player.player_id.p_category,
                    'tier_color': player.player_id.tier_id.color if player.player_id.tier_id else '#01cfff',
                    'tier_name': player.player_id.tier_id.name if player.player_id.tier_id else '',
                }
                player_data_list.append(player_data)
        return request.render('auction_module.auction_team_players_template', {'players': player_data_list, 'team': team})

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
