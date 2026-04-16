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
`sudo apt update`

`sudo apt install build-essential`
## Installation
### 1. Clone the repository
`git clone https://github.com/JikruKakru/crud-app`

`cd crud-app`
### 2. Install NVM (Node Version Manager)
`curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.1/install.sh | bash`
### 3. Install Node.js with nvm
`nvm install`

`nvm use`

Verify version:
`node -v`

Should be:
`v18.x.x`
### 4. Install dependencies
`npm install`
### 5. Start the application
`npm run start`
### 6. Seed the database (optional)
`npm run seed`
## Usage
Open your browser and navigate to:
`http://<your-ip>:3000`

You can:
* Add items
* View items
* Update items
* Delete items
