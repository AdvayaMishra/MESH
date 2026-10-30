"""Typed local collection limits; never expose raw provider failures."""


class CloudInventoryLimit(RuntimeError):
    pass
