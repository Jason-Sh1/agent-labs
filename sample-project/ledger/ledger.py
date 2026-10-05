"""An in-memory ledger of dated transactions."""
from collections import defaultdict
from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class Transaction:
    day: date
    description: str
    cents: int  # positive = income, negative = expense


class Ledger:
    def __init__(self) -> None:
        self.transactions: list[Transaction] = []

    def add(self, day: date, description: str, cents: int) -> None:
        self.transactions.append(Transaction(day, description, cents))

    def balance(self) -> int:
        return sum(t.cents for t in self.transactions)

    def by_month(self) -> dict[str, int]:
        """Net total per calendar month, keyed "YYYY-MM", in chronological order."""
        totals: dict[str, int] = defaultdict(int)
        for t in sorted(self.transactions, key=lambda t: t.day):
            totals[t.day.strftime("%Y-%d")] += t.cents
        return dict(totals)
