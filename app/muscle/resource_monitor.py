"""
resource_monitor.py — Ryzen-Aware Resource Monitor (Module 6)
FileFlow X (V10)

Monitors hardware statistics to prevent the laptop from overheating 
and fan noise from interrupting the professional experience.
If the system is under heavy load, it gracefully throttles the Triage workers.
"""

import os
import psutil
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

class ResourceMonitor:
    def __init__(self, max_ram_percent: float = 85.0, max_cpu_temp: float = 80.0):
        self.max_ram_percent = max_ram_percent
        self.max_cpu_temp = max_cpu_temp
        
        # On Windows, psutil doesn't always have sensors_temperatures() 
        # unless running specific hardware drivers.
        self.can_read_temp = hasattr(psutil, "sensors_temperatures")

    def get_system_health(self) -> Dict[str, Any]:
        """Returns the current state of RAM and CPU."""
        ram = psutil.virtual_memory()
        cpu_percent = psutil.cpu_percent(interval=0.1)
        
        health = {
            "ram_percent": ram.percent,
            "ram_available_gb": ram.available / (1024 ** 3),
            "cpu_percent": cpu_percent,
            "cpu_temp": None,
            "throttling_required": False,
            "reason": ""
        }
        
        if self.can_read_temp:
            try:
                temps = psutil.sensors_temperatures()
                if temps:
                    # Look for coretemp or anything indicative of CPU
                    for name, entries in temps.items():
                        if "coretemp" in name.lower() or "cpu" in name.lower():
                            if entries:
                                max_temp = max(entry.current for entry in entries)
                                health["cpu_temp"] = max_temp
                                break
            except Exception as e:
                logger.debug(f"[Hardware Guard] Could not read temperature sensors: {e}")

        # Check thresholds
        if health["ram_percent"] > self.max_ram_percent:
            health["throttling_required"] = True
            health["reason"] = f"RAM usage critical ({health['ram_percent']}%)"
            
        # Fallback to general CPU usage if temps aren't readable on Windows
        if health.get("cpu_temp") and health["cpu_temp"] > self.max_cpu_temp:
            health["throttling_required"] = True
            health["reason"] = f"CPU Temperature high ({health['cpu_temp']}°C)"
        elif not health.get("cpu_temp") and cpu_percent > 95.0:
            health["throttling_required"] = True
            health["reason"] = f"CPU Usage critical ({cpu_percent}%)"
            
        return health

    def recommend_worker_count(self, base_workers: int = 4) -> int:
        """Dynamically adjusts the number of Triage threads."""
        health = self.get_system_health()
        
        if health["throttling_required"]:
            logger.warning(f"[Hardware Guard] THROTTLING ENGAGED: {health['reason']}")
            # Drop to 1 thread to allow the system to cool down
            return 1
            
        if health["cpu_percent"] < 50.0 and health["ram_percent"] < 60.0:
            # System is chilling, unleash the threads
            cores = psutil.cpu_count(logical=True)
            return min(cores or base_workers, 12) # Use up to 12 threads on the Ryzen if idle
            
        return base_workers
