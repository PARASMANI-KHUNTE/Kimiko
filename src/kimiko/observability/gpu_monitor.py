"""GPU Monitor — Background telemetry via nvidia-smi polling (Phase 5).

Runs as a background asyncio task, polling nvidia-smi every N seconds
and updating Prometheus gauges. Designed to run outside the request loop
to avoid blocking API workers.
"""

from __future__ import annotations

import asyncio
import subprocess

import structlog

from kimiko.core.observability import (
    GPU_VRAM_USED_BYTES,
    GPU_VRAM_TOTAL_BYTES,
    GPU_UTILIZATION_PERCENT,
    GPU_TEMPERATURE_CELSIUS,
)

logger = structlog.get_logger(__name__)

# Megabytes → Bytes
MB_TO_BYTES = 1024 * 1024


def _parse_nvidia_smi() -> dict | None:
    """Run nvidia-smi and parse GPU telemetry.

    Returns dict with keys: vram_used_mb, vram_total_mb, gpu_util, temperature.
    Returns None if nvidia-smi is unavailable.
    """
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=memory.used,memory.total,utilization.gpu,temperature.gpu",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )

        if result.returncode != 0:
            return None

        line = result.stdout.strip().split("\n")[0]  # First GPU
        parts = [p.strip() for p in line.split(",")]

        return {
            "vram_used_mb": float(parts[0]),
            "vram_total_mb": float(parts[1]),
            "gpu_util": float(parts[2]),
            "temperature": float(parts[3]),
        }
    except (FileNotFoundError, subprocess.TimeoutExpired, Exception) as e:
        logger.debug("nvidia_smi_unavailable", error=str(e))
        return None


async def gpu_monitor_loop(interval_seconds: int = 5) -> None:
    """Background loop that polls nvidia-smi and updates Prometheus gauges.

    This should be started as an asyncio task during application startup.

    Args:
        interval_seconds: How often to poll (default: 5s).
    """
    logger.info("gpu_monitor_started", interval=interval_seconds)

    while True:
        try:
            # Run blocking subprocess in executor to avoid blocking the event loop
            loop = asyncio.get_running_loop()
            data = await loop.run_in_executor(None, _parse_nvidia_smi)

            if data:
                GPU_VRAM_USED_BYTES.set(data["vram_used_mb"] * MB_TO_BYTES)
                GPU_VRAM_TOTAL_BYTES.set(data["vram_total_mb"] * MB_TO_BYTES)
                GPU_UTILIZATION_PERCENT.set(data["gpu_util"])
                GPU_TEMPERATURE_CELSIUS.set(data["temperature"])
        except Exception as e:
            logger.warning("gpu_monitor_poll_error", error=str(e))

        await asyncio.sleep(interval_seconds)
