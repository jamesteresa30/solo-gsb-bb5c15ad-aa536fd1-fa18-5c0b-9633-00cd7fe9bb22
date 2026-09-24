"""干线绿波发车窗口核心算法。

所有时间量均为整数秒，路口信号以固定周期循环。

相位约定
--------
对路口 i，给定：

* ``cycle``  : 信号周期 C（秒，正整数）；
* ``offset`` : 相位偏移 o（0 <= o < C），绝对时间 t 在该路口的本地相位为
               ``(t + o) mod C``；
* ``green_start`` / ``green_end`` : 周期内绿灯半开区间端点，取值 [0, C)：
    - g_start < g_end：绿灯为 ``[g_start, g_end)``；
    - g_start > g_end：绿灯跨零点，为 ``[g_start, C) ∪ [0, g_end)``；
    - g_start == g_end：整周期常绿 ``[0, C)``；
* ``travel`` : 从起点到该路口的行驶秒数下限 T；
* ``travel_max`` : 可选的行驶秒数上限 T_max >= T。实际行驶时间可取闭区间
  ``[T, T_max]`` 内任意实数秒；省略或等于 T 时退化为固定行驶时间。

出发时刻为 t 时，实际抵达时刻可能是 t + T + s（s ∈ [0, slack]，
slack = T_max - T）中的任意值。要在**所有**行程取值下都遇绿灯，抵达相位
必须整体落入绿灯弧：等价于把绿灯弧的“入口端”收缩 slack 秒——

* 整周期常绿（g_start == g_end）：任意 slack 下仍为整周期，**不受波动影响**；
* 普通绿灯 [a, b)：slack < b - a 时收缩为 [a, b - slack)，否则无可行段；
* 跨零点绿灯 [g_start, C) ∪ [0, g_end)：**先视为覆盖零点的连续弧**
  [g_start, C + g_end) 再收缩为 [g_start, C + g_end - slack)，随后按长度映射
  回 [0, C)：收缩后不再跨零点（至多剩一段普通绿灯）或仍跨零点（至多两段）。

固定行驶时间下（slack = 0）收缩退化为恒等，语义与原先完全一致。收缩后的
绿灯按 ``shift = (T + o) mod C`` 平移到出发时间轴，得到一组周期重复的半开
整数区间，再与请求的发车范围 ``[depart_from, depart_to)`` 求交；各路口结果
两两求交并合并相邻（端点相接）区间，即得全部极大半开发车窗口。全程只做
区间运算，不逐秒试探。
"""

from __future__ import annotations

from typing import Iterable

# 周期上限仅用于防御异常输入，一日之内足够覆盖任何实际信号周期。
MAX_CYCLE = 86_400
MAX_WINDOW_SECONDS = 3_600
MAX_INTERSECTIONS = 8

Interval = list[int]  # 长度为 2 的半开区间 [start, end)


def local_green_intervals(cycle: int, green_start: int, green_end: int) -> list[Interval]:
    """展开单个周期 [0, C) 内的绿灯半开区间。

    端点相等时视为整周期常绿；跨零点时展开为两段。
    """
    if green_start == green_end:
        return [[0, cycle]]
    if green_start < green_end:
        return [[green_start, green_end]]
    return [[green_start, cycle], [0, green_end]]


def eroded_green_intervals(
    cycle: int, green_start: int, green_end: int, slack: int
) -> list[Interval]:
    """把绿灯弧的入口端收缩 ``slack`` 秒后的本地绿灯半开区间。

    ``slack`` 为行驶时间波动量 T_max - T：抵达相位弧长度为 slack，须整体
    落入绿灯。跨零点绿灯先在展开的连续弧 [g_start, C + g_end) 上收缩，再
    映射回 [0, C)；整周期常绿恒为整周期（不受波动影响）。
    """
    if green_start == green_end:
        return [[0, cycle]]
    if slack <= 0:
        return local_green_intervals(cycle, green_start, green_end)
    if green_start < green_end:
        end = green_end - slack
        return [[green_start, end]] if end > green_start else []
    # 跨零点：连续弧 [green_start, C + green_end) 收缩入口端
    arc_end = cycle + green_end - slack
    if arc_end <= green_start:
        return []
    if arc_end <= cycle:
        return [[green_start, arc_end]]
    return [[green_start, cycle], [0, arc_end - cycle]]


def merge_intervals(intervals: Iterable[Interval]) -> list[Interval]:
    """合并重叠或端点相接的半开区间（[a,b) 与 [b,c) 合并为 [a,c)）。"""
    merged: list[Interval] = []
    for start, end in sorted(intervals):
        if start >= end:
            continue
        if merged and start <= merged[-1][1]:
            if end > merged[-1][1]:
                merged[-1][1] = end
        else:
            merged.append([start, end])
    return merged


def clip_intervals(
    intervals: Iterable[Interval], lower: int, upper: int
) -> list[Interval]:
    """把半开区间裁剪进 [lower, upper)。"""
    clipped: list[Interval] = []
    for start, end in intervals:
        start = max(start, lower)
        end = min(end, upper)
        if start < end:
            clipped.append([start, end])
    return clipped


def departure_windows_for_intersection(
    cycle: int,
    offset: int,
    green_start: int,
    green_end: int,
    travel: int,
    depart_from: int,
    depart_to: int,
    slack: int = 0,
) -> list[Interval]:
    """单个路口在 [depart_from, depart_to) 内的全部可行出发区间（已合并）。

    ``slack`` 为行驶时间波动量 T_max - T（0 表示固定行驶时间）。
    """
    greens = eroded_green_intervals(cycle, green_start, green_end, slack)
    # (t + T + o) mod C 与 (t + shift) mod C 等价；波动部分已在绿灯收缩中扣除。
    shift = (travel + offset) % cycle

    raw: list[Interval] = []
    for local_start, local_end in greens:
        # 本地绿灯 [a, b) 对应出发区间 [kC + a - shift, kC + b - shift)。
        # 只需枚举与发车范围有非空交的周期 k：
        #   kC + b - shift > depart_from  ⇔  k > (depart_from - b + shift) / C
        #   kC + a - shift < depart_to    ⇔  k < (depart_to   - a + shift) / C
        k_min = (depart_from - local_end + shift) // cycle + 1
        k_max = -((-(depart_to - local_start + shift)) // cycle) - 1
        for k in range(k_min, k_max + 1):
            base = k * cycle
            raw.append(
                [base + local_start - shift, base + local_end - shift]
            )

    return merge_intervals(clip_intervals(raw, depart_from, depart_to))


def intersect_interval_lists(
    left: list[Interval], right: list[Interval]
) -> list[Interval]:
    """两组各自有序、互不相交的半开区间列表的交集（双指针）。"""
    i = j = 0
    result: list[Interval] = []
    while i < len(left) and j < len(right):
        start = max(left[i][0], right[j][0])
        end = min(left[i][1], right[j][1])
        if start < end:
            result.append([start, end])
        if left[i][1] < right[j][1]:
            i += 1
        else:
            j += 1
    return result


def compute_windows(
    intersections: Iterable[dict],
    depart_from: int,
    depart_to: int,
) -> list[Interval]:
    """求所有路口均遇绿灯的全部极大半开发车区间，按起点排序。

    ``intersections`` 中的每个字典包含 cycle / offset / green_start /
    green_end / travel 字段，以及可选的 travel_max 字段（缺省或为 None 时
    视为 travel，即行驶时间无波动），由 Pydantic 模型保证合法。
    """
    common: list[Interval] | None = None
    for item in intersections:
        travel_max = item.get("travel_max")
        if travel_max is None:
            travel_max = item["travel"]
        windows = departure_windows_for_intersection(
            cycle=item["cycle"],
            offset=item["offset"],
            green_start=item["green_start"],
            green_end=item["green_end"],
            travel=item["travel"],
            depart_from=depart_from,
            depart_to=depart_to,
            slack=travel_max - item["travel"],
        )
        if common is None:
            common = windows
        else:
            common = intersect_interval_lists(common, windows)
        if not common:
            return []
    # 求交不会产生相接区间，最后再合并一次以策安全。
    return merge_intervals(common or [])
