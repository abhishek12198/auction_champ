/* 3-step player registration — vanilla JS, no Odoo webclient. */
(function () {
    var posterOverlay = document.getElementById('regPosterOverlay');
    var posterClose = document.getElementById('regPosterClose');
    function closePoster() {
        if (!posterOverlay) return;
        posterOverlay.classList.remove('open');
        posterOverlay.setAttribute('aria-hidden', 'true');
        document.body.classList.remove('reg-roster-lock');
    }
    function openPoster() {
        if (!posterOverlay) return;
        posterOverlay.classList.add('open');
        posterOverlay.setAttribute('aria-hidden', 'false');
        document.body.classList.add('reg-roster-lock');
    }
    document.querySelectorAll('.reg-poster-open').forEach(function (btn) {
        btn.addEventListener('click', openPoster);
    });
    if (posterClose) posterClose.addEventListener('click', closePoster);
    if (posterOverlay) {
        posterOverlay.addEventListener('click', function (ev) {
            if (ev.target === posterOverlay) closePoster();
        });
        document.addEventListener('keydown', function (ev) {
            if (ev.key === 'Escape' && posterOverlay.classList.contains('open')) closePoster();
        });
    }

    var form = document.getElementById('playerRegisterForm');
    if (!form || !document.body.classList.contains('reg-page--steps')) return;
    form.setAttribute('novalidate', 'novalidate');

    var nav = document.getElementById('regStepsNav');
    var backBtn = document.getElementById('regStepBack');
    var nextBtn = document.getElementById('regStepNext');
    var submitBtn = document.getElementById('regStepSubmit');
    var clearBtn = document.getElementById('regStepClear');
    var current = 1;
    var maxStep = 3;
    var booted = false;
    var STEP_LABELS = {1: 'Player', 2: 'Game', 3: 'Pay & submit'};

    function showAlert(message, focusEl) {
        var alertBox = document.getElementById('regClientAlert');
        var alertMsg = document.getElementById('regClientAlertMsg');
        if (alertMsg) alertMsg.textContent = message || 'Please fill all mandatory fields marked with *.';
        if (alertBox) {
            alertBox.style.display = 'flex';
            try { alertBox.scrollIntoView({ behavior: 'smooth', block: 'start' }); } catch (e) {}
        }
        if (focusEl && focusEl.focus) {
            setTimeout(function () {
                try { focusEl.scrollIntoView({ behavior: 'smooth', block: 'center' }); } catch (e2) {}
                focusEl.focus();
            }, 80);
        } else if (focusEl) {
            setTimeout(function () {
                try { focusEl.scrollIntoView({ behavior: 'smooth', block: 'center' }); } catch (e3) {}
            }, 80);
        }
    }

    function clearMarks() {
        form.querySelectorAll('[data-reg-missing]').forEach(function (el) {
            el.removeAttribute('data-reg-missing');
            el.removeAttribute('aria-invalid');
            el.classList.remove('reg-field-missing', 'was-invalid');
        });
        if (nav) {
            nav.querySelectorAll('.reg-step-missing').forEach(function (el) {
                el.classList.remove('reg-step-missing');
            });
        }
    }

    function visualTarget(el) {
        if (!el) return null;
        if (el.id === 'photoSection' || el.id === 'photoInput') {
            return document.querySelector('#photoSection .reg-photo-upload') || document.getElementById('photoSection');
        }
        if (el.id === 'paymentSection' || el.id === 'paymentInput' || el.id === 'paymentUploadBox') {
            return document.getElementById('paymentUploadBox') || document.getElementById('paymentSection');
        }
        if (el.type === 'radio' || el.type === 'checkbox') {
            return el.closest('.reg-role-group, .reg-chip-group, .reg-radio-stack, .reg-extra-q') || el;
        }
        return el;
    }

    function paintIssues(issues) {
        clearMarks();
        issues.forEach(function (it) {
            var target = visualTarget(it.el);
            if (target && target.classList) {
                target.classList.add('reg-field-missing');
                target.setAttribute('data-reg-missing', '1');
            }
            if (it.el && it.el.classList) {
                it.el.classList.add('was-invalid');
                it.el.setAttribute('data-reg-missing', '1');
                if (it.el.matches && it.el.matches('input, select, textarea')) {
                    it.el.setAttribute('aria-invalid', 'true');
                }
            }
            if (nav) {
                var btn = nav.querySelector('.reg-step[data-step="' + it.step + '"]');
                if (btn) btn.classList.add('reg-step-missing');
            }
        });
    }

    function hideAlert() {
        var alertBox = document.getElementById('regClientAlert');
        if (alertBox) alertBox.style.display = 'none';
        var serverBox = document.getElementById('regServerAlert');
        if (serverBox) serverBox.style.display = 'none';
        clearMarks();
        var photoErr = document.getElementById('photoErrorMsg');
        if (photoErr) photoErr.remove();
        var paySection = document.getElementById('paymentSection');
        var missed = document.getElementById('paymentMissedBanner');
        var payErr = document.getElementById('paymentErrorMsg');
        if (paySection) paySection.classList.remove('is-missing');
        if (missed) missed.style.display = 'none';
        if (payErr) payErr.style.display = 'none';
    }

    function warningShowing() {
        var alertBox = document.getElementById('regClientAlert');
        return !!(alertBox && alertBox.style.display === 'flex');
    }

    function refreshWarning() {
        if (!warningShowing() && !form.querySelector('[data-reg-missing]')) return;
        var gate = document.getElementById('paymentProofGate');
        if (gate) gate.value = hasPaymentProof() ? 'ok' : '';
        var issues = collectIssues();
        if (!issues.length) {
            hideAlert();
            return;
        }
        paintIssues(issues);
        if (warningShowing()) {
            var alertMsg = document.getElementById('regClientAlertMsg');
            if (alertMsg) alertMsg.textContent = formatIssues(issues);
        }
    }

    function photoOk() {
        var photoInput = document.getElementById('photoInput');
        var sourceEl = document.getElementById('sourcePlayerId');
        var hasSourcePhoto = !!(sourceEl && sourceEl.value && sourceEl.getAttribute('data-has-photo') === '1');
        var hasNewPhoto = !!(photoInput && photoInput.files && photoInput.files[0]);
        return hasNewPhoto || hasSourcePhoto;
    }

    function paymentRequired() {
        var section = document.getElementById('paymentSection');
        var paymentInput = document.getElementById('paymentInput');
        var gate = document.getElementById('paymentProofGate');
        return form.getAttribute('data-payment-required') === '1'
            || (section && section.getAttribute('data-payment-required') === '1')
            || (paymentInput && paymentInput.getAttribute('data-required') === '1')
            || !!gate;
    }

    function hasPaymentProof() {
        var paymentInput = document.getElementById('paymentInput');
        return !!(paymentInput && paymentInput.files && paymentInput.files[0]);
    }

    function fieldCaption(el) {
        if (!el) return 'This field';
        if (el.id === 'paymentProofGate' || el.name === 'payment_proof_gate' || el.name === 'payment_proof') {
            return 'Payment proof';
        }
        if (el.id === 'jerseySize' || el.name === 'jersy_size') return 'Jersey size';
        if (el.id === 'jerseySleeve' || el.name === 'jersy_sleeve') return 'Sleeve';
        if (el.name === 'role') return 'Role';
        if (el.type === 'radio' || el.type === 'checkbox') {
            var group = el.closest('.reg-extra-q');
            var groupLbl = group && group.querySelector('.reg-label');
            if (groupLbl) {
                var groupRaw = (groupLbl.textContent || '').replace(/\*/g, '').replace(/\(optional\)/ig, '').trim();
                if (groupRaw) return groupRaw;
            }
        }
        if (el.id) {
            var lbl = form.querySelector('label[for="' + el.id + '"]');
            if (lbl) {
                var raw = (lbl.textContent || '').replace(/\*/g, '').replace(/\(optional\)/ig, '').trim();
                if (raw) return raw;
            }
        }
        if (el.name) return el.name.replace(/_/g, ' ');
        return 'This field';
    }

    function stepOf(el) {
        var box = el && el.closest ? el.closest('[data-reg-step]') : null;
        var n = box ? parseInt(box.getAttribute('data-reg-step'), 10) : 0;
        return n || 1;
    }

    function collectIssues() {
        var issues = [];
        var seen = {};

        function add(step, el, msg) {
            var key = step + ':' + msg;
            if (seen[key]) return;
            seen[key] = true;
            issues.push({step: step, el: el, msg: msg});
        }

        if (!photoOk()) {
            add(1, document.getElementById('photoSection') || document.getElementById('photoInput'), 'Player photo');
        }
        if (paymentRequired() && !hasPaymentProof()) {
            add(3, document.getElementById('paymentSection') || document.getElementById('paymentInput'), 'Payment proof');
        }

        var els = form.querySelectorAll('input, select, textarea');
        for (var i = 0; i < els.length; i++) {
            var el = els[i];
            if (el.disabled || el.type === 'hidden' || el.type === 'submit' || el.type === 'button' || el.type === 'file') continue;
            if (el.id === 'paymentProofGate' || el.name === 'payment_proof_gate') continue;
            if (!el.checkValidity()) add(stepOf(el), el, fieldCaption(el));
        }
        return issues;
    }

    function formatIssues(issues) {
        var by = {};
        issues.forEach(function (it) {
            if (!by[it.step]) by[it.step] = [];
            by[it.step].push(it.msg);
        });
        var parts = [];
        [1, 2, 3].forEach(function (step) {
            if (!by[step]) return;
            parts.push(
                'Go to ' + STEP_LABELS[step] + ' (step ' + step + ') to add or correct:\n' +
                by[step].map(function (item) { return '• ' + item; }).join('\n')
            );
        });
        return parts.join('\n\n');
    }

    function goTo(n, force) {
        n = Math.max(1, Math.min(maxStep, n));
        if (!force && n > current) return;
        current = n;
        document.querySelectorAll('[data-reg-step]').forEach(function (box) {
            var on = String(box.getAttribute('data-reg-step')) === String(current);
            box.classList.toggle('is-step-hidden', !on);
            box.setAttribute('aria-hidden', on ? 'false' : 'true');
        });
        if (nav) {
            nav.querySelectorAll('.reg-step').forEach(function (btn) {
                var step = parseInt(btn.getAttribute('data-step'), 10);
                btn.classList.toggle('is-on', step === current);
                btn.classList.toggle('is-done', step < current);
                if (step === current) btn.setAttribute('aria-current', 'step');
                else btn.removeAttribute('aria-current');
            });
        }
        if (backBtn) backBtn.hidden = current === 1;
        if (nextBtn) nextBtn.hidden = current === maxStep;
        if (submitBtn) submitBtn.hidden = current !== maxStep;
        if (clearBtn) clearBtn.hidden = current !== 1;
        if (booted) {
            var start = document.getElementById('reg-form-start');
            if (start) {
                try { start.scrollIntoView({ behavior: 'smooth', block: 'start' }); } catch (e) {}
            }
        }
        booted = true;
    }

    if (nextBtn) {
        nextBtn.addEventListener('click', function () { goTo(current + 1, true); });
    }
    if (backBtn) {
        backBtn.addEventListener('click', function () { goTo(current - 1, true); });
    }
    if (nav) {
        nav.addEventListener('click', function (ev) {
            var btn = ev.target.closest('.reg-step');
            if (!btn) return;
            var step = parseInt(btn.getAttribute('data-step'), 10);
            if (!step) return;
            goTo(step, true);
        });
    }

    document.addEventListener('click', function (ev) {
        if (!ev.target.closest('[data-reg-alert-clear]')) return;
        hideAlert();
    });
    form.addEventListener('input', refreshWarning);
    form.addEventListener('change', refreshWarning);
    form.addEventListener('reset', function () {
        setTimeout(hideAlert, 0);
    });

    form.addEventListener('submit', function (e) {
        if (current !== maxStep) {
            e.preventDefault();
            goTo(current + 1, true);
            return;
        }
        var gate = document.getElementById('paymentProofGate');
        if (gate) gate.value = hasPaymentProof() ? 'ok' : '';

        var issues = collectIssues();
        if (!issues.length) {
            hideAlert();
            return;
        }
        e.preventDefault();
        e.stopPropagation();
        showAlert(formatIssues(issues), issues[0].el);
        goTo(issues[0].step, true);
        paintIssues(issues);
    });

    goTo(1, true);
})();
