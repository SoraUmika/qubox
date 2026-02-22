# qubox_v2/migration/__init__.py
"""Migration utilities for qubox_v2.

Provides tools for converting between config formats:
- ``pulses_converter``: pulses.json → pulse_specs.json
- ``strip_raw_artifacts``: remove shot-level raw payloads from persisted JSON
- Schema migrations via ``core.schemas.migrate_file``

See docs/SCHEMA_VERSIONING.md and docs/PULSE_SPEC_SCHEMA.md for details.
"""
