import pytest

from app.greenwave import (
    compute_windows,
    departure_windows_for_intersection,
    eroded_green_intervals,
    intersect_interval_lists,
    local_green_intervals,
    merge_intervals,
)


def it(name=None, **kw):
    # 默认 green_start == green_end 表示整周期常绿，所有取值均满足 schema 约束。
    return {"cycle": 60, "offset": 0, "green_start": 0, "green_end": 0, "travel": 0, **kw}


# ---------- 本地绿灯展开 ----------

def test_local_green_normal():
    assert local_green_intervals(60, 10, 30) == [[10, 30]]


def test_local_green_wrapping():
    assert local_green_intervals(60, 50, 10) == [[50, 60], [0, 10]]


def test_local_green_full_cycle():
    assert local_green_intervals(60, 20, 20) == [[0, 60]]


def test_merge_adjacent_half_open_intervals():
    assert merge_intervals([[0, 10], [10, 20]]) == [[0, 20]]
    assert merge_intervals([[5, 9], [0, 3], [3, 5]]) == [[0, 9]]
    assert merge_intervals([[0, 5], [6, 7]]) == [[0, 5], [6, 7]]


def test_intersection_basic():
    assert intersect_interval_lists([[0, 100]], [[20, 50], [60, 80]]) == [
        [20, 50],
        [60, 80],
    ]
    assert intersect_interval_lists([[0, 5]], [[5, 10]]) == []


# ---------- 单路口周期展开 ----------

def test_single_plain_window_clipped():
    # 全周期常绿：整个发车范围都可行
    got = departure_windows_for_intersection(60, 0, 0, 60, 0, 0, 600)
    assert got == [[0, 600]]


def test_single_periodic_green_and_offset():
    # [20,40) 绿灯，无偏移：在 [0,180) 内应出现 3 段
    got = departure_windows_for_intersection(60, 0, 20, 40, 0, 0, 180)
    assert got == [[20, 40], [80, 100], [140, 160]]


def test_offset_shifts_departure_window():
    # 偏移 10：本地相位 (t+10)%60 ∈ [20,40) ⇔ t%60 ∈ [10,30)
    got = departure_windows_for_intersection(60, 10, 20, 40, 0, 0, 120)
    assert got == [[10, 30], [70, 90]]


def test_travel_time_shifts_departure_window():
    # 行驶 15：t+15 落在 [20,40) ⇔ t ∈ [5,25)
    got = departure_windows_for_intersection(60, 0, 20, 40, 15, 0, 60)
    assert got == [[5, 25]]


def test_wrapping_green_unwrapped_across_boundary():
    # 绿灯 [50,60)∪[0,10)，行驶 0：可行段 [-10,10) 周期 60，裁剪到 [0,130)
    got = departure_windows_for_intersection(60, 0, 50, 10, 0, 0, 130)
    assert got == [[0, 10], [50, 70], [110, 130]]


def test_wrapping_green_with_travel():
    # 行驶 5：到达相位 (t+5)%60 ∈ [50,10)（绕零点）
    # 出发段：[-15,5) 周期 60，裁剪到 [0,125)
    got = departure_windows_for_intersection(60, 0, 50, 10, 5, 0, 125)
    assert got == [[0, 5], [45, 65], [105, 125]]


def test_range_starts_mid_cycle():
    got = departure_windows_for_intersection(60, 0, 0, 30, 0, 75, 150)
    # [0,30) 周期 60：[60,90) 裁剪为 [75,90)，另有 [120,150)
    assert got == [[75, 90], [120, 150]]


def test_green_equal_to_range_boundary_yields_empty():
    # 可行段恰好在发车范围起点“之后才开始”的反例：范围 [40,80)，绿灯 [20,40)
    got = departure_windows_for_intersection(60, 0, 20, 40, 0, 40, 80)
    assert got == []  # [20,40) 与范围无交；下一段 [80,100) 也无交


# ---------- 行驶时间波动（travel_max） ----------

def test_eroded_green_normal():
    # 普通绿灯 [10, 30) 收缩入口端 5 秒
    assert eroded_green_intervals(60, 10, 30, 5) == [[10, 25]]
    assert eroded_green_intervals(60, 10, 30, 0) == [[10, 30]]
    # 收缩量等于绿灯长度：任何非零抵达弧都放不进半开绿灯
    assert eroded_green_intervals(60, 10, 30, 20) == []
    assert eroded_green_intervals(60, 10, 30, 21) == []


def test_eroded_green_full_cycle_unaffected():
    # 整周期常绿不受任何波动量影响
    assert eroded_green_intervals(60, 0, 0, 59) == [[0, 60]]
    assert eroded_green_intervals(60, 20, 20, 86400) == [[0, 60]]


def test_eroded_green_wrapping_treated_as_continuous_arc():
    # 跨零点 [50,60)∪[0,10) 视为连续弧 [50,70) 再收缩：
    # slack=5 后 [50,65) 映射回 [50,60)∪[0,5)，仍是跨零点两段
    assert eroded_green_intervals(60, 50, 10, 5) == [[50, 60], [0, 5]]
    # slack=15 后 [50,55) 收缩成不跨零点的一段
    assert eroded_green_intervals(60, 50, 10, 15) == [[50, 55]]
    # slack=20 恰好退化为空（半开端点 50 不含）
    assert eroded_green_intervals(60, 50, 10, 20) == []
    assert eroded_green_intervals(60, 50, 10, 21) == []


def test_slack_shrinks_departure_window():
    # 绿灯 [20,40) 长 20 秒，行驶 T=15、波动 5：只剩收缩绿灯 [20,35)
    # 对应出发区间 [5,20)
    got = departure_windows_for_intersection(60, 0, 20, 40, 15, 0, 60, slack=5)
    assert got == [[5, 20]]


def test_slack_equal_green_length_yields_empty():
    # 波动量等于绿灯长度：无法保证抵达弧整体遇绿
    got = departure_windows_for_intersection(60, 0, 20, 40, 0, 0, 120, slack=20)
    assert got == []


def test_full_cycle_green_immune_to_slack():
    # 常绿（green_start == green_end）：即使波动 120 秒（超过周期），整个发车范围仍可行
    got = departure_windows_for_intersection(60, 0, 0, 0, 0, 0, 600, slack=120)
    assert got == [[0, 600]]


def test_wrapping_green_continuous_shrink_departure():
    # 跨零点绿灯 [50,10)，行驶 5 秒、波动 5 秒：
    # 连续弧收缩后为 [50,60)∪[0,5)，按 shift=5 平移到出发轴并裁剪 [0,125)
    got = departure_windows_for_intersection(60, 0, 50, 10, 5, 0, 125, slack=5)
    # [45,55) 与 [55,60) 端点相接，合并为 [45,60)
    assert got == [[45, 60], [105, 120]]


def test_compute_windows_with_travel_max():
    # 路口 1：绿灯 [0,30)、行驶 0..5，收缩为 [0,25)
    # 路口 2：常绿、行驶 30..40，不受波动影响，offset=30 补偿 30 秒基准行程
    nodes = [
        it(cycle=60, offset=0, green_start=0, green_end=30, travel=0, travel_max=5),
        it(cycle=60, offset=30, green_start=0, green_end=0, travel=30, travel_max=40),
    ]
    assert compute_windows(nodes, 0, 300) == [
        [0, 25], [60, 85], [120, 145], [180, 205], [240, 265],
    ]


def test_travel_max_defaults_to_travel():
    # 省略 travel_max 与显式 travel_max == travel 等价
    nodes = [it(cycle=60, green_start=0, green_end=30, travel=0)]
    nodes_max = [
        it(cycle=60, green_start=0, green_end=30, travel=0, travel_max=0)
    ]
    assert compute_windows(nodes, 0, 120) == compute_windows(nodes_max, 0, 120)
    assert compute_windows(nodes, 0, 120) == [[0, 30], [60, 90]]


# ---------- 多路口联动（端到端，含暴力对照） ----------

# 下游路口相位偏移 30 秒，恰好补偿 30 秒行程，两路口可行域完全重合
TWO_NODES = [
    it(cycle=60, offset=0, green_start=0, green_end=30, travel=0),
    it(cycle=60, offset=30, green_start=0, green_end=30, travel=30),
]


def test_two_intersections_green_band():
    got = compute_windows(TWO_NODES, 0, 300)
    assert got == [[0, 30], [60, 90], [120, 150], [180, 210], [240, 270]]


def test_empty_array_when_no_solution():
    nodes = [
        it(cycle=60, green_start=0, green_end=10, travel=0),
        it(cycle=60, green_start=20, green_end=30, travel=0),
    ]
    assert compute_windows(nodes, 0, 60) == []


def test_eight_intersections_allowed():
    nodes = [it(travel=i * 5) for i in range(8)]  # 全周期常绿
    assert compute_windows(nodes, 100, 400) == [[100, 400]]


def test_half_open_endpoints_are_never_green():
    # 绿灯终点 30 不含：t=30 到达为红灯
    got = departure_windows_for_intersection(60, 0, 20, 30, 0, 20, 31)
    assert got == [[20, 30]]  # 30 不被包含


def test_brute_force_equivalence_on_random_cases():
    """与逐秒判定的参考实现完全一致（测试本身才允许逐秒）。"""
    import random

    random.seed(42)

    def brute(nodes, lo, hi):
        expected = []
        run_start = None
        for t in range(lo, hi + 1):
            ok = t < hi
            if ok:
                for n in nodes:
                    phase = (t + n["travel"] + n["offset"]) % n["cycle"]
                    gs, ge, c = n["green_start"], n["green_end"], n["cycle"]
                    if gs == ge:
                        green = True
                    elif gs < ge:
                        green = gs <= phase < ge
                    else:
                        green = phase >= gs or phase < ge
                    if not green:
                        ok = False
                        break
            if ok:
                if run_start is None:
                    run_start = t
            else:
                if run_start is not None:
                    expected.append([run_start, t])
                    run_start = None
        if run_start is not None:
            expected.append([run_start, hi])
        return expected

    for _ in range(300):
        n_nodes = random.randint(1, 8)
        nodes = []
        for _ in range(n_nodes):
            c = random.randint(1, 90)
            gs = random.randint(0, c - 1)
            ge = random.randint(0, c - 1)
            nodes.append(
                it(
                    cycle=c,
                    offset=random.randint(0, c - 1),
                    green_start=gs,
                    green_end=ge,
                    travel=random.randint(0, 120),
                )
            )
        length = random.randint(1, 600)
        lo = random.randint(0, 300)
        hi = lo + length
        assert compute_windows(nodes, lo, hi) == brute(nodes, lo, hi)


def test_brute_force_equivalence_with_travel_max():
    """带行驶时间波动时，与逐秒的“抵达弧整体落入绿灯”参考实现一致。"""
    import random

    random.seed(7)

    def green_arcs(c, gs, ge):
        # 提升到实数轴的周期弧：跨零点先视为 [gs, C+ge) 的连续弧
        if gs == ge:
            return [(0, c)]
        if gs < ge:
            return [(gs, ge)]
        return [(gs, c + ge)]

    def brute(nodes, lo, hi):
        expected = []
        run_start = None
        for t in range(lo, hi + 1):
            ok = t < hi
            if ok:
                for n in nodes:
                    # 整周期常绿：任意抵达时刻（含跨周期）均为绿灯
                    if n["green_start"] == n["green_end"]:
                        continue
                    c, o = n["cycle"], n["offset"]
                    t0 = t + n["travel"] + o
                    t1 = t + n.get("travel_max", n["travel"]) + o
                    contained = False
                    for a0, b0 in green_arcs(c, n["green_start"], n["green_end"]):
                        for k in range(t0 // c - 2, t1 // c + 3):
                            a, b = a0 + k * c, b0 + k * c
                            # 抵达弧 [t0,t1] 须整体落入半开绿灯 [a,b)
                            if a <= t0 and t1 < b:
                                contained = True
                                break
                        if contained:
                            break
                    if not contained:
                        ok = False
                        break
            if ok:
                if run_start is None:
                    run_start = t
            else:
                if run_start is not None:
                    expected.append([run_start, t])
                    run_start = None
        if run_start is not None:
            expected.append([run_start, hi])
        return expected

    for _ in range(300):
        n_nodes = random.randint(1, 8)
        nodes = []
        for _ in range(n_nodes):
            c = random.randint(1, 90)
            gs = random.randint(0, c - 1)
            ge = random.randint(0, c - 1)
            travel = random.randint(0, 120)
            node = it(
                cycle=c,
                offset=random.randint(0, c - 1),
                green_start=gs,
                green_end=ge,
                travel=travel,
            )
            if random.random() < 0.7:
                node["travel_max"] = travel + random.randint(0, 2 * c)
            nodes.append(node)
        length = random.randint(1, 600)
        lo = random.randint(0, 300)
        hi = lo + length
        assert compute_windows(nodes, lo, hi) == brute(nodes, lo, hi)
