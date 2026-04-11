const sqlite3 = require('sqlite3').verbose();

const db = new sqlite3.Database('./database.db');

const TOTAL = 1000; // number of rows

function randomString(length) {
    const chars = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789';
    let result = '';
    for (let i = 0; i < length; i++) {
        result += chars.charAt(Math.floor(Math.random() * chars.length));
    }
    return result;
}

db.serialize(() => {
    db.run("DELETE FROM items"); // clear table first

    const stmt = db.prepare("INSERT INTO items (name) VALUES (?)");

    for (let i = 0; i < TOTAL; i++) {
        stmt.run(randomString(20));
    }

    stmt.finalize();
});

db.close();

console.log(`Inserted ${TOTAL} random rows.`);
