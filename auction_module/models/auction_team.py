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

import base64
import io
import os
import re
import shutil
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

from odoo import api, models, fields, _
from odoo.exceptions import UserError
from odoo.tools.image import image_data_uri

import werkzeug
import werkzeug.exceptions

class AuctionTeam(models.Model):
    _name = 'auction.team'
    _description = 'Auction Team'
    _inherit = [
        'auction.image.compress.mixin',
        'auction.tournament.security.mixin',
        'auction.live.snapshot.mixin',
    ]

    _compressible_image_fields = {
        'logo': (400, 400, 82, 'JPEG'),
        'owner_photo': (400, 400, 82, 'JPEG'),
    }

    @api.model
    def default_get(self, fields_list):
        defaults = super().default_get(fields_list)
        if not defaults.get('tournament_id'):
            user_tournament = self.env.user.tournament_id
            if user_tournament:
                defaults['tournament_id'] = user_tournament.id
        return defaults

    active = fields.Boolean(default=True)
    name = fields.Char(string="Team Name", required=True)
    logo = fields.Binary(string="Team Logo",
                            help="Add team logo")
    tournament_id = fields.Many2one('auction.tournament', 'Tournament')
    manager = fields.Char('Owner')
    owner_photo = fields.Binary(
        string='Owner Photo',
        attachment=True,
        help='Optional. When set, the Squad Poster shows TEAM OWNER, this photo, '
             'and the owner name.',
    )
    squad_poster_owner_crop = fields.Char(
        string='Squad Poster Owner Crop',
        help='JSON crop window {l,t,sw,sh} for the owner photo on the squad poster.',
    )
    key_player_ids = fields.Many2many('auction.team.player', 'team_player_rel', 'team_id', 'player_id', 'Icon Players')

    # Match squad poster export orientation/dimensions.
    _ICON_POSTER_W = 1024
    _ICON_POSTER_H = 1536

    @api.model
    def _icon_render_binary(self):
        for cand in ('/usr/local/bin/wkhtmltoimage', '/usr/bin/wkhtmltoimage', 'wkhtmltoimage'):
            path = cand if os.path.isabs(cand) else shutil.which(cand)
            if path and os.path.exists(path):
                return path
        return None

    @api.model
    def _icon_workdir(self):
        return tempfile.mkdtemp(prefix='ac_icon_posters_')

    @api.model
    def _icon_asset_data_uri(self, parts, mime='image/jpeg'):
        path = os.path.join(os.path.dirname(os.path.dirname(__file__)), *parts)
        try:
            with open(path, 'rb') as fh:
                b64 = base64.b64encode(fh.read()).decode('ascii')
            return 'data:%s;base64,%s' % (mime, b64)
        except Exception:
            return ''

    @staticmethod
    def _icon_safe_filename(name, used):
        base = re.sub(r'[^A-Za-z0-9]+', '_', (name or 'Icon_Player').strip()).strip('_') or 'Icon_Player'
        candidate = base
        i = 1
        while candidate.lower() in used:
            i += 1
            candidate = '%s_%d' % (base, i)
        used.add(candidate.lower())
        return candidate + '.jpg'

    def _icon_poster_values(self, team, player):
        tournament = team.tournament_id
        def uri(binary_val):
            try:
                return image_data_uri(binary_val) if binary_val else ''
            except Exception:
                return ''

        return {
            'team': team,
            'player': player,
            'tournament': tournament,
            'tournament_name': (tournament.name or '') if tournament else '',
            'tournament_desc': (tournament.description or '') if tournament else '',
            'tournament_logo_uri': uri(tournament.logo) if tournament else '',
            'team_name': team.name or '',
            'team_logo_uri': uri(team.logo),
            'player_photo_uri': uri(player.photo or player.photo_card),
            'player_name': player.name or '',
            'player_role': player.role or 'Icon Player',
            'stadium_bg_uri': self._icon_asset_data_uri(('static', 'img', 'stadium_cricket.jpg')),
            'flame_bg_uri': self._icon_asset_data_uri(('static', 'src', 'assets', 'images', 'squad_poster', 'sp_fire_band.jpg')),
        }

    def _render_icon_poster_html(self, team, player):
        html = self.env['ir.qweb']._render(
            'auction_module.icon_player_poster_image',
            self._icon_poster_values(team, player),
        )
        if isinstance(html, bytes):
            html = html.decode('utf-8')
        return str(html)

    def _icon_html_to_jpg(self, html, workdir, binary):
        import uuid as _uuid
        base = os.path.join(workdir, _uuid.uuid4().hex)
        hpath, opath = base + '.html', base + '.jpg'
        with open(hpath, 'w', encoding='utf-8') as fh:
            fh.write(html)
        cmd = [
            binary, '--format', 'jpg', '--quality', '100',
            '--width', str(self._ICON_POSTER_W), '--height', str(self._ICON_POSTER_H),
            '--disable-smart-width',
            '--enable-local-file-access',
            '--load-error-handling', 'ignore',
            '--load-media-error-handling', 'ignore',
            '--quiet', hpath, opath,
        ]
        try:
            subprocess.run(cmd, timeout=180, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except subprocess.TimeoutExpired:
            return None
        if not (os.path.exists(opath) and os.path.getsize(opath) > 0):
            return None
        with open(opath, 'rb') as fh:
            return fh.read()

    def action_download_icon_player_posters(self):
        import zipfile

        teams = self.exists()
        if not teams:
            raise UserError(_('Please select at least one team.'))

        binary = self._icon_render_binary()
        if not binary:
            raise UserError(_(
                'The wkhtmltoimage tool was not found on the server. '
                'Please install wkhtmltox to export icon posters as JPG.'))

        jobs = []
        used_names = set()
        for team in teams:
            icon_players = team.key_player_ids.filtered(lambda p: p.icon_player)
            for player in icon_players:
                html = self._render_icon_poster_html(team, player)
                fname = self._icon_safe_filename(
                    '%s_%s_Icon_Poster' % ((team.name or 'Team'), (player.name or 'Player')),
                    used_names,
                )
                jobs.append((fname, html))
        if not jobs:
            raise UserError(_('No icon players found in the selected team(s).'))

        workdir = self._icon_workdir()
        zip_buf = io.BytesIO()
        failed = []
        try:
            def _render_one(job):
                fname, html = job
                return fname, self._icon_html_to_jpg(html, workdir, binary)

            workers = min(6, max(1, len(jobs)))
            results = []
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futures = {pool.submit(_render_one, job): job for job in jobs}
                for fut in as_completed(futures):
                    results.append(fut.result())

            with zipfile.ZipFile(zip_buf, 'w', zipfile.ZIP_DEFLATED) as zf:
                for fname, jpg in results:
                    if jpg:
                        zf.writestr(fname, jpg)
                    else:
                        failed.append(fname)
                if failed:
                    note = (u'%d poster(s) failed to generate:\n\n%s'
                            % (len(failed), u'\n'.join(failed)))
                    zf.writestr('_FAILED_ICON_POSTERS.txt', note.encode('utf-8'))
        finally:
            shutil.rmtree(workdir, ignore_errors=True)

        if zip_buf.getbuffer().nbytes == 0:
            raise UserError(_('Icon poster generation failed. Please check server logs.'))

        tname = teams[0].tournament_id.name if teams[0].tournament_id else 'Tournament'
        tname = re.sub(r'[^A-Za-z0-9]+', '_', tname).strip('_') or 'Tournament'
        zipname = 'Icon_Posters_%s_%s.zip' % (tname, datetime.now().strftime('%Y%m%d_%H%M%S'))
        attachment = self.env['ir.attachment'].create({
            'name': zipname,
            'type': 'binary',
            'datas': base64.b64encode(zip_buf.getvalue()),
            'mimetype': 'application/zip',
            'res_model': 'auction.team',
        })
        return {
            'type': 'ir.actions.act_url',
            'url': '/web/content/%s?download=true' % attachment.id,
            'target': 'self',
        }
