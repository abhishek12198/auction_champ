# Auction Champ — Phase 2A Redis snapshots

PostgreSQL is the **authoritative** live-auction store. Redis is an optional
**shared replica** of the three public poll payloads (Live Board, Projector,
Bid Summary). If Redis is disabled, missing, or down, auctions continue on
the existing ORM polling path.

The process-local `_LIVE_PAYLOAD_CACHE` is only a tertiary shortcut on one
Odoo worker. It cannot be correct across workers, after a mutation on another
process, or after a worker restart. Redis is the shared cache; PostgreSQL
`live_snapshot_seq` is the version authority. Never use Redis `INCR` as the
sequence.

Stamp expiry is **not** a Redis rebuild. Snapshots embed `stamp_expires_at`;
clients (or the next mutation) handle the transition. Do not schedule Redis
writes on a timer.

## Redis keys (multi-database safe)

```
ac:{dbname}:t:{tid}:lb
ac:{dbname}:t:{tid}:pj
ac:{dbname}:t:{tid}:bal
ac:{dbname}:t:{tid}:meta
ac:{dbname}:t:{tid}:seq
ac:{dbname}:t:{tid}:rebuild_lock
```

## Odoo settings (`ir.config_parameter`)

```
auction.redis.enabled = True
auction.redis.uri = redis://127.0.0.1:6379/1
```

Unix socket:

```
auction.redis.uri = unix:///var/run/redis/redis.sock?db=1
```

## Install Python client (optional)

```bash
sudo pip3 install redis
# or, in the Odoo venv:
pip install redis
```

Do **not** add `redis` to `external_dependencies` — the module must install
and run when the package is absent.

## Local Redis on Ubuntu

```bash
sudo apt-get update
sudo apt-get install -y redis-server
sudo systemctl enable --now redis-server
```

Recommended `/etc/redis/redis.conf` (do not apply automatically):

```
bind 127.0.0.1
maxmemory 256mb
maxmemory-policy noeviction
appendfsync everysec
# use database 1 from the URI (.../1)
```

```bash
redis-cli ping
redis-cli -n 1 keys 'ac:*'
```

## Enable after module upgrade

```bash
# Upgrade auction_module so live_snapshot_seq exists
./odoo-bin -c odoo.conf -d YOUR_DB -u auction_module --stop-after-init

# Enable Redis (Settings → Technical → System Parameters, or):
./odoo-bin shell -c odoo.conf -d YOUR_DB <<'PY'
env['ir.config_parameter'].sudo().set_param('auction.redis.enabled', 'True')
env['ir.config_parameter'].sudo().set_param('auction.redis.uri', 'redis://127.0.0.1:6379/1')
env.cr.commit()
PY
```

Restart Odoo workers after enabling.

## Rollback (ORM polling only)

```
auction.redis.enabled = False
```

Or:

```bash
./odoo-bin shell -c odoo.conf -d YOUR_DB <<'PY'
env['ir.config_parameter'].sudo().set_param('auction.redis.enabled', 'False')
env.cr.commit()
PY
```

No need to uninstall Redis or revert the `live_snapshot_seq` column. Poll
URLs and frontend intervals are unchanged.

## Failure behaviour

- SOLD / UNSOLD / BID / NEXT / DICE / BREAK / RECALL always commit in PostgreSQL.
- Postcommit Redis errors are logged only.
- Redis restart: next poll acquires a short rebuild lock and rebuilds from PostgreSQL.

## Phase 3 — Pub/Sub + SSE (optional)

After a successful Redis CAS write, Odoo PUBLISHes a small invalidation message:

```
ac:{dbname}:t:{tid}:events
{"event":"auction.update","db":"...","tournament_id":N,"seq":N,"targets":["lb","pj"],"ts":"..."}
```

Gateway SSE endpoints (same process as `/data`):

```
GET /{db}/{slug}/auction/live-board/events
GET /{db}/auction/projector/{slug}/events
GET /{db}/{slug}/auction/show/team/balance/events
```

Frontend flag (default False; polling remains):

```
auction.sse.enabled = True
```

`noupdate=1` — existing DBs may need a one-shot create if the parameter is missing:

```python
ICP = env['ir.config_parameter'].sudo()
if not ICP.get_param('auction.sse.enabled'):
    ICP.set_param('auction.sse.enabled', 'False')
env.cr.commit()
```

Rollback SSE without touching Redis snapshots: set `auction.sse.enabled = False`
(and/or remove Nginx `/events` locations). Poll path is unchanged.
