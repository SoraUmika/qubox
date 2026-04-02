# Transitions

Pulse name resolution and transition family management.

## Overview

The transitions module maps logical transition names (like `"x180"`, `"ef_x180"`)
to physical pulse configurations. It handles the naming conventions and family
relationships between pulses.

## Transition Families

| Family | Prefix | Transitions | Description |
|--------|--------|-------------|-------------|
| GE | (none) | `x180`, `x90`, `y180`, `y90`, `-x90`, `-y90` | Ground ↔ Excited |
| EF | `ef_` | `ef_x180`, `ef_x90`, `ef_y180`, `ef_y90` | Excited ↔ Second Excited |
| Sideband | `sb_` | `sb_x180`, `sb_x90` | Sideband transitions |
| Custom | user-defined | user-defined | User-registered transitions |

## Pulse Name Resolution

```python
from qubox.calibration.transitions import resolve_pulse_name

# Standard resolution
resolve_pulse_name("x180")       # → PulseCalibration for π pulse
resolve_pulse_name("x90")        # → PulseCalibration for π/2 pulse
resolve_pulse_name("ef_x180")    # → PulseCalibration for EF π pulse

# With family prefix
resolve_pulse_name("x180", family="ge")  # Explicit GE family
resolve_pulse_name("x180", family="ef")  # EF family
```

## Relationship Between Pulses

Certain pulses are derived from others:

| Base Pulse | Derived | Relationship |
|------------|---------|-------------|
| `x180` | `x90` | `amp = x180.amp / 2` |
| `x180` | `-x90` | `amp = -x180.amp / 2` |
| `y180` | `y90` | `amp = y180.amp / 2` |
| `ef_x180` | `ef_x90` | `amp = ef_x180.amp / 2` |

When you calibrate `x180`, the store automatically updates `x90` and `-x90`.
