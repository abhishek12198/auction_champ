# -*- coding: utf-8 -*-
import base64

from odoo import api, models, fields, _
from odoo.exceptions import UserError
from odoo.tools.image import image_data_uri

import werkzeug
import werkzeug.exceptions

class Question(models.Model):

    _name = 'odoo.question'

    name = fields.Char(string="Question", required=True)

    type = fields.Selection([
        ("char", "Text"),
        ("selection", "Selection"),
        ("date", "Date"),
        ("datetime", "Datetime"),
        ("boolean", "Yes/No"),
    ], string="Type", required=True, default="char")
    category = fields.Char(string="Category")



