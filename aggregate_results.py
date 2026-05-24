import os
import pandas as pd
from datetime import datetime
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def discover_benchmark_dirs(search_root):
    candidates = []

    for name in os.listdir(search_root):
        full_path = os.path.join(search_root, name)
        if not os.path.isdir(full_path):
            continue
        if not name.startswith("benchmark_results_"):
            continue

        timestamp_str = name.replace("benchmark_results_", "", 1)
        try:
            timestamp = datetime.strptime(timestamp_str, "%Y%m%d_%H%M%S")
        except ValueError:
            # If naming is unexpected, keep it but sort it after valid timestamps.
            timestamp = datetime.max

        candidates.append((name, full_path, timestamp))

    # Sort by timestamp (oldest -> newest), then by name for stable ordering.
    candidates.sort(key=lambda x: (x[2], x[0]))
    return candidates


def choose_benchmark_dir(candidates):
    if not candidates:
        print("No benchmark_results_* folders found.")
        sys.exit(1)

    print("\nAvailable benchmark result folders:")
    for idx, (name, _, timestamp) in enumerate(candidates, start=1):
        if timestamp == datetime.max:
            date_label = "unknown date"
        else:
            date_label = timestamp.strftime("%Y-%m-%d %H:%M:%S")
        print(f"{idx}. {name} ({date_label})")

    if len(candidates) <= 9:
        # Windows keypress mode: select using one numeric key, no Enter needed.
        try:
            import msvcrt
        except ImportError:
            msvcrt = None

        if msvcrt is not None:
            print("\nPress a number key to choose a benchmark folder...")
            while True:
                key = msvcrt.getch()
                if not key:
                    continue
                char = key.decode("utf-8", errors="ignore")
                if char.isdigit():
                    choice = int(char)
                    if 1 <= choice <= len(candidates):
                        print(choice)
                        return candidates[choice - 1][1]

    # Fallback and multi-digit support.
    while True:
        raw = input("\nEnter the number of the benchmark folder to analyze: ").strip()
        if raw.isdigit():
            choice = int(raw)
            if 1 <= choice <= len(candidates):
                return candidates[choice - 1][1]
        print("Invalid selection. Please enter one of the listed numbers.")


ROOT_DIR = choose_benchmark_dir(discover_benchmark_dirs(BASE_DIR))

results = []

def parse_optional_float(value):
    cleaned = (
        value.replace(" ms", "")
        .replace(" MB", "")
        .replace(" KB/s", "")
        .replace("%", "")
        .strip()
    )
    if cleaned.lower() in {"", "null", "none", "nan"}:
        return float("nan")
    return float(cleaned)


def parse_summary(summary_path):
    data = {}

    with open(summary_path) as f:
        for line in f:
            line = line.strip()
            
            if not line or line.startswith("---") or line.endswith("only"):
                # Skip empty lines, separators, and section headers
                continue

            if line.startswith("Boot time:"):
                data["boot_time"] = line.split(":", 1)[1].strip()

            elif line.startswith("Req/sec:"):
                data["req_sec"] = parse_optional_float(line.split(":", 1)[1])

            elif line.startswith("Latency avg:"):
                data["lat_avg"] = parse_optional_float(line.split(":", 1)[1])

            elif line.startswith("Latency p97.5:"):
                data["lat_p97_5"] = parse_optional_float(line.split(":", 1)[1])

            elif line.startswith("Latency p99:"):
                data["lat_p99"] = parse_optional_float(line.split(":", 1)[1])

            elif line.startswith("Max latency:"):
                data["lat_max"] = parse_optional_float(line.split(":", 1)[1])

            elif line.startswith("Avg CPU:"):
                data["cpu_avg"] = parse_optional_float(line.split(":", 1)[1])

            elif line.startswith("Peak CPU:"):
                data["cpu_peak"] = parse_optional_float(line.split(":", 1)[1])

            elif line.startswith("Avg RAM:"):
                data["ram_avg"] = parse_optional_float(line.split(":", 1)[1])

            elif line.startswith("Peak RAM:"):
                data["ram_peak"] = parse_optional_float(line.split(":", 1)[1])

            elif line.startswith("Idle RAM:"):
                data["idle_app_ram"] = parse_optional_float(line.split(":", 1)[1])

            elif line.startswith("Avg Read:"):
                data["disk_read_avg"] = parse_optional_float(line.split(":", 1)[1])

            elif line.startswith("Avg Write:"):
                data["disk_write_avg"] = parse_optional_float(line.split(":", 1)[1])

    return data


# -------------------------
# LOAD DATA
# -------------------------
for test_type in os.listdir(ROOT_DIR):
    test_path = os.path.join(ROOT_DIR, test_type)

    if not os.path.isdir(test_path):
        continue

    for run in os.listdir(test_path):
        run_path = os.path.join(test_path, run)
        summary_file = os.path.join(run_path, "summary.txt")

        if os.path.exists(summary_file):
            parsed = parse_summary(summary_file)
            parsed["test"] = test_type
            parsed["run"] = run
            results.append(parsed)

df = pd.DataFrame(results)

if df.empty:
    print("No data found. Check your benchmark_results folder.")
    exit()

# Save raw data
df.to_csv(os.path.join(ROOT_DIR, "all_runs.csv"), index=False)

# -------------------------
# COMPUTE STATS
# -------------------------
grouped = df.groupby("test")

avg_df = grouped.mean(numeric_only=True)
std_df = grouped.std(numeric_only=True)
boot_df = grouped["boot_time"].first() if "boot_time" in df.columns else None

avg_df.to_csv(os.path.join(ROOT_DIR, "averages.csv"))
std_df.to_csv(os.path.join(ROOT_DIR, "std_dev.csv"))

# -------------------------
# PRETTY PRINT FUNCTION
# -------------------------
def print_summary(avg, std):
    print("\n========================================")
    print("        BENCHMARK SUMMARY")
    print("========================================\n")

    for test in avg.index:
        print(f"--- {test} ---")

        if boot_df is not None and test in boot_df.index:
            print(f"Boot time    : {boot_df.loc[test]}")

        print(f"Requests/sec : {avg.loc[test, 'req_sec']:.2f} ± {std.loc[test, 'req_sec']:.2f}")
        print(f"Avg Latency  : {avg.loc[test, 'lat_avg']:.2f} ms")

        if "lat_p97_5" in avg.columns:
            print(f"P97.5 Latency: {avg.loc[test, 'lat_p97_5']:.2f} ms")

        if "lat_p99" in avg.columns:
            print(f"P99 Latency  : {avg.loc[test, 'lat_p99']:.2f} ms")

        print(f"Max Latency  : {avg.loc[test, 'lat_max']:.2f} ms")

        print(f"App CPU      : {avg.loc[test, 'cpu_avg']:.2f}% (peak {avg.loc[test, 'cpu_peak']:.2f}%)")
        print(f"App Memory   : {avg.loc[test, 'ram_avg']:.2f} MB (peak {avg.loc[test, 'ram_peak']:.2f} MB)")

        if "idle_app_ram" in avg.columns:
            print(f"Idle App RAM : {avg.loc[test, 'idle_app_ram']:.2f} MB")

        if "disk_read_avg" in avg.columns:
            print(f"Disk Read    : {avg.loc[test, 'disk_read_avg']:.2f} KB/s")

        if "disk_write_avg" in avg.columns:
            print(f"Disk Write   : {avg.loc[test, 'disk_write_avg']:.2f} KB/s")

        print("")

    # Highlight best performance
    best_req = avg["req_sec"].idxmax()
    lowest_latency = avg["lat_avg"].idxmin()

    print("========================================")
    print("            KEY INSIGHTS")
    print("========================================")
    print(f"Highest throughput : {best_req}")
    print(f"Lowest latency     : {lowest_latency}")
    print("========================================\n")


# -------------------------
# RUN OUTPUT
# -------------------------
print_summary(avg_df, std_df)

print("Saved files:")
print("- all_runs.csv")
print("- averages.csv")
print("- std_dev.csv")