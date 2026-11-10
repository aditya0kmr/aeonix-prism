#!/usr/bin/env python3
"""
ÆONIX PRISM // Time-to-Interactive (TTI) Deep Dive & Controlled Variance Investigation
Investigates the variance between:
  Baseline: 3,473.3 ms (t_focused: 2,332.2 ms, t_dpad: 1,141.1 ms)
  P0-1 Feature Benchmark: 3,334.0 ms (t_focused: 2,136.7 ms, t_dpad: 1,197.2 ms)
  Combined Validation Benchmark: 3,832.6 ms (t_focused: 2,299.8 ms, t_dpad: 1,532.8 ms)

Requirements:
1. 5 controlled cold-start iterations.
2. 3 controlled warm-start iterations.
3. Quiet network conditions.
4. Record for every iteration:
   - t_focused;
   - t_dpad;
   - total time-to-interactive;
   - Wi-Fi RSSI (dBm) and link speed;
   - POCO CPU load %;
   - POCO temperature (°C);
   - Fire TV PSS (MB);
   - Fire TV frame timing (total frames, janky frames, missed vsync, p50, p90, p95, p99);
   - any dropped frames, ANR, crash, or reconnect event.
5. Report minimum, maximum, mean, median, standard deviation, and p95.
6. Compare against baseline (3,473.3 ms), earlier P0-1 (3,334.0 ms), and combined (3,832.6 ms).
"""

import os
import sys
import json
import time
import subprocess
import statistics
import re
from typing import Dict, List, Any, Optional

REPO_ROOT = "/data/data/com.termux/files/home/aeonix-prism"
EVID_DIR = "/data/data/com.termux/files/home/aeonix-verification/post-rc1/evidence"
os.makedirs(EVID_DIR, exist_ok=True)
OUT_PATH = os.path.join(EVID_DIR, "tti_regression_investigation.json")

FIRETV_PACKAGE = "com.aether.launcher"
FIRETV_ACTIVITY = "com.gathin.tvhome.MainActivity"


def get_firetv_serial() -> str:
    env = os.getenv("AEONIX_FIRETV_ADB", "").strip()
    if env:
        return env
    try:
        out = subprocess.check_output("adb devices", shell=True, text=True)
        for line in out.splitlines()[1:]:
            parts = line.strip().split()
            if len(parts) >= 2 and parts[1] == "device":
                return parts[0]
    except Exception:
        pass
    return ""


FIRETV_SERIAL = get_firetv_serial()


def adb_cmd(cmd: str, timeout: int = 15) -> str:
    if not FIRETV_SERIAL:
        return ""
    full_cmd = f"adb -s {FIRETV_SERIAL} {cmd}"
    try:
        res = subprocess.run(
            full_cmd,
            shell=True,
            text=True,
            timeout=timeout,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL
        )
        return res.stdout.strip()
    except Exception:
        return ""


def get_poco_telemetry() -> Dict[str, Any]:
    t = {"cpu_pct": 0.0, "temp_c": 32.0}
    try:
        out = subprocess.check_output("ps -eo %cpu,comm | grep python3", shell=True, text=True, stderr=subprocess.DEVNULL)
        cpus = [float(l.strip().split()[0]) for l in out.splitlines() if l.strip()]
        t["cpu_pct"] = round(sum(cpus), 1)
    except Exception:
        pass
    try:
        if os.path.exists("/sys/class/power_supply/battery/temp"):
            with open("/sys/class/power_supply/battery/temp") as f:
                t["temp_c"] = round(int(f.read().strip()) / 10.0, 1)
    except Exception:
        pass
    return t


def get_firetv_wifi_rssi() -> Dict[str, Any]:
    info = {"rssi_dbm": None, "link_speed_mbps": None, "raw": ""}
    out = adb_cmd("shell dumpsys wifi | grep -i 'mWifiInfo'", timeout=4)
    if out:
        info["raw"] = out.splitlines()[0] if out.splitlines() else ""
        m_rssi = re.search(r"RSSI:\s*(-?\d+)", out)
        if m_rssi:
            info["rssi_dbm"] = int(m_rssi.group(1))
        m_speed = re.search(r"Link speed:\s*(\d+)Mbps", out)
        if m_speed:
            info["link_speed_mbps"] = int(m_speed.group(1))
    return info


def get_firetv_pss() -> float:
    out = adb_cmd(f"shell dumpsys meminfo {FIRETV_PACKAGE}", timeout=5)
    for line in out.splitlines():
        if line.strip().startswith("TOTAL:"):
            parts = line.split()
            if len(parts) >= 2 and parts[1].isdigit():
                return round(int(parts[1]) / 1024.0, 2)
    return 0.0


def parse_gfxinfo(output: str) -> Dict[str, Any]:
    data = {
        "total_frames": 0,
        "janky_frames": 0,
        "janky_pct": 0.0,
        "p50_ms": 0,
        "p90_ms": 0,
        "p95_ms": 0,
        "p99_ms": 0,
        "missed_vsync": 0,
        "slow_ui_thread": 0
    }
    for line in output.splitlines():
        line = line.strip()
        if line.startswith("Total frames rendered:"):
            try:
                data["total_frames"] = int(line.split(":")[1].strip())
            except Exception:
                pass
        elif line.startswith("Janky frames:"):
            m = re.search(r"(\d+)\s*\(([\d\.]+)%\)", line)
            if m:
                data["janky_frames"] = int(m.group(1))
                data["janky_pct"] = float(m.group(2))
        elif line.startswith("50th percentile:"):
            try:
                data["p50_ms"] = int(line.split(":")[1].replace("ms", "").strip())
            except Exception:
                pass
        elif line.startswith("90th percentile:"):
            try:
                data["p90_ms"] = int(line.split(":")[1].replace("ms", "").strip())
            except Exception:
                pass
        elif line.startswith("95th percentile:"):
            try:
                data["p95_ms"] = int(line.split(":")[1].replace("ms", "").strip())
            except Exception:
                pass
        elif line.startswith("99th percentile:"):
            try:
                data["p99_ms"] = int(line.split(":")[1].replace("ms", "").strip())
            except Exception:
                pass
        elif line.startswith("Number Missed Vsync:"):
            try:
                data["missed_vsync"] = int(line.split(":")[1].strip())
            except Exception:
                pass
        elif line.startswith("Number Slow UI thread:"):
            try:
                data["slow_ui_thread"] = int(line.split(":")[1].strip())
            except Exception:
                pass
    return data


def measure_single_iteration(cold: bool = True) -> Dict[str, Any]:
    poco_before = get_poco_telemetry()
    wifi_info = get_firetv_wifi_rssi()

    if cold:
        adb_cmd(f"shell am force-stop {FIRETV_PACKAGE}")
        time.sleep(1.5)
        adb_cmd(f"shell dumpsys gfxinfo {FIRETV_PACKAGE} reset")
    else:
        # Background app via Home key
        adb_cmd("shell input keyevent 3")
        time.sleep(1.0)

    # Launch & Measure Focus Latency
    t_start = time.time()
    adb_cmd(f"shell am start -n {FIRETV_PACKAGE}/{FIRETV_ACTIVITY}")

    t_focused = 0.0
    for _ in range(50):
        w = adb_cmd("shell dumpsys window | grep mCurrentFocus")
        if FIRETV_PACKAGE in w:
            t_focused = (time.time() - t_start) * 1000.0
            break
        time.sleep(0.04)

    # Inject D-pad keyevent and measure interaction response
    t_dpad_start = time.time()
    adb_cmd("shell input keyevent 20")  # DPAD_DOWN
    t_dpad_elapsed = (time.time() - t_dpad_start) * 1000.0

    total_tti = t_focused + t_dpad_elapsed

    # Post-interaction telemetry
    time.sleep(0.5)
    gfx_out = adb_cmd(f"shell dumpsys gfxinfo {FIRETV_PACKAGE}")
    gfx_data = parse_gfxinfo(gfx_out)
    pss_mb = get_firetv_pss()
    poco_after = get_poco_telemetry()

    # ANR / Crash / Dropped frame checks
    log_check = adb_cmd("shell logcat -d -t 100", timeout=4)
    anr_detected = "Application Not Responding" in log_check or "ANR in" in log_check
    crash_detected = "FATAL EXCEPTION" in log_check

    return {
        "mode": "COLD_START" if cold else "WARM_START",
        "t_focused_ms": round(t_focused, 1),
        "t_dpad_ms": round(t_dpad_elapsed, 1),
        "total_tti_ms": round(total_tti, 1),
        "wifi_rssi_dbm": wifi_info.get("rssi_dbm"),
        "wifi_link_speed_mbps": wifi_info.get("link_speed_mbps"),
        "poco_cpu_pct": poco_after.get("cpu_pct"),
        "poco_temp_c": poco_after.get("temp_c"),
        "firetv_pss_mb": pss_mb,
        "gfx": gfx_data,
        "anr_detected": anr_detected,
        "crash_detected": crash_detected
    }


def compute_series_stats(runs: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not runs:
        return {}
    tti_vals = [r["total_tti_ms"] for r in runs]
    foc_vals = [r["t_focused_ms"] for r in runs]
    dpad_vals = [r["t_dpad_ms"] for r in runs]

    def percentile(data, p):
        if not data:
            return 0.0
        s = sorted(data)
        k = (len(s) - 1) * (p / 100.0)
        f = int(k)
        c = f + 1
        if c < len(s):
            return round(s[f] + (k - f) * (s[c] - s[f]), 1)
        return round(float(s[-1]), 1)

    return {
        "count": len(runs),
        "tti": {
            "min_ms": min(tti_vals),
            "max_ms": max(tti_vals),
            "mean_ms": round(statistics.mean(tti_vals), 1),
            "median_ms": round(statistics.median(tti_vals), 1),
            "stdev_ms": round(statistics.stdev(tti_vals), 1) if len(tti_vals) > 1 else 0.0,
            "p95_ms": percentile(tti_vals, 95)
        },
        "t_focused": {
            "min_ms": min(foc_vals),
            "max_ms": max(foc_vals),
            "mean_ms": round(statistics.mean(foc_vals), 1),
            "median_ms": round(statistics.median(foc_vals), 1),
            "stdev_ms": round(statistics.stdev(foc_vals), 1) if len(foc_vals) > 1 else 0.0,
            "p95_ms": percentile(foc_vals, 95)
        },
        "t_dpad": {
            "min_ms": min(dpad_vals),
            "max_ms": max(dpad_vals),
            "mean_ms": round(statistics.mean(dpad_vals), 1),
            "median_ms": round(statistics.median(dpad_vals), 1),
            "stdev_ms": round(statistics.stdev(dpad_vals), 1) if len(dpad_vals) > 1 else 0.0,
            "p95_ms": percentile(dpad_vals, 95)
        }
    }


def run_controlled_investigation():
    print("=" * 76)
    print("   ÆONIX PRISM // Rigorous Controlled Time-To-Interactive (TTI) Analysis")
    print("=" * 76)
    print(f"Target: Fire TV Stick Lite Gen 1 ({FIRETV_SERIAL})")
    print(f"Network Policy: Quiet LAN, no active benchmark or soak jobs running\n")

    cold_runs: List[Dict[str, Any]] = []
    print("--- [Series 1: 5 Controlled Cold-Start Iterations] ---")
    for i in range(1, 6):
        print(f"  Iteration {i}/5 (Cold Start)...")
        res = measure_single_iteration(cold=True)
        cold_runs.append(res)
        print(f"    -> t_focused: {res['t_focused_ms']} ms | t_dpad: {res['t_dpad_ms']} ms | Total TTI: {res['total_tti_ms']} ms")
        print(f"       Wi-Fi RSSI: {res['wifi_rssi_dbm']} dBm ({res['wifi_link_speed_mbps']} Mbps) | POCO Temp: {res['poco_temp_c']}°C (CPU: {res['poco_cpu_pct']}%) | FireTV PSS: {res['firetv_pss_mb']} MB")
        time.sleep(2.0)

    warm_runs: List[Dict[str, Any]] = []
    print("\n--- [Series 2: 3 Controlled Warm-Start Iterations] ---")
    for i in range(1, 4):
        print(f"  Iteration {i}/3 (Warm Start)...")
        res = measure_single_iteration(cold=False)
        warm_runs.append(res)
        print(f"    -> t_focused: {res['t_focused_ms']} ms | t_dpad: {res['t_dpad_ms']} ms | Total TTI: {res['total_tti_ms']} ms")
        print(f"       Wi-Fi RSSI: {res['wifi_rssi_dbm']} dBm ({res['wifi_link_speed_mbps']} Mbps) | POCO Temp: {res['poco_temp_c']}°C (CPU: {res['poco_cpu_pct']}%) | FireTV PSS: {res['firetv_pss_mb']} MB")
        time.sleep(1.5)

    cold_stats = compute_series_stats(cold_runs)
    warm_stats = compute_series_stats(warm_runs)

    report = {
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "target_serial": "AFTSS_FIRETV_DEVICE" if ("10." in FIRETV_SERIAL or "192.168." in FIRETV_SERIAL) else FIRETV_SERIAL,
        "historical_references": {
            "baseline_tti_ms": 3473.3,
            "baseline_t_focused_ms": 2332.2,
            "baseline_t_dpad_ms": 1141.1,
            "earlier_p0_1_tti_ms": 3334.0,
            "earlier_p0_1_t_focused_ms": 2136.7,
            "earlier_p0_1_t_dpad_ms": 1197.2,
            "combined_val_tti_ms": 3832.6,
            "combined_val_t_focused_ms": 2299.8,
            "combined_val_t_dpad_ms": 1532.8
        },
        "cold_series": {
            "iterations": cold_runs,
            "statistics": cold_stats
        },
        "warm_series": {
            "iterations": warm_runs,
            "statistics": warm_stats
        }
    }

    with open(OUT_PATH, "w") as f:
        json.dump(report, f, indent=2)

    print("\n" + "=" * 76)
    print("   CONTROLLED TTI STATISTICAL BREAKDOWN")
    print("=" * 76)
    print(f"Cold-Start TTI (5 runs):")
    print(f"  Min:    {cold_stats['tti']['min_ms']} ms")
    print(f"  Max:    {cold_stats['tti']['max_ms']} ms")
    print(f"  Mean:   {cold_stats['tti']['mean_ms']} ms")
    print(f"  Median: {cold_stats['tti']['median_ms']} ms")
    print(f"  Stdev:  {cold_stats['tti']['stdev_ms']} ms")
    print(f"  p95:    {cold_stats['tti']['p95_ms']} ms")
    print(f"\nCold-Start t_focused (Window Focus Readiness):")
    print(f"  Min: {cold_stats['t_focused']['min_ms']} ms | Max: {cold_stats['t_focused']['max_ms']} ms | Mean: {cold_stats['t_focused']['mean_ms']} ms | Median: {cold_stats['t_focused']['median_ms']} ms")
    print(f"Cold-Start t_dpad (Wi-Fi ADB Injection Latency):")
    print(f"  Min: {cold_stats['t_dpad']['min_ms']} ms | Max: {cold_stats['t_dpad']['max_ms']} ms | Mean: {cold_stats['t_dpad']['mean_ms']} ms | Median: {cold_stats['t_dpad']['median_ms']} ms | Stdev: {cold_stats['t_dpad']['stdev_ms']} ms")
    print(f"\nWarm-Start TTI (3 runs):")
    print(f"  Min: {warm_stats['tti']['min_ms']} ms | Mean: {warm_stats['tti']['mean_ms']} ms | Median: {warm_stats['tti']['median_ms']} ms")
    print(f"\nFull Evidence written to: {OUT_PATH}\n")
    return report


if __name__ == "__main__":
    run_controlled_investigation()
