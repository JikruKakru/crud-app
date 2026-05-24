#!/bin/bash

# -----------------------------
# CLEANUP ON EXIT
# -----------------------------
cleanup() {
    echo "Cleaning up background processes..."
    kill 0 2>/dev/null
}
trap cleanup EXIT

# -----------------------------
# CONFIG
# -----------------------------
SERVER_IP=$(hostname -I | awk '{print $1}')
BASE_URL="http://${SERVER_IP}:3000/items"
RESET_URL="http://${SERVER_IP}:3000/reset"
BOOT_TIME=$(uptime -s 2>/dev/null || date)

DURATION=30
CONNECTIONS=100
RUNS=5
IDLE_SECONDS=5
APP_PROC_PATTERN="node app.js"

OUTPUT_ROOT="benchmark_results_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$OUTPUT_ROOT"

echo "========================================"
echo " Benchmark starting..."
echo " Output directory: $OUTPUT_ROOT"
echo "========================================"

# -----------------------------
# RESET FUNCTION
# -----------------------------
reset_db() {
    curl -s -X POST "$RESET_URL" > /dev/null
    sleep 1
}

# -----------------------------
# HEALTH CHECK
# -----------------------------
assert_backend_ready() {
    local item_count

    item_count=$(curl -s --max-time 5 "$BASE_URL" | jq 'length' 2>/dev/null)

    if [ -z "$item_count" ] || [ "$item_count" = "null" ] || [ "$item_count" -le 0 ]; then
        echo "Backend check failed: /items is empty or unreachable. Stopping benchmark."
        exit 1
    fi
}

# -----------------------------
# APP PID
# -----------------------------
get_app_pid() {
    # Find node process by exact name match to avoid shell wrappers
    pgrep "^node$" | tail -n 1
}

# -----------------------------
# APP RSS
# -----------------------------
get_app_rss_kb() {
    local pid

    pid=$(get_app_pid)

    if [ -z "$pid" ]; then
        echo 0
        return
    fi

    ps -o rss= -p "$pid" 2>/dev/null | awk '{print $1+0}'
}

# -----------------------------
# WARM-UP
# -----------------------------
echo "Reset + warm-up..."
reset_db
assert_backend_ready
autocannon -c 10 -d 10 "$BASE_URL" > /dev/null

# -----------------------------
# RUN TEST FUNCTION
# -----------------------------
run_test() {
    TEST_NAME=$1
    METHOD=$2
    URL=$3
    BODY=$4

    echo "Running $TEST_NAME..."

    TEST_DIR="$OUTPUT_ROOT/$TEST_NAME"
    mkdir -p "$TEST_DIR"

    for i in $(seq 1 $RUNS); do
        echo "  Run $i..."

        reset_db
        assert_backend_ready

        RUN_DIR="$TEST_DIR/run_$i"
        mkdir -p "$RUN_DIR"

        APP_PID=$(get_app_pid)

        if [ -z "$APP_PID" ]; then
            echo "Could not find app PID."
            exit 1
        fi

        # -----------------------------
        # IDLE BASELINE
        # -----------------------------
        pidstat -u -p "$APP_PID" 1 > "$RUN_DIR/idle_pidstat_cpu.txt" &
        IDLE_CPU_PID=$!

        (
            while true; do
                if ! kill -0 $IDLE_CPU_PID 2>/dev/null; then
                    break
                fi
                get_app_rss_kb >> "$RUN_DIR/idle_app_mem.log"
                sleep 1
            done
        ) &
        IDLE_MEM_PID=$!

        sleep "$IDLE_SECONDS"

        kill $IDLE_CPU_PID 2>/dev/null
        kill $IDLE_MEM_PID 2>/dev/null

        sleep 1

        # -----------------------------
        # START MONITORING
        # -----------------------------
        pidstat -u -p "$APP_PID" 1 > "$RUN_DIR/pidstat_cpu.txt" &
        CPU_PID=$!

        pidstat -d -p "$APP_PID" 1 > "$RUN_DIR/pidstat_disk.txt" &
        DISK_PID=$!

        (
            while true; do
                if ! kill -0 $CPU_PID 2>/dev/null; then
                    break
                fi
                get_app_rss_kb >> "$RUN_DIR/app_mem.log"
                sleep 1
            done
        ) &
        MEM_PID=$!

        sleep 2

        # -----------------------------
        # RUN LOAD TEST
        # -----------------------------
        if [ "$METHOD" = "GET" ]; then
            autocannon -c $CONNECTIONS -d $DURATION -j "$URL" > "$RUN_DIR/load.json"

        elif [ -z "$BODY" ]; then
            autocannon -c $CONNECTIONS -d $DURATION \
                -m "$METHOD" \
                -j "$URL" > "$RUN_DIR/load.json"

        else
            autocannon -c $CONNECTIONS -d $DURATION \
                -m "$METHOD" \
                -H "Content-Type: application/json" \
                -b "$BODY" \
                -j "$URL" > "$RUN_DIR/load.json"
        fi

        # -----------------------------
        # STOP MONITORING
        # -----------------------------
        kill $CPU_PID 2>/dev/null
        kill $DISK_PID 2>/dev/null
        kill $MEM_PID 2>/dev/null

        sleep 1

        # -----------------------------
        # SUMMARY
        # -----------------------------
        SUMMARY="$RUN_DIR/summary.txt"

        {
            echo "Run $i Summary"
            echo "----------------------------"
            echo "Boot time: $BOOT_TIME"

            if [ -f "$RUN_DIR/load.json" ]; then
                jq -r '
                    "Req/sec: \(.requests.average)",
                    "Latency avg: \(.latency.average) ms",
                    "Latency p97.5: \((.latency.p97_5 // .latency.p99 // 0)) ms",
                    "Latency p99: \((.latency.p99 // 0)) ms",
                    "Max latency: \(.latency.max) ms"
                ' "$RUN_DIR/load.json"
            fi

            echo ""

            echo "CPU (App only)"
            awk '
                $5 ~ /^[0-9.]+$/ && $6 ~ /^[0-9.]+$/ {
                    cpu=$5+$6
                    sum+=cpu
                    if(cpu>max) max=cpu
                    count++
                }
                END {
                    if(count>0)
                        printf "Avg CPU: %.2f%%\nPeak CPU: %.2f%%\n", sum/count, max
                }
            ' "$RUN_DIR/pidstat_cpu.txt"

            echo ""

            echo "Memory (App RSS)"
            awk '
                {
                    mem=$1/1024
                    sum+=mem
                    if(mem>max) max=mem
                    count++
                }
                END {
                    if(count>0)
                        printf "Avg RAM: %.2f MB\nPeak RAM: %.2f MB\n", sum/count, max
                }
            ' "$RUN_DIR/app_mem.log"

            echo ""

            echo "Idle App RAM"
            awk '
                {
                    mem=$1/1024
                    sum+=mem
                    count++
                }
                END {
                    if(count>0)
                        printf "Idle RAM: %.2f MB\n", sum/count
                }
            ' "$RUN_DIR/idle_app_mem.log"

            echo ""

            echo "Disk I/O (App only)"
            awk '
                $4 ~ /^[0-9.]+$/ && $5 ~ /^[0-9.]+$/ {
                    read+=$4
                    write+=$5
                    count++
                }
                END {
                    if(count>0)
                        printf "Avg Read: %.2f KB/s\nAvg Write: %.2f KB/s\n",
                            read/count, write/count
                }
            ' "$RUN_DIR/pidstat_disk.txt"

        } > "$SUMMARY"
    done
}

# -----------------------------
# RUN TESTS
# -----------------------------
run_test "CREATE" "POST" "$BASE_URL" '{"name":"test"}'
run_test "READ"   "GET"  "$BASE_URL" ""
run_test "UPDATE" "PUT"  "$BASE_URL/1" '{"name":"updated"}'
run_test "DELETE" "DELETE" "$BASE_URL/1" ""

echo "========================================"
echo " Benchmark complete!"
echo " Results stored in: $OUTPUT_ROOT"
echo "========================================"
