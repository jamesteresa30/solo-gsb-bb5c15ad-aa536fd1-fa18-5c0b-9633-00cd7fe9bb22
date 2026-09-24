"""FastAPI 应用入口。"""

from __future__ import annotations

from fastapi import FastAPI

from .greenwave import compute_windows
from .schemas import GreenWaveRequest, Window

app = FastAPI(
    title="干线绿波发车窗口 API",
    description=(
        "给定干线上至多 8 个路口的信号周期、相位偏移、周期内绿灯半开区间"
        "（可跨周期零点）及行驶秒数（可选波动上限 travel_max），计算在指定"
        "发车范围（<= 3600 秒）内，对行驶时间区间内任意取值都能在抵达每个"
        "路口时遇绿灯的全部极大半开发车区间。"
    ),
    version="1.0.0",
)


@app.get("/health", tags=["系统"], summary="健康检查")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post(
    "/api/green-wave/windows",
    response_model=list[Window],
    tags=["绿波"],
    summary="计算全部极大绿波发车窗口",
)
def green_wave_windows(request: GreenWaveRequest) -> list[Window]:
    request.validate_ranges()
    windows = compute_windows(
        intersections=[
            {
                "cycle": item.cycle,
                "offset": item.offset,
                "green_start": item.green_start,
                "green_end": item.green_end,
                "travel": item.travel,
                "travel_max": item.travel_max,
            }
            for item in request.intersections
        ],
        depart_from=request.depart_from,
        depart_to=request.depart_to,
    )
    return [Window(start=start, end=end) for start, end in windows]
