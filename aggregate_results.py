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

def segment_value(segment):
    return segment.split(":", 1)[1].strip()


def parse_optional_float(value):
    cleaned = (
        value.replace(" ms", "")
        .replace(" MB", "")
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
            if line.startswith("Boot time:"):
                data["boot_time"] = line.split("Boot time:", 1)[1].strip()

            if "Req/sec" in line:
                parts = [part.strip() for part in line.strip().split("|")]
                data["req_sec"] = parse_optional_float(segment_value(parts[0]))
                data["lat_avg"] = parse_optional_float(segment_value(parts[1]))

                if len(parts) > 3:
                    data["lat_p97_5"] = parse_optional_float(segment_value(parts[2]))
                    data["lat_p99"] = parse_optional_float(segment_value(parts[3]))
                    data["lat_max"] = parse_optional_float(segment_value(parts[4]))
                else:
                    data["lat_max"] = parse_optional_float(segment_value(parts[2]))

            elif "Avg CPU" in line:
                parts = [part.strip() for part in line.strip().split("|")]
                data["cpu_avg"] = parse_optional_float(segment_value(parts[0]))
                data["cpu_peak"] = parse_optional_float(segment_value(parts[1]))

            elif "Avg RAM" in line:
                parts = [part.strip() for part in line.strip().split("|")]
                data["ram_avg"] = parse_optional_float(segment_value(parts[0]))
                data["ram_peak"] = parse_optional_float(segment_value(parts[1]))

            elif "App RAM" in line:
                parts = [part.strip() for part in line.strip().split("|")]
                if len(parts) >= 1:
                    data["app_ram_avg"] = parse_optional_float(segment_value(parts[0]))
                if len(parts) >= 2:
                    data["app_ram_peak"] = parse_optional_float(segment_value(parts[1]))

            elif "Idle CPU" in line:
                data["idle_cpu"] = parse_optional_float(line.split(":", 1)[1])

            elif "Idle RAM" in line:
                data["idle_ram"] = parse_optional_float(line.split(":", 1)[1])

            elif "Idle App RAM" in line:
                data["idle_app_ram"] = parse_optional_float(line.split(":", 1)[1])

            elif "Disk util" in line:
                parts = [part.strip() for part in line.strip().split("|")]
                data["disk_util_avg"] = parse_optional_float(segment_value(parts[0]))
                data["disk_util_peak"] = parse_optional_float(segment_value(parts[1]))

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

        print(f"CPU Usage    : {avg.loc[test, 'cpu_avg']:.2f}% (peak {avg.loc[test, 'cpu_peak']:.2f}%)")
        print(f"Memory Usage : {avg.loc[test, 'ram_avg']:.2f} MB (peak {avg.loc[test, 'ram_peak']:.2f} MB)")

        if "app_ram_avg" in avg.columns:
            print(f"App RAM      : {avg.loc[test, 'app_ram_avg']:.2f} MB (peak {avg.loc[test, 'app_ram_peak']:.2f} MB)")

        if "idle_cpu" in avg.columns:
            print(f"Idle CPU     : {avg.loc[test, 'idle_cpu']:.2f}%")

        if "idle_ram" in avg.columns:
            print(f"Idle RAM     : {avg.loc[test, 'idle_ram']:.2f} MB")

        if "idle_app_ram" in avg.columns:
            print(f"Idle App RAM : {avg.loc[test, 'idle_app_ram']:.2f} MB")

        if "disk_util_avg" in avg.columns:
            print(f"Disk I/O     : {avg.loc[test, 'disk_util_avg']:.2f}% avg util (peak {avg.loc[test, 'disk_util_peak']:.2f}%)")

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