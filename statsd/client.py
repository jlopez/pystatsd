from __future__ import with_statement
from functools import wraps
import random
import socket
import time


class _Timer(object):
    """A context manager/decorator for statsd.timing()."""

    def __init__(self, client, stat, rate=1):
        self.client = client
        self.stat = stat
        self.rate = rate
        self.ms = None

    def __call__(self, f):
        @wraps(f)
        def wrapper(*args, **kw):
            with self:
                return f(*args, **kw)
        return wrapper

    def __enter__(self):
        self.start = time.time()
        return self

    def __exit__(self, typ, value, tb):
        dt = time.time() - self.start
        self.ms = int(round(1000 * dt))  # Convert to ms.
        self.client.timing(self.stat, self.ms, self.rate)


class StatsClient(object):
    """A client for statsd."""

    def __init__(self, host='localhost', port=8125, prefix=None, batch_len=1,
                 thread_safe=False, debug=False):
        """Create a new client."""
        self._addr = host and (socket.gethostbyname(host), port)
        self._sock = host and socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._prefix = prefix
        self._batch_len = batch_len
        self._stats = []
        self._debug = debug

        if thread_safe:
            import threading
        else:
            import dummy_threading as threading
        self._lock = threading.Lock()

    def timer(self, stat, rate=1):
        return _Timer(self, stat, rate)

    def timing(self, stat, delta, rate=1):
        """Send new timing information. `delta` is in milliseconds."""
        self._send(stat, '%d|ms' % delta, rate)

    def incr(self, stat, count=1, rate=1):
        """Increment a stat by `count`."""
        self._send(stat, '%s|c' % count, rate)

    def decr(self, stat, count=1, rate=1):
        """Decrement a stat by `count`."""
        self.incr(stat, -count, rate)

    def gauge(self, stat, value, rate=1):
        """Set a gauge value."""
        self._send(stat, '%s|g' % value, rate)

    def flush(self, force=True):
        """Flush the stats batching buffer."""
        with self._lock:
            data = None
            if self._stats and (force or len(self._stats) >= self._batch_len):
                data = '\n'.join(self._stats)
                self._stats = []
        if data:
            self._transmit(data)

    def _transmit(self, data):
        """Send an encoded event string over the network"""
        if self._debug:
            print data
        if self._sock:
            try:
                self._sock.sendto(data.encode('ascii'), self._addr)
            except socket.error:
                # No time for love, Dr. Jones!
                pass

    def _send(self, stat, value, rate=1):
        """Send data to statsd."""
        if rate < 1:
            if random.random() < rate:
                value = '%s|@%s' % (value, rate)
            else:
                return

        if self._prefix:
            stat = '%s.%s' % (self._prefix, stat)

        txt = '%s:%s' % (stat, value)

        if self._batch_len <= 1:
            # Optimization - Skip buffer and transmit immediately
            self._transmit(txt)
        else:
            self._stats.append(txt)
            self.flush(force=False)
