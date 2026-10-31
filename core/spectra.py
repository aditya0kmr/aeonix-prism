"""
ÆONIX PRISM // SPECTRA Media Intelligence & Live IPTV Engine
Manages curated, public legal live streams and local media for the Living Surface.
Zero Paid APIs, 100% Local-First Provenance.
"""

import os
import json
import time
from typing import Dict, Any, List, Optional

from aeonix.core.db import get_connection, log_audit_event

# Curated high-reliability public/free live streams (Zero Paid APIs)
CURATED_CHANNELS = [
    {
        "id": "nasa_tv",
        "name": "NASA TV / ISS Live",
        "category": "Science & Space",
        "stream_url": "https://ntv1.akamaized.net/hls/live/2014075/NASA-NTV1-HLS/master.m3u8",
        "description": "Live views of Earth from the International Space Station and NASA coverage."
    },
    {
        "id": "dw_news",
        "name": "DW News Live",
        "category": "World News",
        "stream_url": "https://dwamdstream102.akamaized.net/hls/live/2015525/dl_live_102/master.m3u8",
        "description": "Deutsche Welle 24/7 International Global News Broadcast."
    },
    {
        "id": "euronews_en",
        "name": "EuroNews Global",
        "category": "World News",
        "stream_url": "https://euronews-euronews-world-1-au.samsung.wurl.tv/playlist.m3u8",
        "description": "Continuous European & Global Headlines."
    },
    {
        "id": "retro_synth",
        "name": "Cyber Synth & Ambient",
        "category": "Atmosphere & Focus",
        "stream_url": "https://amg01269-01.akamaized.net/hls/live/2026723/amg0126901/master.m3u8",
        "description": "Ambient retro visuals and relaxing soundscapes for Living Surface."
    },
    {
        "id": "nature_relax",
        "name": "Earth Cam & Wildlife",
        "category": "Ambient Nature",
        "stream_url": "https://live-manifests.superfeed.live/live/nature-hls/master.m3u8",
        "description": "Live global wildlife and natural landscape feeds."
    }
]

# In-memory playback state
CURRENT_PLAYBACK: Dict[str, Any] = {
    "is_playing": False,
    "channel_id": None,
    "title": None,
    "stream_url": None,
    "category": None,
    "started_at": None
}

def get_channel_catalog() -> List[Dict[str, Any]]:
    """Returns curated channel lineup."""
    return CURATED_CHANNELS

def find_channel_by_query(query: str) -> Optional[Dict[str, Any]]:
    """Fuzzy searches channel list by name or category."""
    clean = query.strip().lower()
    for ch in CURATED_CHANNELS:
        if ch["id"] in clean or ch["name"].lower() in clean or clean in ch["name"].lower():
            return ch
        if clean in ch["category"].lower():
            return ch
    # Fallback to NASA TV if generic 'space' or 'news'
    if "space" in clean or "iss" in clean or "nasa" in clean:
        return CURATED_CHANNELS[0]
    if "news" in clean or "world" in clean:
        return CURATED_CHANNELS[1]
    if "ambient" in clean or "music" in clean or "chill" in clean:
        return CURATED_CHANNELS[3]
    return CURATED_CHANNELS[0]

def set_playback_state(is_playing: bool, channel: Optional[Dict[str, Any]] = None):
    """Updates internal playback state."""
    global CURRENT_PLAYBACK
    if is_playing and channel:
        CURRENT_PLAYBACK = {
            "is_playing": True,
            "channel_id": channel.get("id"),
            "title": channel.get("name"),
            "stream_url": channel.get("stream_url"),
            "category": channel.get("category"),
            "started_at": time.time()
        }
        log_audit_event(
            actor="SPECTRA",
            action="media_playback_start",
            target=channel.get("id", "stream"),
            result="success",
            details={"title": channel.get("name"), "url": channel.get("stream_url")}
        )
    else:
        CURRENT_PLAYBACK["is_playing"] = False
        log_audit_event(
            actor="SPECTRA",
            action="media_playback_stop",
            target=CURRENT_PLAYBACK.get("channel_id") or "stream",
            result="success",
            details={}
        )

def get_current_playback() -> Dict[str, Any]:
    """Returns the current playback state."""
    return dict(CURRENT_PLAYBACK)
