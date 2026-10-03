"""候补分配库的自动化测试。"""

import pytest

from booking import BookingAllocator

BUFFER = 30 * 60


def make_allocator() -> BookingAllocator:
    return BookingAllocator()


class TestGroupBlocking:
    """较早的整组请求等待时，不阻塞更晚的可接纳请求。"""

    def test_earlier_group_waits_but_later_single_accepted(self):
        allocator = make_allocator()
        # 占用时段二，使整组请求无法完整接纳。
        allocator.submit("blocker", "hall", [(5000, 6000)])
        # 较早请求需要两个时段，只有时段一空闲 -> 整组等待。
        allocator.submit("group", "hall", [(0, 1000), (5000, 6000)])
        # 较晚请求只需要空闲的时段一 -> 应获得占用。
        allocator.submit("single", "hall", [(0, 1000)])

        snap = allocator.snapshot()
        assert set(snap.allocated) == {"blocker", "single"}
        assert snap.waitlisted == ["group"]

    def test_group_promoted_when_all_slots_free(self):
        allocator = make_allocator()
        allocator.submit("blocker", "hall", [(5000, 6000)])
        allocator.submit("group", "hall", [(0, 1000), (5000, 6000)])
        # 较晚请求使用与整组请求无关的空闲时段。
        allocator.submit("single", "hall", [(9000, 9500)])

        # 释放时段二后，整组请求立即递补（single 不冲突，保留）。
        allocator.withdraw(["blocker"])
        snap = allocator.snapshot()
        assert set(snap.allocated) == {"group", "single"}
        assert snap.waitlisted == []


class TestBatchWithdraw:
    """成批撤回：整批先生效再递补，批次内顺序不影响结果。"""

    def build_scenario(self) -> BookingAllocator:
        allocator = make_allocator()
        allocator.submit("hold-1", "hall", [(0, 1000)])
        allocator.submit("hold-2", "hall", [(5000, 6000)])
        # 最早的整组请求，需要两个时段。
        allocator.submit("group", "hall", [(0, 1000), (5000, 6000)])
        # 较晚的两个单时段请求。
        allocator.submit("late-1", "hall", [(0, 1000)])
        allocator.submit("late-2", "hall", [(5000, 6000)])
        assert allocator.snapshot().waitlisted == ["group", "late-1", "late-2"]
        return allocator

    def test_group_wins_over_later_singles(self):
        allocator = self.build_scenario()
        allocator.withdraw(["hold-1", "hold-2"])
        snap = allocator.snapshot()
        assert set(snap.allocated) == {"group"}
        assert snap.waitlisted == ["late-1", "late-2"]

    def test_withdraw_order_irrelevant(self):
        allocator_a = self.build_scenario()
        allocator_a.withdraw(["hold-1", "hold-2"])
        allocator_b = self.build_scenario()
        allocator_b.withdraw(["hold-2", "hold-1"])

        snap_a = allocator_a.snapshot()
        snap_b = allocator_b.snapshot()
        assert set(snap_a.allocated) == set(snap_b.allocated)
        assert snap_a.waitlisted == snap_b.waitlisted

    def test_batch_can_mix_allocated_and_waitlisted(self):
        allocator = self.build_scenario()
        # 同批撤回一个已分配请求和一个候补请求。
        allocator.withdraw(["hold-1", "late-2"])
        snap = allocator.snapshot()
        # group 仍缺时段二，继续等待；late-1 获得时段一。
        assert set(snap.allocated) == {"hold-2", "late-1"}
        assert snap.waitlisted == ["group"]

    def test_unknown_ids_ignored(self):
        allocator = make_allocator()
        allocator.submit("r1", "hall", [(0, 1000)])
        allocator.withdraw(["nope", "r1"])
        assert set(allocator.snapshot().allocated) == set()


class TestBufferRule:
    """时段结束后额外占用 30 分钟，最终结束点本身不占用。"""

    def test_exactly_30_minutes_after_end_is_accepted(self):
        allocator = make_allocator()
        allocator.submit("first", "hall", [(0, 1000)])
        # 前一活动结束后恰好 30 分钟开始 -> 可接纳。
        allocator.submit("second", "hall", [(1000 + BUFFER, 5000)])
        assert set(allocator.snapshot().allocated) == {"first", "second"}

    def test_one_second_before_buffer_end_conflicts(self):
        allocator = make_allocator()
        allocator.submit("first", "hall", [(0, 1000)])
        allocator.submit("too-early", "hall", [(1000 + BUFFER - 1, 5000)])
        snap = allocator.snapshot()
        assert set(snap.allocated) == {"first"}
        assert snap.waitlisted == ["too-early"]

    def test_touching_intervals_do_not_conflict(self):
        allocator = make_allocator()
        allocator.submit("a", "hall", [(0, 1000)])
        # [0,2800) 与 [2800,5000) 半开区间不相交。
        allocator.submit("b", "hall", [(1000 + BUFFER, 5000)])
        allocator.submit("c", "hall", [(5000 + BUFFER, 9000)])
        assert set(allocator.snapshot().allocated) == {"a", "b", "c"}


class TestSpaceIsolation:
    def test_different_spaces_do_not_interfere(self):
        allocator = make_allocator()
        allocator.submit("a", "hall-1", [(0, 1000)])
        allocator.submit("b", "hall-2", [(0, 1000)])
        assert set(allocator.snapshot().allocated) == {"a", "b"}


class TestFairness:
    def test_no_partial_success(self):
        allocator = make_allocator()
        allocator.submit("blocker", "hall", [(5000, 6000)])
        allocator.submit("group", "hall", [(0, 1000), (5000, 6000)])
        # 整组等待，时段一也不被该请求占用。
        allocator.submit("other", "hall", [(0, 1000)])
        assert set(allocator.snapshot().allocated) == {"blocker", "other"}

    def test_new_submit_cannot_overtake_acceptable_waiter(self):
        allocator = make_allocator()
        allocator.submit("blocker", "hall", [(0, 1000)])
        allocator.submit("waiter", "hall", [(0, 1000)])
        # 释放后 waiter 立即递补；新提交只能在剩余空隙中判断。
        allocator.withdraw(["blocker"])
        allocator.submit("newcomer", "hall", [(0, 1000)])
        snap = allocator.snapshot()
        assert set(snap.allocated) == {"waiter"}
        assert snap.waitlisted == ["newcomer"]

    def test_allocation_never_revoked(self):
        allocator = make_allocator()
        allocator.submit("mine", "hall", [(0, 1000)])
        # 后来的整组请求即使只差一个时段，也不能收回 mine 的占用。
        allocator.submit("greedy", "hall", [(0, 1000), (5000, 6000)])
        snap = allocator.snapshot()
        assert set(snap.allocated) == {"mine"}
        assert snap.waitlisted == ["greedy"]

    def test_waitlist_order_preserved(self):
        allocator = make_allocator()
        allocator.submit("blocker", "hall", [(0, 10000)])
        allocator.submit("w1", "hall", [(0, 1000)])
        allocator.submit("w2", "hall", [(2000, 3000)])
        allocator.submit("w3", "hall", [(4000, 5000)])
        assert allocator.snapshot().waitlisted == ["w1", "w2", "w3"]


class TestValidation:
    def test_duplicate_request_id_rejected(self):
        allocator = make_allocator()
        allocator.submit("r1", "hall", [(0, 1000)])
        with pytest.raises(ValueError):
            allocator.submit("r1", "hall", [(2000, 3000)])

    def test_empty_slots_rejected(self):
        allocator = make_allocator()
        with pytest.raises(ValueError):
            allocator.submit("r1", "hall", [])

    def test_invalid_slot_rejected(self):
        allocator = make_allocator()
        with pytest.raises(ValueError):
            allocator.submit("r1", "hall", [(1000, 1000)])
