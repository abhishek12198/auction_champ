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
            r = request.render("auction_module.player_template_new", {'player': player, 'tournament': tournament_id, 'auction_ids': auction_ids})
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
