# -*- coding: utf-8 -*-
import base64

from odoo import api, models, fields, _
from odoo.exceptions import UserError
from odoo.tools.image import image_data_uri

import werkzeug
import werkzeug.exceptions

class Survey(models.Model):

    _name = 'odoo.survey'

    @api.model
    def default_get(self, fields):
        defaults = super(Survey, self).default_get(fields)
        question_records = self.env['odoo.question'].search([])
        question_list = []
        if question_records:
            for question in question_records:
                question_data = {
                    'name': question.name,
                    'category': question.category,
                    'question_id': question.id,
                    'type': question.type

                }
                question_list.append((0, 0, question_data))

        if question_list:
            defaults.update({'survey_question_ids': question_list})
        return defaults

    name = fields.Char(string="Name of the Survey", required=True)

    survey_question_ids = fields.One2many('odoo.survey.question', 'survey_id', string="Questions")

class SurveyQuestions(models.Model):
    _name = 'odoo.survey.question'

    name = fields.Char(string="Question", required=True)
    type = fields.Selection([
        ("char", "Text"),
        ("selection", "Selection"),
        ("date", "Date"),
        ("datetime", "Datetime"),
        ("boolean", "Yes/No"),
    ], string="Type", required=True, default="char")
    category = fields.Char(string="Category")
    answer = fields.Char(string="Answer")
    question_id = fields.Many2one('odoo.question', string='Question')
    survey_id = fields.Many2one('odoo.survey', 'Survey')


