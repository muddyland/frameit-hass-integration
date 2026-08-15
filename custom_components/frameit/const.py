"""Constants for the FrameIT integration."""

DOMAIN = "frameit"

CONF_URL = "url"
CONF_USERNAME = "username"
CONF_PASSWORD = "password"

UPDATE_INTERVAL = 30  # seconds

CONTENT_MODE_POOL = "pool"
CONTENT_MODE_PINNED = "pinned"
CONTENT_MODE_NOW_PLAYING = "now-playing"
CONTENT_MODES = [CONTENT_MODE_POOL, CONTENT_MODE_PINNED, CONTENT_MODE_NOW_PLAYING]

# Bounds the server enforces on PATCH /api/frames/<id>.
MIN_INTERVAL_SECONDS = 10
MAX_INTERVAL_SECONDS = 86400

# Values of the frame's `agent_auth` field. 'secret' is the per-frame
# credential issued at registration; 'legacy' is the registration token being
# reused as a bearer by an agent that has not been updated yet.
AGENT_AUTH_SECRET = "secret"
AGENT_AUTH_LEGACY = "legacy"

# Server-wide security switches, exposed as config entities. Each entry is
# (settings key, entity name, icon). They are only created when the server
# actually reports the key, so an older server gets no dead switches.
SECURITY_SETTINGS: tuple[tuple[str, str, str], ...] = (
    ("strict_agent_auth", "Require agent authentication", "mdi:shield-key"),
    ("strict_frame_auth", "Require frame tokens", "mdi:shield-lock"),
    ("allow_bypass_frames", "Allow preview frames", "mdi:monitor-star"),
)
