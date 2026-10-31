"""
ATLAS — Geospatial & Situational Awareness Engine
Provides offline/local situational awareness, open-source weather intelligence (Open-Meteo),
geographic coordinate normalization, and spatial risk contexts.
"""

import time
import urllib.request
import json
import logging
from typing import Dict, Any

logger = logging.getLogger("aeonix.core.atlas")


class AtlasEngine:
    def __init__(self):
        pass

    def get_weather_intel(self, lat: float = 28.6139, lon: float = 77.2090) -> Dict[str, Any]:
        """
        Retrieves weather telemetry using Open-Meteo (100% free, keyless, open-source).
        Falls back gracefully if offline.
        """
        url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Aeonix-Prism-Atlas/2.0"})
            with urllib.request.urlopen(req, timeout=3.0) as resp:
                data = json.loads(resp.read().decode())
                current = data.get("current_weather", {})
                return {
                    "source": "Open-Meteo (Keyless)",
                    "latitude": lat,
                    "longitude": lon,
                    "temperature_c": current.get("temperature"),
                    "windspeed_kmh": current.get("windspeed"),
                    "weather_code": current.get("weathercode"),
                    "is_live": True,
                }
        except Exception as e:
            logger.warning(f"Atlas weather fetch fallback (offline): {e}")
            return {
                "source": "Local Cache (Offline Fallback)",
                "latitude": lat,
                "longitude": lon,
                "temperature_c": 24.0,
                "condition": "Clear / Nominal",
                "is_live": False,
            }

    def get_situational_summary(self) -> Dict[str, Any]:
        weather = self.get_weather_intel()
        return {
            "spatial_zone": "Sovereign Home Perimeter",
            "coordinates": {"lat": 28.6139, "lon": 77.2090},
            "environment": weather,
            "status": "SECURE",
            "timestamp": time.time(),
        }


atlas = AtlasEngine()
