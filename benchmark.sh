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
CONNECTIONS=50
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

get_app_rss_kb() {
    local pids rss_sum

    pids=$(pgrep -f "$APP_PROC_PATTERN" 2>/dev/null)
    if [ -z "$pids" ]; then
        echo 0
        return
    fi

    rss_sum=$(ps -o rss= -p $pids 2>/dev/null | awk '{sum += $1} END {print sum + 0}')
    echo "$rss_sum"
}

# -----------------------------
# WARM-UP
# -----------------------------
echo "Reset + warm-up..."
reset_db
assert_backend_ready
autocannon -c 10 -d 10 "$BASE_URL" > /dev/null

# -----------------------------
# FUNCTION: RUN TEST
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

        # ✅ Reset BEFORE EACH RUN
        reset_db
        assert_backend_ready

        RUN_DIR="$TEST_DIR/run_$i"
        mkdir -p "$RUN_DIR"

        TOTAL_RAM=$(free -k | awk '/^Mem:/ {print $2}')

        # -----------------------------
        # IDLE BASELINE SNAPSHOT
        # -----------------------------
        vmstat 1 > "$RUN_DIR/idle_vmstat.txt" &
        IDLE_VMSTAT_PID=$!

        (
            while true; do
                if ! kill -0 $IDLE_VMSTAT_PID 2>/dev/null || [ ! -d "$RUN_DIR" ]; then
                    break
                fi
                free -k | awk '/^Mem:/ {print $7}' >> "$RUN_DIR/idle_available_mem.log"
                get_app_rss_kb >> "$RUN_DIR/idle_app_mem.log"
                sleep 1
            done
        ) &
        IDLE_MEM_PID=$!

        sleep "$IDLE_SECONDS"

        kill $IDLE_VMSTAT_PID 2>/dev/null
        kill $IDLE_MEM_PID 2>/dev/null

        sleep 1

        # -----------------------------
        # START MONITORING
        # -----------------------------
        vmstat 1 > "$RUN_DIR/vmstat.txt" &
        VMSTAT_PID=$!

        iostat -x 1 > "$RUN_DIR/iostat.txt" &
        IOSTAT_PID=$!

        (
            while true; do
                if ! kill -0 $VMSTAT_PID 2>/dev/null || [ ! -d "$RUN_DIR" ]; then
                    break
                fi
                free -k | awk '/^Mem:/ {print $7}' >> "$RUN_DIR/available_mem.log"
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
                -m $METHOD \
                -j "$URL" > "$RUN_DIR/load.json"

        else
            autocannon -c $CONNECTIONS -d $DURATION \
                -m $METHOD \
                -H "Content-Type: application/json" \
                -b "$BODY" \
                -j "$URL" > "$RUN_DIR/load.json"
        fi

        # -----------------------------
        # STOP MONITORING
        # -----------------------------
        kill $VMSTAT_PID 2>/dev/null
        kill $IOSTAT_PID 2>/dev/null
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
                jq -r '"Req/sec: \(.requests.average) | Latency avg: \(.latency.average) ms | Latency p97.5: \((.latency.p97_5 // .latency.p99 // .latency.p90 // .latency.max // 0)) ms | Latency p99: \((.latency.p99 // .latency.max // 0)) ms | Max: \(.latency.max) ms"' "$RUN_DIR/load.json"
            fi

            awk 'NR > 2 && $15 ~ /^[0-9]+$/ {
                usage = 100 - $15;
                sum += usage;
                if (usage > max) max = usage;
                count++
            }
            END {
                if (count > 0)
                    printf "Avg CPU: %.2f%% | Peak CPU: %.2f%%\n", sum/count, max
            }' "$RUN_DIR/vmstat.txt"

            awk -v total="$TOTAL_RAM" '{
                used = (total - $1)/1024;
                sum += used;
                if (used > max) max = used;
                count++
            }
            END {
                if (count > 0)
                    printf "Avg RAM: %.2f MB | Peak RAM: %.2f MB\n", sum/count, max
            }' "$RUN_DIR/available_mem.log"

            awk '{
                used = $1 / 1024;
                sum += used;
                if (used > max) max = used;
                count++
            }
            END {
                if (count > 0)
                    printf "App RAM: %.2f MB | App peak RAM: %.2f MB\n", sum/count, max
            }' "$RUN_DIR/app_mem.log"

            awk 'NR > 2 && $15 ~ /^[0-9]+$/ {
                idle += $15;
                count++
            }
            END {
                if (count > 0)
                    printf "Idle CPU: %.2f%%\n", idle/count
            }' "$RUN_DIR/idle_vmstat.txt"

            awk '{
                available = $1 / 1024;
                sum += available;
                count++
            }
            END {
                if (count > 0)
                    printf "Idle RAM: %.2f MB\n", sum/count
            }' "$RUN_DIR/idle_available_mem.log"

            awk '{
                used = $1 / 1024;
                sum += used;
                count++
            }
            END {
                if (count > 0)
                    printf "Idle App RAM: %.2f MB\n", sum/count
            }' "$RUN_DIR/idle_app_mem.log"

            awk '
                $1 !~ /^(Linux|avg-cpu:|Device|loop|sr)/ && $NF ~ /^[0-9.]+$/ {
                    util = $NF + 0;
                    sum += util;
                    if (util > max) max = util;
                    count++;
                }
                END {
                    if (count > 0)
                        printf "Disk util: %.2f%% | Disk peak util: %.2f%%\n", sum/count, max;
                }' "$RUN_DIR/iostat.txt"

        } > "$SUMMARY"

    done
}

# -----------------------------
# RUN TESTS
# -----------------------------
run_test "CREATE" "POST" "$BASE_URL" '{"name":"test"}'
run_test "READ"   "GET"  "$BASE_URL" ""

# dynamic IDs still fine
ITEM_ID=1
run_test "UPDATE" "PUT" "$BASE_URL/$ITEM_ID" '{"name":"updated"}'
run_test "DELETE" "DELETE" "$BASE_URL/$ITEM_ID" ""

echo "========================================"
echo " Benchmark complete!"
echo " Results stored in: $OUTPUT_ROOT"
echo "========================================"