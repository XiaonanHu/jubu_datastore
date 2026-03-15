from enum import Enum


class ConversationState(Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    ENDED = "ended"
    FLAGGED = "flagged"
