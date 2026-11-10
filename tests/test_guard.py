"""The PreToolUse guard refuses secret reads and destructive git commands, and lets normal work through."""
import guard


def test_guard_selftest():
    guard.selftest()
