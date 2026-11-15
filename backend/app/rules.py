"""Every fit-rule value, one place (handoff section 5). Lengths in inches."""

# --- Hard rules ---
PATH_WIDTH = 36.0  # clear path from the door. Hunker (3 ft); Comfyco.
BED_OPEN_SIDE = 24.0  # open side of the bed. Hunker (2 ft); Houzz (20-22 in).
# A twin may sit against a wall: one open long side is enough.
FRONT_CLEARANCE = 24.0  # in front of dresser and closet. Hunker (2 ft).
CHAIR_BACK = 18.0  # behind the desk chair. Hunker (18 in).

# --- Soft rules (percent of floor covered by furniture) ---
# Adapted from the 60/40 rule (Apartment Therapy, Comfyco). Our own number.
COVERAGE_WARN = 40.0  # warn above this
COVERAGE_FLAG = 45.0  # flag above this

# --- Ricky's decisions, Nov 15 (docs/decisions-log.md) ---
PATH_END_FRACTION = 0.5  # the door path runs to the room's center line (depth / 2)
CHAIR_ASSUMED = (
    20.0,
    20.0,
)  # desk chairs rarely list dimensions: assumed, labeled in the UI

EPS = 1e-9  # float slack so "exactly 18 in" passes
