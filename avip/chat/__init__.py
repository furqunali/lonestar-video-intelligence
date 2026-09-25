"""Chat-support subsystem for the AI Video-Intelligence platform.

A full, offline-first support assistant: a one-click chat widget anyone can open,
an assistant that answers from the platform's own data and can EXECUTE actions,
gated by a Manager -> Director approval workflow, with the complete chat history,
actions, approvals and per-user memory persisted to a database.

Modules
    store      — SQLite persistence (sessions, messages, action_requests, approvals, memory)
    roles      — role hierarchy (staff < manager < director < admin)
    actions    — typed action registry (permission + approval chain + handlers)
    approvals  — approval workflow engine (create -> approve chain -> execute)
    memory     — per-user persistent memory
    engine     — assistant engine (Strategy: offline RuleEngine + pluggable LLMEngine)
    service    — orchestrates everything (handle_message / approve / history)
    server     — zero-dependency stdlib HTTP server + REST API + serves the widget

Design: offline/on-prem, no cloud, no API key required (LLM is optional/pluggable);
fail-soft; every message/action/approval durably saved.
"""
from __future__ import annotations

__all__ = ["store", "roles", "actions", "approvals", "memory", "engine", "service"]
