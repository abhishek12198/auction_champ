let last_id = 0;

function fetchAuctionUpdates() {
    const feed = document.getElementById('auction_feed');
    if (!feed) {
        console.warn('auction_feed not found');
        return;
    }

    fetch(`/auction/status/data?last_id=${last_id}`)
        .then(r => r.json())
        .then(data => {
            data.records.forEach(rec => {
                const el = document.createElement('div');
                el.className = 'auction-card';

                el.innerHTML = `
                    <div class="d-flex align-items-center">
                        <img src="${rec.image_url}" class="player-img"/>
                        <div class="ms-3">
                            <p class="mb-0 fw-bold">${rec.message}</p>
                        </div>
                    </div>
                `;

                feed.prepend(el);
                last_id = rec.id;
            });
        });
}

document.addEventListener('DOMContentLoaded', () => {
    fetchAuctionUpdates();
    setInterval(fetchAuctionUpdates, 3000);
});
