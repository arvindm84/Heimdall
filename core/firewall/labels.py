"""Confidentiality labels: Public < Private < Confidential.

A session's label is the highest label of anything it has read, and it only goes
up (Denning's lattice model; FIDES and CaMeL track labels the same way). Later
steps use it to decide when a send or a cloud model call needs consent.
"""

from enum import IntEnum


class Label(IntEnum):
    PUBLIC = 0
    PRIVATE = 1
    CONFIDENTIAL = 2

    def __str__(self) -> str:
        # Lowercase, the same spelling as the contract and the event lines.
        return self.name.lower()


def from_contract(name: str) -> Label:
    """Map FolderAccess.label ("public" | "private" | "confidential") to a Label."""
    return Label[name.upper()]


def join(first: Label, second: Label) -> Label:
    """The label of data mixed from both: the higher of the two."""
    return max(first, second)
