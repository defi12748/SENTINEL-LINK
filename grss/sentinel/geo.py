"""Pass geometry from the observation's own TLE (SGP4): sub-satellite track,
station look angles and range rate (for the Doppler view)."""

from __future__ import annotations

import math

import numpy as np
from sgp4.api import Satrec, jday

WGS84_A = 6378.137
WGS84_F = 1 / 298.257223563
C_KM_S = 299792.458


def _gmst(jd_ut1: float) -> float:
    t = (jd_ut1 - 2451545.0) / 36525.0
    g = 67310.54841 + (876600 * 3600 + 8640184.812866) * t + 0.093104 * t * t - 6.2e-6 * t ** 3
    return math.radians((g % 86400) / 240.0)


def _teme_to_ecef(r: np.ndarray, jd: float) -> np.ndarray:
    th = _gmst(jd)
    c, s = math.cos(th), math.sin(th)
    return np.array([c * r[0] + s * r[1], -s * r[0] + c * r[1], r[2]])


def _ecef_to_geodetic(x: np.ndarray) -> tuple[float, float, float]:
    lon = math.atan2(x[1], x[0])
    p = math.hypot(x[0], x[1])
    e2 = WGS84_F * (2 - WGS84_F)
    lat = math.atan2(x[2], p * (1 - e2))
    for _ in range(5):
        n = WGS84_A / math.sqrt(1 - e2 * math.sin(lat) ** 2)
        h = p / math.cos(lat) - n
        lat = math.atan2(x[2], p * (1 - e2 * n / (n + h)))
    n = WGS84_A / math.sqrt(1 - e2 * math.sin(lat) ** 2)
    return math.degrees(lat), math.degrees(lon), p / math.cos(lat) - n


def _geodetic_to_ecef(lat: float, lon: float, alt_km: float) -> np.ndarray:
    la, lo = math.radians(lat), math.radians(lon)
    e2 = WGS84_F * (2 - WGS84_F)
    n = WGS84_A / math.sqrt(1 - e2 * math.sin(la) ** 2)
    return np.array([(n + alt_km) * math.cos(la) * math.cos(lo), (n + alt_km) * math.cos(la) * math.sin(lo),
                     (n * (1 - e2) + alt_km) * math.sin(la)])


def pass_geometry(tle1: str, tle2: str, start_utc: float, end_utc: float, station_lat: float,
                  station_lon: float, station_alt_m: float, step_s: float = 10.0,
                  downlink_hz: float = 145.935e6) -> list[dict]:
    sat = Satrec.twoline2rv(tle1, tle2)
    st = _geodetic_to_ecef(station_lat, station_lon, station_alt_m / 1000)
    la, lo = math.radians(station_lat), math.radians(station_lon)
    up = np.array([math.cos(la) * math.cos(lo), math.cos(la) * math.sin(lo), math.sin(la)])
    east = np.array([-math.sin(lo), math.cos(lo), 0.0])
    north = np.cross(up, east)
    out, prev_range = [], None
    for t in np.arange(start_utc, end_utc + step_s, step_s):
        tm = np.datetime64(int(t), "s").astype(object)
        jd, fr = jday(tm.year, tm.month, tm.day, tm.hour, tm.minute, tm.second)
        err, r, _ = sat.sgp4(jd, fr)
        if err:
            continue
        ecef = _teme_to_ecef(np.array(r), jd + fr)
        lat, lon, alt = _ecef_to_geodetic(ecef)
        d = ecef - st
        rng = float(np.linalg.norm(d))
        el = math.degrees(math.asin(float(d @ up) / rng))
        az = math.degrees(math.atan2(float(d @ east), float(d @ north))) % 360
        rr = (rng - prev_range) / step_s if prev_range is not None else 0.0
        prev_range = rng
        out.append({"t": float(t), "lat": lat, "lon": lon, "alt_km": alt, "el": el, "az": az,
                    "range_km": rng, "doppler_hz": -downlink_hz * rr / C_KM_S})
    if len(out) > 1:
        out[0]["doppler_hz"] = out[1]["doppler_hz"]
    return out
