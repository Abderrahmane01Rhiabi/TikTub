#!/usr/bin/env python3
"""
Render slot - one heavy video render at a time in the whole app.

The machine (WSL) has ~7.8 GB: two final Adaptation renders at once were
killed by the system at 4.5 GB, and a preview, a Montage auto or a
Génération render running beside one could do the same. Every heavy
ffmpeg render takes this slot; the others wait their turn. Not reentrant:
a render must never call another one while holding it.
"""

import threading

SLOT = threading.BoundedSemaphore(1)
