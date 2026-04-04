document.addEventListener('click', function (ev) {
    const btn = ev.target.closest('.o_take_pool_snapshot');
    if (!btn) return;

    ev.preventDefault();
    ev.stopPropagation();
    ev.stopImmediatePropagation();

    const container = document.getElementById('pool_snapshot_container');
    if (!container || !container.innerHTML.trim()) {
        alert('Generate pools before taking snapshot.');
        return;
    }

    // Walk into Odoo's Html field wrapper to reach the real content
    const fieldEl = container.querySelector('.odoo-editor-editable')
                 || container.querySelector('.o_field_html > div')
                 || container.querySelector('.o_field_html')
                 || container;

    // Clone into an off-screen div on the same page (avoids popup blockers)
    const clone = document.createElement('div');
    clone.style.cssText = [
        'position:fixed',
        'top:0',
        'left:-99999px',
        'width:900px',
        'background:#0d0d2b',
        'display:block',
        'z-index:-9999',
    ].join(';');
    clone.innerHTML = fieldEl.innerHTML;
    document.body.appendChild(clone);

    // Force browser to lay out the clone before measuring
    void clone.offsetHeight;

    const origText = btn.innerHTML;
    btn.innerHTML = '⏳ Generating...';
    btn.style.pointerEvents = 'none';

    html2canvas(clone, {
        scale        : 2,
        backgroundColor: '#0d0d2b',
        useCORS      : true,
        allowTaint   : true,
        logging      : false,
        imageTimeout : 0,
    }).then(function (canvas) {
        document.body.removeChild(clone);
        btn.innerHTML = origText;
        btn.style.pointerEvents = '';

        const link = document.createElement('a');
        link.href     = canvas.toDataURL('image/png');
        link.download = 'pool_draw.png';
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
    }).catch(function (err) {
        document.body.removeChild(clone);
        btn.innerHTML = origText;
        btn.style.pointerEvents = '';
        console.error('Snapshot error:', err);
        alert('Snapshot failed — see browser console for details.');
    });
});
