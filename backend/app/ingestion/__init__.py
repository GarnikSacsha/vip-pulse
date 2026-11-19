"""Import of source files into the normalized domain model.

Flow: adapter (format-specific parsing) -> pipeline (generic checks, dedupe,
referential integrity) -> store (idempotent upsert into the database).
"""
