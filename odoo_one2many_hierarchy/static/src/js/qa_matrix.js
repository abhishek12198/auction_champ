/** odoo_one2many_hierarchy/static/src/js/qa_matrix.js (fixed for your schema) **/
odoo.define('odoo_one2many_hierarchy.QAMatrix', function (require) {
    "use strict";

    const AbstractField = require('web.AbstractField');
    const fieldRegistry = require('web.field_registry');
    const rpc = require('web.rpc');
    const core = require('web.core');
    const qweb = core.qweb;

    /**
     * Works on odoo.survey.survey_question_ids (one2many to odoo.survey.question)
     * Master questions model: odoo.question with fields: name (Char), type (Selection), category (Char)
     * Line model: odoo.survey.question with fields: question_id (M2O), category (Char), type (Selection), name (Char), answer (Char)
     */
    const QAMatrix = AbstractField.extend({
        className: 'o_qa_matrix',
        supportedFieldTypes: ['one2many'],

        willStart() {
            const _super = this._super.bind(this);

            // Map existing O2M cached lines: question_id -> line
            this._answerMap = {};
            const lines = (this.value && this.value.data) ? this.value.data : [];
            lines.forEach(l => {
                const qid = l.data.question_id && l.data.question_id.res_id;
                if (qid) this._answerMap[qid] = l;
            });

            // Fetch ALL master questions; group by char category
            const fields = ['name', 'type', 'category']; // your schema
            return Promise.all([
                _super(),
                rpc.query({
                    model: 'odoo.question',
                    method: 'search_read',
                    args: [[], fields],
                }).catch(() => []) // don't block the form if RPC fails
            ]).then(([_, questions]) => {
                const grouped = {};
                (questions || []).forEach(q => {
                    const cat = q.category || 'Uncategorized';
                    if (!grouped[cat]) grouped[cat] = [];
                    grouped[cat].push(q);
                });
                this._groups = grouped;
            });
        },

        _render() {
            this.$el.empty();
            const html = qweb.render('odoo_one2many_hierarchy.QAMatrix', {
                groups: this._groups || {},
                answerMap: this._answerMap || {},
            });
            this.$el.html(html);
            this._bindEvents();
        },

        _bindEvents() {
            const self = this;
            this.$('.o-qa-input').on('change', function (ev) {
                const $el = $(ev.currentTarget);
                const qid = parseInt($el.data('qid'));
                const qcat = $el.data('qcat') || '';
                const qtype = $el.data('qtype') || 'char';
                const qname = $el.data('qname') || '';
                let val = $el.val();
                if ($el.attr('type') === 'checkbox') {
                    val = $el.is(':checked') ? 'True' : 'False';
                }
                self._upsertAnswer(qid, qcat, qtype, qname, val);
            });
        },

        _upsertAnswer(question_id, category, qtype, qname, answerText) {
            const existing = this._answerMap[question_id];
            if (existing) {
                const commands = [[1, existing.id, { answer: answerText }]];
                this._apply(commands);
            } else {
                const commands = [[0, 0, {
                    survey_id: this.record.res_id || false, // ok even if record is new
                    question_id: question_id,
                    category: category || '',
                    type: qtype || 'char',
                    name: qname || '',       // copy question text to line.name (your schema has it)
                    answer: answerText,
                }]];
                this._apply(commands);
            }
        },

        _apply(commands) {
            this._setValue({ operation: 'UPDATE', commands });
        },
    });

    fieldRegistry.add('qa_matrix', QAMatrix);
    return QAMatrix;
});
