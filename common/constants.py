"""
Constants for KidsChat.

This module defines all constants used throughout the application,
organized by domain and functionality.
"""

# Base Datastore Constants
MAX_RETRIES = 3  # Maximum number of retries for transient errors
RETRY_DELAY = 0.5  # Delay between retries (in seconds)

# Conversation Datastore Constants
DEFAULT_ARCHIVE_DAYS = 90  # Default days threshold for archiving old conversations

# Facts Datastore Constants
DEFAULT_FACT_EXPIRATION_DAYS = 30  # Default expiration for facts

# Profile Datastore Constants
DEFAULT_PROFILE_INACTIVITY_DAYS = 60  # Default inactivity days for profiles

# Story Datastore Constants
DEFAULT_STORY_VIEW_LIMIT = 10  # Default limit for story views
