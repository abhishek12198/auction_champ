document.addEventListener('click', function (ev) {
    const btn = ev.target.closest('.o_take_pool_snapshot');
    if (!btn) return;

    // ⛔ STOP Odoo FormController
    ev.preventDefault();
    ev.stopPropagation();
    ev.stopImmediatePropagation();

    const container = document.getElementById('pool_snapshot_container');
    if (!container || !container.innerHTML.trim()) {
        alert('Generate pools before taking snapshot.');
        return;
    }

    btn.style.visibility = 'hidden';

    html2canvas(container, {
        scale: 2,
        backgroundColor: '#ffffff',
        useCORS: true,
    }).then(function (canvas) {
        btn.style.visibility = 'visible';

        const link = document.createElement('a');
        link.href = canvas.toDataURL('image/png');
        link.download = 'team_pools.png';
        link.click();
    });
});
