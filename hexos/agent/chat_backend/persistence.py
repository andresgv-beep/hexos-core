"""Inicialización del almacén existente; no introduce migraciones nuevas."""
from __future__ import annotations

from .. import procedures, workflow, notes, devices


def initialize(store):
    store.db.executescript('''
        CREATE TABLE IF NOT EXISTS conversation (
            id TEXT PRIMARY KEY, ts TEXT NOT NULL, role TEXT NOT NULL, text TEXT NOT NULL,
            model_text TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS documents (
            id TEXT PRIMARY KEY, ts TEXT NOT NULL, content TEXT NOT NULL, sha256 TEXT NOT NULL);
        -- Escrituras cuyo efecto no se sabe: el tiempo se agotó y no consta si
        -- llegaron a ejecutarse. Sobreviven al turno a propósito. Se cierran con
        -- una LECTURA que aclare el estado, nunca repitiendo la escritura.
        CREATE TABLE IF NOT EXISTS pending_effects (
            id TEXT PRIMARY KEY, ts TEXT NOT NULL, device TEXT NOT NULL,
            target TEXT NOT NULL, action TEXT NOT NULL, turn_id TEXT NOT NULL,
            resolved_at TEXT, resolved_state TEXT);
        CREATE TABLE IF NOT EXISTS tool_events (
            seq INTEGER PRIMARY KEY, turn_id TEXT NOT NULL, ts TEXT NOT NULL,
            body TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS generation_events (
            seq INTEGER PRIMARY KEY, turn_id TEXT NOT NULL, ts TEXT NOT NULL,
            body TEXT NOT NULL);
        -- Mensajes que PARECÍAN contar algo personal y que el portón de hechos
        -- descartó sin gastar una generación. No es una traza del turno: es el
        -- material con el que ensanchar el patrón con evidencia en vez de a ojo,
        -- porque un descarte no deja ni rastro en la conversación. Acotada a las
        -- últimas filas: es una muestra, no un archivo.
        CREATE TABLE IF NOT EXISTS fact_gate_skips (
            turn_id TEXT PRIMARY KEY, ts TEXT NOT NULL, text TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS progress_events (
            id TEXT PRIMARY KEY, turn_id TEXT NOT NULL, ts TEXT NOT NULL, text TEXT NOT NULL);
    ''')
    procedures.initialize(store)
    workflow.initialize(store)
    notes.initialize(store)
    devices.initialize(store)
