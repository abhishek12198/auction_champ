/** @odoo-module **/

console.log('Screenshot JS loaded');

document.addEventListener('click', function (ev) {
    const btn = ev.target.closest('.o_take_screenshot');
    if (!btn) return;

    ev.preventDefault();
    ev.stopPropagation();

    const container = document.getElementById('screenshot_container');
    if (!container) {
        console.error('Screenshot container not found');
        return;
    }

    // 🔹 Get dynamic filename from QWeb
    const fileName = btn.dataset.filename || 'screenshot.png';

    // Hide button before capture
    btn.style.visibility = 'hidden';

    html2canvas(container, {
        scale: 2,
        useCORS: true,
        backgroundColor: '#ffffff',
        scrollX: 0,
        scrollY: -window.scrollY,
    }).then(canvas => {
        btn.style.visibility = 'visible';

        const link = document.createElement('a');
        link.href = canvas.toDataURL('image/png');
        link.download = fileName;
        link.click();
    });
});
