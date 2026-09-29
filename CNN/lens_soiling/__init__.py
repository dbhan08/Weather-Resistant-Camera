"""Tile-level lens soiling classifier (clean / water / ice) for the
Weather-Resistant Camera.  See CNN/README.md for the design."""

CLASSES = ("clean", "water", "ice")
TILE = 64  # input tile side in pixels

__all__ = ["CLASSES", "TILE"]
