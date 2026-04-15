"""Lightweight system monitor for CPU & GPU status (Linux, zero dependencies)."""

from __future__ import annotations

import os
import subprocess
import time as _time
from dataclasses import dataclass
from pathlib import Path
from typing import TypeVar

_T = TypeVar("_T")


# ---------------------------------------------------------------------------
# TTL cache (avoids re-running probes for every icon and menu rebuild)
# ---------------------------------------------------------------------------

def _ttl_cache(ttl_seconds: float):
    """Simple TTL decorator for zero-arg functions."""
    def decorator(fn):
        _last_time: list[float] = [0.0]
        _last_value: list = [None]
        def wrapper():
            now = _time.monotonic()
            if now - _last_time[0] >= ttl_seconds or _last_value[0] is None:
                _last_value[0] = fn()
                _last_time[0] = now
            return _last_value[0]
        return wrapper
    return decorator


@dataclass
class CpuStatus:
    usage_pct: float        # overall CPU usage %
    temp_c: float | None    # °C, or None if unavailable
    core_count: int


@dataclass
class GpuStatus:
    name: str
    usage_pct: float        # GPU utilization %
    temp_c: float
    mem_used_mb: int
    mem_total_mb: int


# ---------------------------------------------------------------------------
# Internal state for CPU delta
# ---------------------------------------------------------------------------
_prev_idle: int | None = None
_prev_total: int | None = None
_CPU_PRIME_INTERVAL_SECONDS = 0.15


def _read_cpu_totals() -> tuple[int, int] | None:
    """Read the aggregate CPU idle/total counters from ``/proc/stat``."""
    try:
        with open("/proc/stat", encoding="utf-8") as f:
            line = f.readline()  # "cpu  user nice system idle ..."
    except Exception:
        return None

    parts = line.split()
    if not parts or parts[0] != "cpu":
        return None

    vals = list(map(int, parts[1:]))
    idle = vals[3]
    total = sum(vals)
    return idle, total


def _read_max_cpu_temp() -> float | None:
    """Read the hottest available thermal zone in Celsius."""
    try:
        import glob

        zones = glob.glob("/sys/class/thermal/thermal_zone*/temp")
        temps = []
        for zone in zones:
            with open(zone, encoding="utf-8") as f:
                temps.append(int(f.read().strip()) / 1000.0)
        if temps:
            return round(max(temps), 1)
    except Exception:
        pass
    return None


def _compute_cpu_usage(prev_idle: int, prev_total: int, idle: int, total: int) -> float:
    """Convert two ``/proc/stat`` samples into an interval CPU usage percentage."""
    d_idle = idle - prev_idle
    d_total = total - prev_total
    if d_total <= 0:
        return 0.0
    busy = max(d_total - d_idle, 0)
    return round(busy / d_total * 100, 1)


def _read_cpu_status() -> CpuStatus | None:
    """Read CPU usage from /proc/stat and temperature from thermal zones."""
    global _prev_idle, _prev_total  # noqa: PLW0603

    try:
        sample = _read_cpu_totals()
        if sample is None:
            return None

        idle, total = sample
        if _prev_idle is None or _prev_total is None:
            # Prime once on first use so the first number reflects "now" instead
            # of the average CPU load since boot.
            _time.sleep(_CPU_PRIME_INTERVAL_SECONDS)
            primed_sample = _read_cpu_totals()
            if primed_sample is None:
                return None
            prev_idle, prev_total = idle, total
            idle, total = primed_sample
        else:
            prev_idle, prev_total = _prev_idle, _prev_total

        usage = _compute_cpu_usage(prev_idle, prev_total, idle, total)
        _prev_idle = idle
        _prev_total = total

        return CpuStatus(
            usage_pct=usage,
            temp_c=_read_max_cpu_temp(),
            core_count=os.cpu_count() or 1,
        )
    except Exception:
        return None


@_ttl_cache(ttl_seconds=1.0)
def get_cpu_status() -> CpuStatus | None:
    """Cached CPU status — avoids double-read in the same refresh cycle."""
    return _read_cpu_status()


def _get_nvidia_gpu() -> GpuStatus | None:
    """Query NVIDIA GPU status via nvidia-smi."""
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,utilization.gpu,temperature.gpu,"
                "memory.used,memory.total",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=3,
        )
        if result.returncode != 0:
            return None
        # "NVIDIA GeForce RTX 5090 D, 56, 68, 18580, 32607"
        parts = [p.strip() for p in result.stdout.strip().split(",")]
        if len(parts) < 5:
            return None
        return GpuStatus(
            name=parts[0],
            usage_pct=float(parts[1]),
            temp_c=float(parts[2]),
            mem_used_mb=int(parts[3]),
            mem_total_mb=int(parts[4]),
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, Exception):
        return None


def _get_amd_gpu() -> GpuStatus | None:
    """Query AMD GPU via sysfs / rocm-smi."""
    import glob

    # Try rocm-smi first
    try:
        result = subprocess.run(
            ["rocm-smi", "--showuse", "--showtemp", "--showmeminfo", "vram", "--csv"],
            capture_output=True,
            text=True,
            timeout=3,
        )
        if result.returncode == 0 and result.stdout.strip():
            lines = result.stdout.strip().splitlines()
            if len(lines) >= 2:
                parts = [p.strip() for p in lines[1].split(",")]
                if len(parts) >= 4:
                    return GpuStatus(
                        name="AMD GPU",
                        usage_pct=float(parts[0]),
                        temp_c=float(parts[1]),
                        mem_used_mb=int(float(parts[2]) / (1024 * 1024)),
                        mem_total_mb=int(float(parts[3]) / (1024 * 1024)),
                    )
    except (FileNotFoundError, subprocess.TimeoutExpired, Exception):
        pass

    # Fallback: read directly from sysfs
    try:
        busy_files = glob.glob("/sys/class/drm/card*/device/gpu_busy_percent")
        if not busy_files:
            return None

        card_dir = str(Path(busy_files[0]).parent)
        usage = float(Path(busy_files[0]).read_text().strip())

        temp: float = 0.0
        hwmon_dirs = glob.glob(f"{card_dir}/hwmon/hwmon*/temp1_input")
        if hwmon_dirs:
            temp = float(Path(hwmon_dirs[0]).read_text().strip()) / 1000.0

        mem_used = 0
        mem_total = 0
        vram_used_path = f"{card_dir}/mem_info_vram_used"
        vram_total_path = f"{card_dir}/mem_info_vram_total"
        if Path(vram_used_path).exists() and Path(vram_total_path).exists():
            mem_used = int(Path(vram_used_path).read_text().strip()) // (1024 * 1024)
            mem_total = int(Path(vram_total_path).read_text().strip()) // (1024 * 1024)

        return GpuStatus(
            name="AMD GPU",
            usage_pct=round(usage, 1),
            temp_c=round(temp, 1),
            mem_used_mb=mem_used,
            mem_total_mb=mem_total,
        )
    except Exception:
        return None


@_ttl_cache(ttl_seconds=1.5)
def get_gpu_status() -> GpuStatus | None:
    """Query GPU status — tries NVIDIA first, then AMD."""
    return _get_nvidia_gpu() or _get_amd_gpu()


def format_cpu_line(s: CpuStatus) -> str:
    """Format CPU status into a concise display line."""
    line = f"CPU: {s.usage_pct:.0f}%"
    if s.temp_c is not None:
        line += f"  {s.temp_c:.0f}°C"
    return line


def format_gpu_line(s: GpuStatus) -> str:
    """Format GPU status into a concise display line."""
    mem_gb = s.mem_used_mb / 1024
    total_gb = s.mem_total_mb / 1024
    return (
        f"GPU: {s.usage_pct:.0f}%  {s.temp_c:.0f}°C  "
        f"{mem_gb:.1f}/{total_gb:.0f}G"
    )
