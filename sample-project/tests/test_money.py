import unittest

from ledger.money import format_cents, parse_amount


class ParseAmountTests(unittest.TestCase):
    def test_simple(self):
        self.assertEqual(parse_amount("12.50"), 1250)

    def test_dollar_sign(self):
        self.assertEqual(parse_amount("$3"), 300)

    def test_thousands_separator(self):
        self.assertEqual(parse_amount("$1,234.50"), 123450)

    def test_negative(self):
        self.assertEqual(parse_amount("-$7.05"), -705)


class FormatCentsTests(unittest.TestCase):
    def test_positive(self):
        self.assertEqual(format_cents(123450), "$1,234.50")

    def test_negative(self):
        self.assertEqual(format_cents(-150), "-$1.50")


if __name__ == "__main__":
    unittest.main()
