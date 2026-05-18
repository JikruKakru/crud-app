# CRUD App (Node.js + Express + SQLite)
## Overview
This project is a simple CRUD web application built using:
* Node.js
* Express.js
* SQLite

The project was made for benchmarking and comparing Virtual Machines and LXC containers in Proxmox.
## Requirements
* Node.js v18.x
* npm
* nvm
### Linux build tools (required for better-sqlite3)
```bash
sudo apt update
sudo apt install build-essential
```
## Installation
### 1. Clone the repository
```bash
git clone https://github.com/JikruKakru/crud-app
cd crud-app
```
### 2. Install NVM (Node Version Manager)
```bash
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.1/install.sh | bash
```
### 3. Install Node.js with nvm
```bash
nvm install
nvm use
```

Verify version:
```bash
node -v
```

Should output: `v18.x.x`
### 4. Install dependencies
```bash
npm install
```

### 5. Start the application
```bash
npm start
```

The server will start on port 3000 and be accessible at `http://<your-ip>:3000`

## Usage

You can:
* Add items
* View items
* Update items
* Delete items

### Web Interface
Simply navigate to `http://<your-ip>:3000` and use the interface to add, edit, and delete items.

### API Endpoints

#### Create an Item
```bash
curl -X POST http://localhost:3000/items \
  -H "Content-Type: application/json" \
  -d '{"name": "My Item"}'
```
**Response:** `{ "id": 1 }`

#### Get All Items
```bash
curl http://localhost:3000/items
```
**Response:** `[{ "id": 1, "name": "My Item" }, ...]`

#### Update an Item
```bash
curl -X PUT http://localhost:3000/items/1 \
  -H "Content-Type: application/json" \
  -d '{"name": "Updated Item"}'
```
**Response:** `{ "updated": 1 }`

#### Delete an Item
```bash
curl -X DELETE http://localhost:3000/items/1
```
**Response:** `{ "deleted": 1 }`

#### Reset Database
Clears all items, resets the ID counter, and seeds with 1000 random items. Useful for benchmarking to ensure consistent state between test runs.

```bash
curl -X POST http://localhost:3000/reset
```
**Response:** `{ "reset": true, "seeded": 1000 }`

## Benchmarking

This project includes a comprehensive benchmarking script for performance testing.

### Prerequisites
```bash
npm install -g autocannon
```

### Run Benchmarks
```bash
./benchmark.sh
```

The script will:
* Run 5 iterations (configurable via `RUNS` variable)
* Test CREATE, READ, UPDATE, DELETE operations
* Collect metrics:
  - **Requests/sec:** Throughput (requests per second)
  - **Latency:** Response time (average, p97.5, p99, max)
  - **CPU:** Average and peak CPU usage
  - **RAM:** Average and peak memory usage
* Save results to `benchmark_results_YYYYMMDD_HHMMSS/`

### Output
Each test operation (CREATE, READ, UPDATE, DELETE) generates:
* `all_runs.csv` - Aggregated results from all runs
* `averages.csv` - Average metrics across runs
* `std_dev.csv` - Standard deviation across runs
* Individual run directories with detailed metrics:
  - `load.json` - Raw autocannon output
  - `vmstat.txt` - CPU and memory statistics
  - `iostat.txt` - I/O statistics
  - `summary.txt` - Human-readable summary
