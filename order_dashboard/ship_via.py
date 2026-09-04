"""Sage Ship Via codes, from Lauren's list (Sage 100 Ship Via code list)."""

from __future__ import annotations

SHIP_VIA_CODES: list[tuple[str, str]] = [
    ("M", "Mail"),
    ("Z", "Mail Canada"),
    ("U", "UPS Ground"),
    ("P", "Pick Up (customer supplied label)"),
    ("S", "UPS 3 Day"),
    ("B", "UPS Blue, 2 Day"),
    ("R", "UPS Next Day, 10:30 AM"),
    ("R-AM", "UPS Next Day, 8:30 AM"),
    ("R-S", "UPS Next Day Air Saver"),
    ("E", "Express Mail"),
    ("Q", "Priority Mail"),
    ("F", "FedEx"),
    ("D", "Bill DHL Account"),
    ("G", "Bill UPS Account"),
    ("H", "Bill FedEx Account"),
    ("T", "BTX Freight"),
    ("V", "Check with Customer"),
    ("X", "Billing Only, Do Not Ship"),
]

SHIP_VIA_CODE_SET: set[str] = {code for code, _ in SHIP_VIA_CODES}
