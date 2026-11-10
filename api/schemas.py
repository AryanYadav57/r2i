"""Request schemas for the R2I API."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator


class Point(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


class CompareRequest(BaseModel):
    origin: Point
    dest: Point
    vehicle: str = "ICE"
    alpha: float | None = Field(default=None, ge=0, le=1000)


class SweepRequest(CompareRequest):
    alphas: list[float] = Field(default=[0, 0.25, 0.5, 1, 2, 5, 10, 25], max_length=20)


class ExploreRequest(BaseModel):
    origin: Point
    dest: Point
    objective: str = "car_petrol"
    max_nodes: int = Field(default=6000, ge=10, le=20000)


class OrderIn(BaseModel):
    lat: float
    lon: float
    weight_kg: float = Field(gt=0, le=1000)
    tw_start_s: int = Field(default=9 * 3600, ge=0, le=86400)
    tw_end_s: int = Field(default=13 * 3600, ge=0, le=86400)

    @model_validator(mode="after")
    def _window(self):
        if self.tw_end_s < self.tw_start_s:
            raise ValueError("tw_end_s must be >= tw_start_s")
        return self


class FleetPlanRequest(BaseModel):
    hub: Point
    vehicles: list[str] = Field(min_length=1, max_length=20)
    orders: list[OrderIn] | None = Field(default=None, max_length=120)
    n_orders: int = Field(default=30, ge=1, le=120)
    seed: int = 42
    radius_m: float = Field(default=3000, ge=200, le=8000)
    shift_start_s: int = Field(default=9 * 3600, ge=0, le=86400)
    shift_end_s: int = Field(default=13 * 3600, ge=3600, le=86400)
    time_limit_s: float = Field(default=3.0, gt=0, le=20)

    @model_validator(mode="after")
    def _shift(self):
        if self.shift_end_s <= self.shift_start_s:
            raise ValueError("shift_end_s must be after shift_start_s")
        return self


class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4000)


class AskRequest(BaseModel):
    messages: list[ChatTurn] = Field(min_length=1, max_length=30)
