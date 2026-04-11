const express = require('express');
const bodyParser = require('body-parser');
const Database = require('better-sqlite3');

const app = express();
const port = 3000;

app.use(bodyParser.json());
app.use(express.static('public'));

const db = new Database('database.db');

db.prepare(`
  CREATE TABLE IF NOT EXISTS items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT
  )
`).run();

// CREATE
app.post('/items', (req, res) => {
    const { name } = req.body;
    const result = db.prepare(
        'INSERT INTO items (name) VALUES (?)'
    ).run(name);

    res.send({ id: result.lastInsertRowid });
});

// READ
app.get('/items', (req, res) => {
    const rows = db.prepare('SELECT * FROM items').all();
    res.send(rows);
});

// UPDATE
app.put('/items/:id', (req, res) => {
    const { name } = req.body;

    const result = db.prepare(
        'UPDATE items SET name=? WHERE id=?'
    ).run(name, req.params.id);

    res.send({ updated: result.changes });
});

// DELETE
app.delete('/items/:id', (req, res) => {
    const result = db.prepare(
        'DELETE FROM items WHERE id=?'
    ).run(req.params.id);

    res.send({ deleted: result.changes });
});

app.listen(port, '0.0.0.0', () => {
    console.log(`Server running on port ${port}`);
});
