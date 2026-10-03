"""In-memory venue booking waitlist allocator.

The upper-level booking flow submits requests, withdraws them in batches
(expired holds and cancellations alike), and reads the current allocation.
All state lives in the process; there is no persistence.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

#: Each slot occupies its space until 30 minutes after it ends.
#: The final endpoint itself is not occupied (half-open intervals).
BUFFER_SECONDS = 30 * 60


@dataclass(frozen=True)
class Slot:
    """A single time slot in absolute seconds."""

    start: int
    end: int

    def __post_init__(self) -> None:
        if self.end <= self.start:
            raise ValueError("slot end must be after start")

    @property
    def occupied_until(self) -> int:
        """End of the occupied interval (exclusive), buffer included."""
        return self.end + BUFFER_SECONDS


@dataclass(frozen=True)
class BookingRequest:
    """One booking request: a single space plus one or more slots.

    Slots within a request are guaranteed non-conflicting by the caller.
    A request is either allocated as a whole or waitlisted as a whole.
    """

    request_id: str
    space: str
    slots: tuple[Slot, ...]

    def __post_init__(self) -> None:
        if not self.slots:
            raise ValueError("a request must contain at least one slot")


@dataclass(frozen=True)
class AllocationSnapshot:
    """Current allocation state."""

    allocated: dict[str, BookingRequest]
    waitlist: tuple[str, ...]


class VenueAllocator:
    """Allocates requests to spaces, promoting the waitlist in order."""

    def __init__(self) -> None:
        self._allocated: dict[str, BookingRequest] = {}
        self._waitlist: list[BookingRequest] = []
        self._known_ids: set[str] = set()

    def submit(self, request: BookingRequest) -> None:
        """Submit a request; it is allocated immediately if fully free."""
        if request.request_id in self._known_ids:
            raise ValueError(f"duplicate request id: {request.request_id}")
        self._known_ids.add(request.request_id)
        self._waitlist.append(request)
        self._promote()

    def withdraw(self, request_ids: Iterable[str]) -> None:
        """Withdraw a batch of allocated and/or waitlisted requests."""
        # The whole batch takes effect before any promotion happens,
        # so the order of ids within the batch cannot affect the result.
        ids = set(request_ids)
        for request_id in ids:
            self._allocated.pop(request_id, None)
        if ids:
            self._waitlist = [
                req for req in self._waitlist if req.request_id not in ids
            ]
            self._known_ids -= ids
        self._promote()

    def snapshot(self) -> AllocationSnapshot:
        """Return the current allocation and waitlist order."""
        return AllocationSnapshot(
            allocated=dict(self._allocated),
            waitlist=tuple(req.request_id for req in self._waitlist),
        )

    def _promote(self) -> None:
        """Scan the waitlist in submission order, accepting what fits.

        A request is accepted only if every one of its slots is free
        against the current allocations (including requests accepted
        earlier in this same scan); otherwise it is skipped and the
        scan continues with later requests.
        """
        remaining: list[BookingRequest] = []
        for request in self._waitlist:
            if self._fits(request):
                self._allocated[request.request_id] = request
            else:
                remaining.append(request)
        self._waitlist = remaining

    def _fits(self, request: BookingRequest) -> bool:
        for other in self._allocated.values():
            if other.space != request.space:
                continue
            for slot in request.slots:
                for existing in other.slots:
                    if (
                        slot.start < existing.occupied_until
                        and existing.start < slot.occupied_until
                    ):
                        return False
        return True
