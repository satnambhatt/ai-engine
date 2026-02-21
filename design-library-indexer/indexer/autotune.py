"""
Adaptive worker auto-tuning for embedding parallelization.

Dynamically adjusts worker count based on:
- CPU load average
- Available RAM
- CPU temperature (Raspberry Pi specific)

Safety-first design: never crashes indexing, always falls back gracefully.
"""

import logging
import os
import subprocess
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# Try to import psutil, but don't fail if unavailable
try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False
    logger.warning("psutil not available - RAM-based tuning disabled")


def get_cpu_count() -> int:
    """Get number of CPU cores."""
    try:
        return os.cpu_count() or 4  # Default to 4 for Raspberry Pi
    except Exception:
        return 4


def get_load_average() -> float:
    """Get 1-minute load average."""
    try:
        return os.getloadavg()[0]
    except (OSError, AttributeError):
        # Windows doesn't have getloadavg
        return 0.0


def get_available_ram_gb() -> Optional[float]:
    """Get available RAM in GB, or None if unavailable."""
    if not HAS_PSUTIL:
        return None

    try:
        return psutil.virtual_memory().available / (1024 ** 3)
    except Exception as e:
        logger.debug(f"Failed to get RAM info: {e}")
        return None


def get_cpu_temp() -> Optional[float]:
    """
    Get CPU temperature in Celsius (Raspberry Pi specific).

    Returns None if temperature cannot be read.
    Falls back gracefully - never crashes.
    """
    try:
        # Raspberry Pi: vcgencmd measure_temp
        result = subprocess.run(
            ['vcgencmd', 'measure_temp'],
            capture_output=True,
            text=True,
            timeout=1.0,
            check=False,
        )

        if result.returncode == 0:
            # Parse output like: temp=58.0'C
            output = result.stdout.strip()
            if 'temp=' in output:
                temp_str = output.split('=')[1].split("'")[0]
                return float(temp_str)

    except (subprocess.TimeoutExpired, subprocess.SubprocessError, ValueError, IndexError) as e:
        logger.debug(f"Temperature read failed: {e}")
    except FileNotFoundError:
        # vcgencmd not available (not on Raspberry Pi)
        logger.debug("vcgencmd not found - not running on Raspberry Pi")

    return None


def get_system_metrics() -> Dict[str, Optional[float]]:
    """
    Get current system metrics.

    Returns:
        Dict with keys: load_avg, free_ram_gb, temp_c, cpu_cores
    """
    return {
        "load_avg": get_load_average(),
        "free_ram_gb": get_available_ram_gb(),
        "temp_c": get_cpu_temp(),
        "cpu_cores": get_cpu_count(),
    }


def choose_worker_count(
    max_workers: int = 3,
    min_workers: int = 1,
    default_workers: int = 2,
) -> int:
    """
    Dynamically choose embedding worker count based on system load.

    Decision logic:
    - Start from default_workers
    - Increase if system has headroom (low load, high RAM, low temp)
    - Decrease if system is stressed (high load OR low RAM OR high temp)
    - Clamp result between min_workers and max_workers

    Args:
        max_workers: Maximum allowed workers
        min_workers: Minimum allowed workers
        default_workers: Starting point for tuning

    Returns:
        Optimal worker count (always in range [min_workers, max_workers])

    Safety:
        Never crashes - returns default_workers if any error occurs
    """
    try:
        metrics = get_system_metrics()
        workers = default_workers

        cpu_cores = metrics["cpu_cores"]
        load_avg = metrics["load_avg"]
        free_ram_gb = metrics.get("free_ram_gb")
        temp_c = metrics.get("temp_c")

        # ── DECISION LOGIC ──

        # CPU Load Analysis
        if load_avg > 0:  # Only if load is available
            load_ratio = load_avg / cpu_cores

            if load_ratio < 0.6:  # System underutilized
                workers += 1
                logger.debug(f"Auto-tune: Low load ({load_avg:.1f}/{cpu_cores} cores) → increase workers")
            elif load_ratio > 1.0:  # System overloaded
                workers -= 1
                logger.debug(f"Auto-tune: High load ({load_avg:.1f}/{cpu_cores} cores) → decrease workers")

        # RAM Analysis
        if free_ram_gb is not None:
            if free_ram_gb > 1.2:  # Plenty of RAM
                workers = min(workers + 1, default_workers + 1)  # Conservative increase
                logger.debug(f"Auto-tune: High RAM ({free_ram_gb:.1f}GB free) → increase workers")
            elif free_ram_gb < 0.6:  # RAM pressure
                workers -= 1
                logger.debug(f"Auto-tune: Low RAM ({free_ram_gb:.1f}GB free) → decrease workers")

        # Temperature Analysis (Raspberry Pi specific)
        # Throttle at >75°C. Engine manages hysteresis: holds at 2 workers until <65°C.
        if temp_c is not None:
            if temp_c > 75:  # Throttle threshold — engine will cap to 2 workers
                workers = min(workers - 1, default_workers - 1)
                logger.warning(f"Auto-tune: High temp ({temp_c:.0f}°C) → decrease workers")
            elif temp_c > 65:  # Caution zone — don't increase
                workers = min(workers, default_workers)
                logger.debug(f"Auto-tune: Warm temp ({temp_c:.0f}°C) → hold current workers")
        else:
            # No temperature sensor - assume safe temp
            logger.debug("Auto-tune: Temperature unavailable, assuming safe")

        # ── CLAMP RESULT ──
        workers = max(min_workers, min(workers, max_workers))

        # ── LOG DECISION ──
        temp_str = f"{temp_c:.0f}°C" if temp_c is not None else "N/A"
        ram_str = f"{free_ram_gb:.1f}GB" if free_ram_gb is not None else "N/A"

        logger.info(
            f"Auto-tune: workers={workers} "
            f"load={load_avg:.1f}/{cpu_cores} "
            f"temp={temp_str} "
            f"free_ram={ram_str}"
        )

        return workers

    except Exception as e:
        logger.warning(f"Auto-tune failed: {e} - falling back to default={default_workers}")
        return default_workers


def is_psutil_available() -> bool:
    """Check if psutil is installed."""
    return HAS_PSUTIL
