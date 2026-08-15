# -*- coding: utf-8 -*-
"""Shared Redis Pub/Sub fan-out per (db, tournament_id).

Many SSE browsers → one Redis SUBSCRIBE per tournament in this process.
"""
import asyncio
import json
import logging

from . import async_redis, metrics

_logger = logging.getLogger(__name__)


class TournamentChannel(object):
    def __init__(self, dbname, tid):
        self.dbname = dbname
        self.tid = int(tid)
        self.channel = async_redis.tid_keys(dbname, tid)['events']
        # kind -> set of asyncio.Queue
        self.subscribers = {'lb': set(), 'pj': set(), 'bal': set()}
        self._task = None
        self._pubsub = None
        self._lock = asyncio.Lock()
        self._buffer = []  # events received before first snapshot drain
        self._started = False

    def client_count(self):
        return sum(len(s) for s in self.subscribers.values())

    async def start(self):
        async with self._lock:
            if self._started:
                return
            client = await async_redis.get_client()
            self._pubsub = client.pubsub()
            await self._pubsub.subscribe(self.channel)
            self._task = asyncio.create_task(self._listen_loop())
            self._started = True
            metrics.sse_gauge('sse_redis_subscriptions', 1)
            _logger.info(
                'sse subscribed db=%s tid=%s channel=%s',
                self.dbname, self.tid, self.channel,
            )

    async def stop(self):
        async with self._lock:
            self._started = False
            if self._task:
                self._task.cancel()
                try:
                    await self._task
                except (asyncio.CancelledError, Exception):
                    pass
                self._task = None
            if self._pubsub is not None:
                try:
                    await self._pubsub.unsubscribe(self.channel)
                    await self._pubsub.aclose()
                except Exception:
                    pass
                self._pubsub = None
            metrics.sse_gauge('sse_redis_subscriptions', -1)

    async def _listen_loop(self):
        try:
            async for message in self._pubsub.listen():
                if not self._started:
                    break
                if message is None:
                    continue
                if message.get('type') != 'message':
                    continue
                data = message.get('data')
                try:
                    if isinstance(data, bytes):
                        data = data.decode('utf-8')
                    event = json.loads(data)
                except Exception:
                    metrics.incr_sse('sse_redis_errors')
                    continue
                await self._fanout(event)
        except asyncio.CancelledError:
            raise
        except Exception as err:
            _logger.warning('sse listen loop ended: %s', err)
            metrics.incr_sse('sse_redis_errors')
            # Wake subscribers so they can close / fallback
            await self._fanout({'_error': 'redis', 'targets': ['lb', 'pj', 'bal']})

    async def _fanout(self, event):
        targets = event.get('targets') or []
        if event.get('_error'):
            targets = ['lb', 'pj', 'bal']
        for kind in targets:
            queues = list(self.subscribers.get(kind) or ())
            for q in queues:
                try:
                    q.put_nowait(event)
                except asyncio.QueueFull:
                    # Drop oldest then push
                    try:
                        q.get_nowait()
                    except Exception:
                        pass
                    try:
                        q.put_nowait(event)
                    except Exception:
                        pass

    async def join(self, kind):
        if kind not in self.subscribers:
            raise ValueError('bad kind')
        await self.start()
        q = asyncio.Queue(maxsize=32)
        self.subscribers[kind].add(q)
        metrics.incr_sse('sse_connections_total')
        metrics.sse_gauge('sse_connections_current', 1)
        return q

    async def leave(self, kind, q):
        bucket = self.subscribers.get(kind)
        if bucket is not None and q in bucket:
            bucket.discard(q)
            metrics.sse_gauge('sse_connections_current', -1)
            metrics.incr_sse('sse_disconnects')
        if self.client_count() == 0:
            await self.stop()


class ChannelManager(object):
    def __init__(self):
        self._channels = {}
        self._lock = asyncio.Lock()

    def _key(self, dbname, tid):
        return '%s:%s' % (dbname, int(tid))

    async def join(self, dbname, tid, kind):
        key = self._key(dbname, tid)
        async with self._lock:
            ch = self._channels.get(key)
            if ch is None:
                ch = TournamentChannel(dbname, tid)
                self._channels[key] = ch
        q = await ch.join(kind)
        return ch, q

    async def leave(self, dbname, tid, kind, q):
        key = self._key(dbname, tid)
        ch = self._channels.get(key)
        if not ch:
            return
        await ch.leave(kind, q)
        async with self._lock:
            if ch.client_count() == 0 and self._channels.get(key) is ch:
                self._channels.pop(key, None)


manager = ChannelManager()
