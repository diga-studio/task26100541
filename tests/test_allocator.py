import pytest

from venue_booking import BUFFER_SECONDS, BookingRequest, Slot, VenueAllocator


def req(request_id, *slots, space="hall"):
    return BookingRequest(
        request_id=request_id,
        space=space,
        slots=tuple(Slot(start, end) for start, end in slots),
    )


def test_partial_group_waits_but_does_not_block_later_request():
    allocator = VenueAllocator()
    allocator.submit(req("occupant", (0, 3600)))

    # Needs two slots; the first conflicts, so the whole group waits.
    allocator.submit(req("group", (1800, 3600), (7200, 10800)))
    # Later request only needs the free slot and must be accepted.
    allocator.submit(req("single", (7200, 10800)))

    snap = allocator.snapshot()
    assert set(snap.allocated) == {"occupant", "single"}
    assert snap.waitlist == ("group",)


def test_batch_release_promotes_earliest_whole_group_regardless_of_id_order():
    def run(withdraw_order):
        allocator = VenueAllocator()
        allocator.submit(req("hold-a", (0, 3600)))
        allocator.submit(req("hold-b", (7200, 10800)))
        allocator.submit(req("group", (0, 3600), (7200, 10800)))
        allocator.submit(req("first-half", (0, 3600)))
        allocator.submit(req("second-half", (7200, 10800)))
        assert set(allocator.snapshot().allocated) == {"hold-a", "hold-b"}

        allocator.withdraw(withdraw_order)
        return allocator.snapshot()

    snap_ab = run(["hold-a", "hold-b"])
    snap_ba = run(["hold-b", "hold-a"])

    for snap in (snap_ab, snap_ba):
        assert set(snap.allocated) == {"group"}
        assert snap.waitlist == ("first-half", "second-half")
    assert snap_ab.allocated == snap_ba.allocated
    assert snap_ab.waitlist == snap_ba.waitlist


def test_buffer_period_blocks_but_exact_endpoint_is_free():
    allocator = VenueAllocator()
    allocator.submit(req("occupant", (0, 3600)))

    # Starts inside the 30-minute buffer: rejected to the waitlist.
    allocator.submit(req("too-early", (3600 + BUFFER_SECONDS - 1, 7200)))
    # Starts exactly when the buffer ends: acceptable.
    allocator.submit(req("exact", (3600 + BUFFER_SECONDS, 7200)))

    snap = allocator.snapshot()
    assert set(snap.allocated) == {"occupant", "exact"}
    assert snap.waitlist == ("too-early",)


def test_withdraw_releases_and_promotes_in_original_order():
    allocator = VenueAllocator()
    allocator.submit(req("occupant", (0, 3600)))
    allocator.submit(req("waiter", (0, 3600)))

    allocator.withdraw(["occupant"])

    snap = allocator.snapshot()
    assert set(snap.allocated) == {"waiter"}
    assert snap.waitlist == ()


def test_withdraw_removes_waitlisted_request_and_ignores_unknown_ids():
    allocator = VenueAllocator()
    allocator.submit(req("occupant", (0, 3600)))
    allocator.submit(req("waiter", (0, 3600)))

    allocator.withdraw(["waiter", "no-such-id"])

    snap = allocator.snapshot()
    assert set(snap.allocated) == {"occupant"}
    assert snap.waitlist == ()


def test_spaces_are_independent():
    allocator = VenueAllocator()
    allocator.submit(req("a", (0, 3600), space="hall-1"))
    allocator.submit(req("b", (0, 3600), space="hall-2"))

    snap = allocator.snapshot()
    assert set(snap.allocated) == {"a", "b"}
    assert snap.waitlist == ()


def test_new_submission_cannot_overtake_acceptable_earlier_waiter():
    allocator = VenueAllocator()
    allocator.submit(req("occupant", (0, 3600)))
    allocator.submit(req("waiter", (0, 3600)))
    # Freeing the slot must promote the earlier waiter, and a request
    # submitted afterwards must not jump ahead of it.
    allocator.withdraw(["occupant"])
    allocator.submit(req("latecomer", (0, 3600)))

    snap = allocator.snapshot()
    assert set(snap.allocated) == {"waiter"}
    assert snap.waitlist == ("latecomer",)


def test_duplicate_request_id_rejected():
    allocator = VenueAllocator()
    allocator.submit(req("dup", (0, 3600)))
    with pytest.raises(ValueError):
        allocator.submit(req("dup", (7200, 10800)))
