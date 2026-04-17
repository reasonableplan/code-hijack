from __future__ import annotations


def up() -> str:
    return "CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT NOT NULL);"


def down() -> str:
    return "DROP TABLE IF EXISTS users;"
