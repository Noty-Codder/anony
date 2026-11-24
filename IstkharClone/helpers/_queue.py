# Copyright (c) 2025 AnonymousX1025
# Licensed under the MIT License.
# This file is part of AnonXMusic


import random
from collections import defaultdict, deque
from typing import Union

from ._dataclass import Media, Track

MediaItem = Union[Media, Track]


class Queue:
    def __init__(self):
        self.queues: dict[int, deque[MediaItem]] = defaultdict(deque)
        # ids already played per chat (used by autoplay so songs do not repeat)
        self.history: dict[int, deque[str]] = defaultdict(lambda: deque(maxlen=40))

    def add(self, chat_id: int, item: MediaItem) -> int:
        """Add an item to the queue and return its position (1-based)."""
        self.queues[chat_id].append(item)
        return len(self.queues[chat_id]) - 1

    def check_item(self, chat_id: int, item_id: str) -> tuple[int, MediaItem | None]:
        """Check if an item with the given ID exists in the queue."""
        pos, track = next(
            (
                (i, track)
                for i, track in enumerate(list(self.queues[chat_id]))
                if track.id == item_id
            ),
            (-1, None),
        )
        return pos, track

    def force_add(
        self, chat_id: int, item: MediaItem, remove: int | bool = False
    ) -> None:
        """Replace the currently playing item with a new one."""
        self.remove_current(chat_id)
        self.queues[chat_id].appendleft(item)
        if remove:
            self.queues[chat_id].rotate(-remove)
            self.queues[chat_id].popleft()
            self.queues[chat_id].rotate(remove)

    def get_current(self, chat_id: int) -> MediaItem | None:
        """Return the currently playing item (first in queue), if any."""
        return self.queues[chat_id][0] if self.queues[chat_id] else None

    def get_next(self, chat_id: int, check: bool = False) -> MediaItem | None:
        """Remove current item and return the next one, or None if empty."""
        if not self.queues[chat_id]:
            return None
        if check:
            return self.queues[chat_id][1] if len(self.queues[chat_id]) > 1 else None

        self.queues[chat_id].popleft()
        return self.queues[chat_id][0] if self.queues[chat_id] else None

    def get_queue(self, chat_id: int) -> list[MediaItem]:
        """Return the full queue including the currently playing item."""
        return list(self.queues[chat_id])

    def remove_current(self, chat_id: int) -> None:
        """Remove the currently playing item only (if exists)."""
        if self.queues[chat_id]:
            self.queues[chat_id].popleft()

    def clear(self, chat_id: int) -> None:
        """Clear the entire queue."""
        self.queues[chat_id].clear()
        self.history.pop(chat_id, None)

    def shuffle(self, chat_id: int) -> int:
        """Shuffle everything except the playing item; returns shuffled count."""
        q = self.queues[chat_id]
        if len(q) < 3:
            return 0
        current = q.popleft()
        rest = list(q)
        random.shuffle(rest)
        q.clear()
        q.extend(rest)
        q.appendleft(current)
        return len(rest)

    def remove_at(self, chat_id: int, pos: int) -> MediaItem | None:
        """Remove the queued item at ``pos`` (1 = first after the playing one)."""
        q = self.queues[chat_id]
        if pos < 1 or pos >= len(q):
            return None
        q.rotate(-pos)
        item = q.popleft()
        q.rotate(pos)
        return item

    def seen(self, chat_id: int, item_id: str) -> None:
        self.history[chat_id].append(item_id)
