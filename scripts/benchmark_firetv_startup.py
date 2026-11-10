#!/usr/bin/env python3
"""
ÆONIX PRISM // Ticket P0-1: Fire TV View Inflation & UI Startup Benchmark
Measures:
1. Cold start time (ThisTime, TotalTime, WaitTime).
2. Frame stats (Total frames, janky frames > 16.6ms, missed VSYNCs, slow UI thread, frame percentiles p50, p90, p95, p99).
3. First visible frame latency.
4. Time to interactive D-pad navigation.
5. Steady-state rendering performance (during 30-frame D-pad navigation).
6. Process memory PSS (KB and MB).
7. APK binary size.
"""

import os
import sys
import json
import time
import subprocess
import re

FIRETV_SERIAL = os.getenv("AEONIX_FIRETV_ADB", "10.96.74.179:5555")
FIRETV_PACKAGE = "com.aether.launcher"
FIRETV_ACTIVITY = "com.gathin.tvhome.MainActivity"


def adb_cmd(cmd: str, timeout: int = 15) -> str:
    full_cmd = f"adb -s {FIRETV_SERIAL} {cmd}"
    res = subprocess.run(full_cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=timeout)
    return res.stdout.strip()


def get_firetv_pss() -> int:
    try:
        out = adb_cmd(f"shell dumpsys meminfo {FIRETV_PACKAGE}")
        for line in out.splitlines():
            if "TOTAL PSS:" in line or "TOTAL:" in line:
                parts = line.split()
                for p in parts:
                    if p.isdigit():
                        return int(p)
    except Exception:
        pass
    return 0


def get_apk_size() -> int:
    try:
        path_out = adb_cmd(f"shell pm path {FIRETV_PACKAGE}")
        if "package:" in path_out:
            apk_path = path_out.split("package:")[1].strip()
            ls_out = adb_cmd(f"shell ls -l {apk_path}")
            parts = ls_out.split()
            for p in parts:
                if p.isdigit() and int(p) > 100000:
                    return int(p)
    except Exception:
        pass
    return 0


def run_cold_start_measurement(iterations: int = 3) -> dict:
    total_times = []
    this_times = []
    wait_times = []

    for i in range(iterations):
        # Force stop before starting
        adb_cmd(f"shell am force-stop {FIRETV_PACKAGE}")
        time.sleep(1.5)

        # Clear gfxinfo stats
        adb_cmd(f"shell dumpsys gfxinfo {FIRETV_PACKAGE} reset")

        # Launch and measure
        t0 = time.time()
        start_out = adb_cmd(f"shell am start -W -S -n {FIRETV_PACKAGE}/{FIRETV_ACTIVITY}")
        elapsed = (time.time() - t0) * 1000

        tt = None
        this_t = None
        wt = None
        for line in start_out.splitlines():
            if "TotalTime:" in line:
                tt = int(line.split(":")[1].strip())
            elif "ThisTime:" in line:
                this_t = int(line.split(":")[1].strip())
            elif "WaitTime:" in line:
                wt = int(line.split(":")[1].strip())

        if tt is not None:
            total_times.append(tt)
        if this_t is not None:
            this_times.append(this_t)
        if wt is not None:
            wait_times.append(wt)

        time.sleep(2)

    avg_total = sum(total_times) / len(total_times) if total_times else 0.0
    avg_this = sum(this_times) / len(this_times) if this_times else 0.0
    avg_wait = sum(wait_times) / len(wait_times) if wait_times else 0.0

    return {
        "iterations": iterations,
        "total_time_ms_runs": total_times,
        "total_time_ms_avg": round(avg_total, 1),
        "this_time_ms_avg": round(avg_this, 1),
        "wait_time_ms_avg": round(avg_wait, 1)
    }


def parse_gfxinfo(output: str) -> dict:
    data = {
        "total_frames": 0,
        "janky_frames": 0,
        "janky_pct": 0.0,
        "p50_ms": 0,
        "p90_ms": 0,
        "p95_ms": 0,
        "p99_ms": 0,
        "missed_vsync": 0,
        "slow_ui_thread": 0,
        "slow_bitmap_uploads": 0,
        "slow_draw_commands": 0,
        "deadline_missed": 0
    }

    for line in output.splitlines():
        line = line.strip()
        if line.startswith("Total frames rendered:"):
            data["total_frames"] = int(line.split(":")[1].strip())
        elif line.startswith("Janky frames:"):
            m = re.search(r"(\d+)\s*\(([\d\.]+)%\)", line)
            if m:
                data["janky_frames"] = int(m.group(1))
                data["janky_pct"] = float(m.group(2))
        elif line.startswith("50th percentile:"):
            data["p50_ms"] = int(line.split(":")[1].replace("ms", "").strip())
        elif line.startswith("90th percentile:"):
            data["p90_ms"] = int(line.split(":")[1].replace("ms", "").strip())
        elif line.startswith("95th percentile:"):
            data["p95_ms"] = int(line.split(":")[1].replace("ms", "").strip())
        elif line.startswith("99th percentile:"):
            data["p99_ms"] = int(line.split(":")[1].replace("ms", "").strip())
        elif line.startswith("Number Missed Vsync:"):
            data["missed_vsync"] = int(line.split(":")[1].strip())
        elif line.startswith("Number Slow UI thread:"):
            data["slow_ui_thread"] = int(line.split(":")[1].strip())
        elif line.startswith("Number Slow bitmap uploads:"):
            data["slow_bitmap_uploads"] = int(line.split(":")[1].strip())
        elif line.startswith("Number Slow issue draw commands:"):
            data["slow_draw_commands"] = int(line.split(":")[1].strip())
        elif line.startswith("Number Frame deadline missed:"):
            data["deadline_missed"] = int(line.split(":")[1].strip())

    return data


def run_benchmark():
    print("=" * 72)
    print("   ÆONIX PRISM // Ticket P0-1: Fire TV View Inflation Benchmark")
    print("=" * 72)

    # 1. Measure Cold Start
    print("\n[1/3] Benchmarking Cold Start Launch Latency (3 iterations)...")
    cold_start = run_cold_start_measurement(iterations=3)
    print(f"  -> Average TotalTime (first frame rendered): {cold_start['total_time_ms_avg']} ms")
    print(f"  -> Average ThisTime: {cold_start['this_time_ms_avg']} ms")
    print(f"  -> Individual runs: {cold_start['total_time_ms_runs']} ms")

    # 2. Measure Cold-Start Frame Jank
    print("\n[2/3] Extracting Cold-Start Frame Profile & Jank Breakdown...")
    # Cold start fresh and grab gfxinfo immediately after launch
    adb_cmd(f"shell am force-stop {FIRETV_PACKAGE}")
    time.sleep(1.5)
    adb_cmd(f"shell dumpsys gfxinfo {FIRETV_PACKAGE} reset")
    adb_cmd(f"shell am start -W -S -n {FIRETV_PACKAGE}/{FIRETV_ACTIVITY}")
    time.sleep(2)
    cold_gfx = parse_gfxinfo(adb_cmd(f"shell dumpsys gfxinfo {FIRETV_PACKAGE}"))

    print(f"  -> Total Frames on Cold Start: {cold_gfx['total_frames']}")
    print(f"  -> Janky Frames: {cold_gfx['janky_frames']} ({cold_gfx['janky_pct']}%)")
    print(f"  -> Missed VSYNC Count: {cold_gfx['missed_vsync']}")
    print(f"  -> Slow UI Thread Frames: {cold_gfx['slow_ui_thread']}")
    print(f"  -> 50th Percentile Frame Time: {cold_gfx['p50_ms']} ms")
    print(f"  -> 90th Percentile Frame Time: {cold_gfx['p90_ms']} ms")
    print(f"  -> 95th Percentile Frame Time: {cold_gfx['p95_ms']} ms")
    print(f"  -> 99th Percentile Frame Time: {cold_gfx['p99_ms']} ms")

    # 3. Time to Interactive D-pad Navigation
    print("\n[3/3] Measuring Time to Interactive D-pad Navigation & Steady-State...")
    adb_cmd(f"shell am force-stop {FIRETV_PACKAGE}")
    time.sleep(1.5)
    adb_cmd(f"shell dumpsys gfxinfo {FIRETV_PACKAGE} reset")
    
    t_start = time.time()
    adb_cmd(f"shell am start -n {FIRETV_PACKAGE}/{FIRETV_ACTIVITY}")
    
    # Poll for window focus
    t_focused = 0.0
    for _ in range(50):
        w = adb_cmd("shell dumpsys window | grep mCurrentFocus")
        if FIRETV_PACKAGE in w:
            t_focused = (time.time() - t_start) * 1000
            break
        time.sleep(0.05)
    
    # Inject D-pad keyevent and measure interaction response
    t_dpad_start = time.time()
    adb_cmd("shell input keyevent 20") # DPAD_DOWN
    t_dpad_elapsed = (time.time() - t_dpad_start) * 1000
    time_to_interactive = t_focused + t_dpad_elapsed

    print(f"  -> Time to Focused Window: {t_focused:.1f} ms")
    print(f"  -> D-Pad Injection Latency: {t_dpad_elapsed:.1f} ms")
    print(f"  -> Time to Interactive D-Pad Navigation: {time_to_interactive:.1f} ms")

    # Steady-state rendering: inject 20 navigation movements and record steady-state gfxinfo
    adb_cmd(f"shell dumpsys gfxinfo {FIRETV_PACKAGE} reset")
    for key in [20, 20, 19, 19, 21, 22, 21, 22, 20, 19]:
        adb_cmd(f"shell input keyevent {key}")
        time.sleep(0.08)
    
    steady_gfx = parse_gfxinfo(adb_cmd(f"shell dumpsys gfxinfo {FIRETV_PACKAGE}"))
    pss = get_firetv_pss()
    apk_sz = get_apk_size()

    print(f"\n[Steady-State Profile (D-pad Navigation)]")
    print(f"  -> Steady Total Frames: {steady_gfx['total_frames']}")
    print(f"  -> Steady Janky Frames: {steady_gfx['janky_frames']} ({steady_gfx['janky_pct']}%)")
    print(f"  -> Steady p50: {steady_gfx['p50_ms']} ms | p90: {steady_gfx['p90_ms']} ms | p95: {steady_gfx['p95_ms']} ms | p99: {steady_gfx['p99_ms']} ms")
    print(f"  -> PSS Memory: {pss:,} KB (~{pss/1024:.2f} MB)")
    print(f"  -> APK Size: {apk_sz:,} bytes (~{apk_sz/(1024*1024):.2f} MB)")

    result = {
        "cold_start": cold_start,
        "cold_start_gfx": cold_gfx,
        "time_to_interactive_ms": round(time_to_interactive, 1),
        "steady_state_gfx": steady_gfx,
        "pss_kb": pss,
        "apk_size_bytes": apk_sz
    }

    return result


if __name__ == "__main__":
    res = run_benchmark()
    if len(sys.argv) > 1:
        out_file = sys.argv[1]
    else:
        out_file = "/data/data/com.termux/files/home/aeonix-verification/post-rc1/evidence/p0_1_optimized_benchmark.json"
    os.makedirs(os.path.dirname(out_file), exist_ok=True)
    with open(out_file, "w") as f:
        json.dump(res, f, indent=2)
    print(f"\nBenchmark saved to: {out_file}")
