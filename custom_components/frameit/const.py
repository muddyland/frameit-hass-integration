"""Constants for the FrameIT integration."""

DOMAIN = "frameit"

CONF_URL = "url"
CONF_USERNAME = "username"
CONF_PASSWORD = "password"

# Options-flow keys. The now-playing source is an entity_id rather than a
# per-frame setting because the server fans one global now-playing state out
# to every opted-in frame; the token is a secret, so it lives in the config
# entry rather than in a text entity anyone can read off the dashboard.
CONF_NOW_PLAYING_SOURCE = "now_playing_source"
CONF_NOW_PLAYING_TOKEN = "now_playing_token"

UPDATE_INTERVAL = 30  # seconds

CONTENT_MODE_POOL = "pool"
CONTENT_MODE_PINNED = "pinned"
CONTENT_MODES = [CONTENT_MODE_POOL, CONTENT_MODE_PINNED]

# States the server's /api/now-playing endpoint accepts.
NOW_PLAYING_STATES = ("playing", "paused", "idle", "off")
# The subset the server actually puts on a frame; everything else falls
# through to the frame's normal rotation.
NOW_PLAYING_ACTIVE_STATES = ("playing", "paused")

# media_content_type values, as documented for media_player, grouped by how
# the now-playing banners should read. Streaming apps are inconsistent about
# which they report — an episode played through Netflix on an Apple TV often
# arrives as plain "video" with no series fields at all — so the presence of
# media_series_title always wins over the content type, and a missing series
# title is never guessed at.
NOW_PLAYING_TV_CONTENT_TYPES = ("tvshow", "episode")
NOW_PLAYING_VIDEO_CONTENT_TYPES = ("movie", "video")
NOW_PLAYING_MUSIC_CONTENT_TYPE = "music"

# Mirrors the server default for now_playing_stale_seconds. Used only until
# the coordinator has read the real value out of /api/settings.
NOW_PLAYING_DEFAULT_STALE_SECONDS = 120
# The server treats art older than stale_seconds as cleared, so the reporter
# re-posts well inside that window. Half the window leaves room for one lost
# request before a long-playing track goes stale on the wall.
NOW_PLAYING_HEARTBEAT_RATIO = 0.5
NOW_PLAYING_MIN_HEARTBEAT_SECONDS = 5
