import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.main import green_wave_windows
from app.schemas import GreenWaveRequest, Intersection


def make_request(payload):
    return GreenWaveRequest.model_validate(payload)


def test_api_returns_windows_payload():
    req = make_request(
        {
            "depart_from": 0,
            "depart_to": 300,
            "intersections": [
                {"cycle": 60, "offset": 0, "green_start": 0, "green_end": 30, "travel": 0},
                {"cycle": 60, "offset": 30, "green_start": 0, "green_end": 30, "travel": 30},
            ],
        }
    )
    windows = green_wave_windows(req)
    assert [[w.start, w.end] for w in windows] == [
        [0, 30], [60, 90], [120, 150], [180, 210], [240, 270],
    ]


def test_api_empty_array_on_no_solution():
    req = make_request(
        {
            "depart_from": 0,
            "depart_to": 60,
            "intersections": [
                {"cycle": 60, "offset": 0, "green_start": 0, "green_end": 10, "travel": 0},
                {"cycle": 60, "offset": 0, "green_start": 20, "green_end": 30, "travel": 0},
            ],
        }
    )
    assert green_wave_windows(req) == []


def test_reject_invalid_cycle():
    with pytest.raises(ValidationError):
        Intersection(cycle=0, offset=0, green_start=0, green_end=10, travel=0)


def test_reject_negative_travel():
    with pytest.raises(ValidationError):
        Intersection(cycle=60, offset=0, green_start=0, green_end=10, travel=-1)


def test_reject_offset_outside_cycle():
    req = make_request(
        {
            "depart_from": 0,
            "depart_to": 60,
            "intersections": [
                {"cycle": 60, "offset": 60, "green_start": 0, "green_end": 10, "travel": 0}
            ],
        }
    )
    with pytest.raises(HTTPException) as exc:
        req.validate_ranges()
    assert exc.value.status_code == 422


def test_reject_green_endpoint_outside_cycle():
    req = make_request(
        {
            "depart_from": 0,
            "depart_to": 60,
            "intersections": [
                {"cycle": 60, "offset": 0, "green_start": 0, "green_end": 60, "travel": 0}
            ],
        }
    )
    with pytest.raises(HTTPException) as exc:
        req.validate_ranges()
    assert exc.value.status_code == 422


def test_reject_range_over_one_hour():
    req = make_request(
        {
            "depart_from": 0,
            "depart_to": 3601,
            "intersections": [
                {"cycle": 60, "offset": 0, "green_start": 0, "green_end": 10, "travel": 0}
            ],
        }
    )
    with pytest.raises(HTTPException) as exc:
        req.validate_ranges()
    assert exc.value.status_code == 422


def test_reject_too_many_intersections():
    with pytest.raises(ValidationError):
        make_request(
            {
                "depart_from": 0,
                "depart_to": 60,
                "intersections": [
                    {"cycle": 60, "offset": 0, "green_start": 0, "green_end": 10}
                    for _ in range(9)
                ],
            }
        )


def test_reject_empty_intersections():
    with pytest.raises(ValidationError):
        make_request({"depart_from": 0, "depart_to": 60, "intersections": []})
