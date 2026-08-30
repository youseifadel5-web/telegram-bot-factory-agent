# -*- coding: utf-8 -*-
"""Lightweight per-user rate limiting."""
from __future__ import annotations

import time
from collections import defaultdict, deque
from typing import Deque, Dict


class RateLimiter:
    def __init__(self, max_calls=20, window_sec=60.0):
        self.max_calls = max_calls
        self.window = float(window_sec)
        self._hits = defaultdict(deque)  # type: Dict[int, Deque[float]]

    def allow(self, user_id):
        now = time.time()
        q = self._hits[user_id]
        while q and now - q[0] > self.window:
            q.popleft()
        if len(q) >= self.max_calls:
            return False
        q.append(now)
        return True


def get_callback_limiter():
    global _cb
    try:
        return _cb
    except NameError:
        _cb = RateLimiter(40, 60.0)
        return _cb


def get_message_limiter():
    global _msg
    try:
        return _msg
    except NameError:
        _msg = RateLimiter(25, 60.0)
        return _msg


callback_limiter = None
message_limiter = None

def _init():
    global callback_limiter, message_limiter
    callback_limiter = RateLimiter(40, 60.0)
    message_limiter = RateLimiter(25, 60.0)

_init()
