"""Parsing and formatting money. All amounts are stored as integer cents."""


def parse_amount(text: str) -> int:
    """Parse strings like "$1,234.50", "-$3", "12.5" into integer cents."""
    s = text.strip()
    negative = s.startswith("-")
    s = s.lstrip("-").lstrip("$")
    if "." in s:
        dollars, cents = s.split(".", 1)
        cents = (cents + "00")[:2]
    else:
        dollars, cents = s, "00"
    value = int(dollars or "0") * 100 + int(cents)
    return -value if negative else value


def format_cents(cents: int) -> str:
    """Format integer cents as "$1,234.50" or "-$3.00"."""
    dollars, rem = divmod(cents, 100)
    return f"${dollars:,}.{rem:02d}"
