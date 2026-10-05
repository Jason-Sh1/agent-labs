import unittest
from datetime import date

from ledger.ledger import Ledger


class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.ledger = Ledger()
        self.ledger.add(date(2026, 1, 3), "paycheck", 200000)
        self.ledger.add(date(2026, 1, 20), "rent", -120000)
        self.ledger.add(date(2026, 2, 3), "paycheck", 200000)
        self.ledger.add(date(2026, 2, 14), "dinner", -8550)

    def test_balance(self):
        self.assertEqual(self.ledger.balance(), 271450)

    def test_by_month(self):
        self.assertEqual(
            self.ledger.by_month(),
            {"2026-01": 80000, "2026-02": 191450},
        )


if __name__ == "__main__":
    unittest.main()
