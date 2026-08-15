# AuctionChamp — Phase 2B/3 Redis Live Gateway

Lightweight FastAPI service that serves Live Board / Projector / Bid Summary
JSON **directly from Redis**, plus Phase 3 **SSE** over Redis Pub/Sub.
Odoo is not imported. PostgreSQL is not used.

```
Browser → Nginx → Gateway (127.0.0.1:8090) → Redis GET / PUBSUB
                   ↘ /data 404/503 → Nginx → Odoo (poll fallback)
```

## Install

```bash
cd /home/abhishek/PycharmProjects/auction_champ/auction_live_gateway
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
```

## Run (foreground)

Prefer **one uvicorn worker** so SSE fan-out stays in-process:

```bash
export AUCTION_REDIS_URL=redis://127.0.0.1:6379/1
./venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8090 --workers 1 --log-level warning
```

## Health

```bash
curl -sS http://127.0.0.1:8090/health
curl -sS http://127.0.0.1:8090/ready
```

## Prerequisites (Odoo / Redis)

1. Phase 2A snapshots: `auction.redis.enabled = True`
2. Seq `0` is a valid HIT
3. Slug map + meta flags populated
4. Phase 3.0+: live-board payload includes bid fields; BID dirties `lb,pj`

## Poll routes (`/data`)

Same as Phase 2B. Live Board Option A meta:

- `live_board_active=0` → `{"live_board_active": false}` (200)
- `code_protected=1` → **404** (Nginx → Odoo unlock)
- Unprotected + active → Redis HIT

## SSE routes (`/events`) — Phase 3

```
GET /{db}/{slug}/auction/live-board/events
GET /{db}/auction/projector/{slug}/events
GET /{db}/{slug}/auction/show/team/balance/events
```

Behaviour:

1. Resolve slug → tid; Option A for live-board
2. SUBSCRIBE `ac:{db}:t:{tid}:events` (shared per tournament in-process)
3. Send `event: snapshot` with current Redis payload
4. On Pub/Sub message whose `targets` include this kind, re-GET snapshot → `event: auction.update`
5. Heartbeat comment every ~15s

Projector SSE sends **raw `:pj` JSON** (not JSON-RPC). Clients apply it like `json.result`.

Frontend only opens `EventSource` when `auction.sse.enabled = True` (default False).
Polling code stays as fallback.

## Tests

```bash
cd auction_live_gateway
./venv/bin/python -m unittest discover -s tests -v
```

## systemd (do not enable until reviewed)

```bash
sudo cp deploy/auction-redis-gateway.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now auction-redis-gateway
```

Unit defaults: `--workers 1`, `MemoryMax=512M`. Raise MemoryMax before large SSE load tests.

## Nginx (do not apply until gateway tests pass)

See `deploy/nginx-auction-live-gateway.snippet.conf`.

1. Add `upstream auction_live_gateway`
2. Paste **poll** + **SSE** `location` blocks **before** `location /`
3. SSE locations: `proxy_buffering off`, long `proxy_read_timeout`
4. `sudo nginx -t && sudo systemctl reload nginx`

### Rollback

- Comment out gateway `location` blocks → reload Nginx (poll + SSE)
- Or only remove `/events` locations and set `auction.sse.enabled = False`
- Optionally: `sudo systemctl stop auction-redis-gateway`

Browser → Odoo again. `auction.redis.enabled = False` still uses ORM when hitting Odoo.

## Load tests

```bash
GW_PY=./auction_live_gateway/venv/bin/python

# Poll (Phase 2B)
$GW_PY scripts/load_test_live_polls.py --run --viewers 100 --duration 10 \
  --base http://127.0.0.1:8090 --db main_db_1 --slug jas-cricket-league

# SSE (Phase 3)
$GW_PY scripts/load_test_sse.py --run --viewers 50 --duration 20 \
  --base http://127.0.0.1:8090 --db main_db_1 --slug jas-cricket-league --kind lb
```

Do **not** publish a supported viewer count from localhost alone.

## Enable SSE on a database

```python
env['ir.config_parameter'].sudo().set_param('auction.sse.enabled', 'True')
env.cr.commit()
```

Upgrade `-u auction_module` so templates pass `sse_enabled` and assets load.
If `auction.sse.enabled` is missing (noupdate), create it once as above.
