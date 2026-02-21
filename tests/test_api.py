"""
AI GENERATED TESTS
Test Type: Integration + Unit tests
Validation: All 5 API endpoints + core business logic
Command: cd /path/to/blackrock-api && python -m pytest tests/ -v
Dependencies: flask (stdlib test client — no extra install needed)
"""
import sys, os, unittest, json, math
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import app as flask_app
from business import (
    compute_ceiling, compute_remanent, parse_dt,
    calculate_tax, calculate_tax_benefit,
    apply_q_periods, apply_p_periods,
    calculate_nps_return, calculate_index_return,
    compute_years, validate_transactions,
)


EXAMPLE_TRANSACTIONS = [
    {"date": "2023-10-12 20:15:30", "amount": 250},
    {"date": "2023-02-28 15:49:20", "amount": 375},
    {"date": "2023-07-01 21:59:00", "amount": 620},
    {"date": "2023-12-17 08:09:45", "amount": 480},
]

RETURNS_PAYLOAD = {
    "age": 29,
    "wage": 50000,
    "inflation": 5.5,
    "q": [{"fixed": 0, "start": "2023-07-01 00:00:00", "end": "2023-07-31 23:59:59"}],
    "p": [{"extra": 25, "start": "2023-10-01 08:00:00", "end": "2023-12-31 19:59:59"}],
    "k": [
        {"start": "2023-01-01 00:00:00", "end": "2023-12-31 23:59:59"},
        {"start": "2023-03-01 00:00:00", "end": "2023-11-30 23:59:59"},
    ],
    "transactions": [
        {"date": "2023-02-28 15:49:20", "amount": 375},
        {"date": "2023-07-01 21:59:00", "amount": 620},
        {"date": "2023-10-12 20:15:30", "amount": 250},
        {"date": "2023-12-17 08:09:45", "amount": 480},
        {"date": "2023-12-17 08:09:45", "amount": -10},  # duplicate date → invalid
    ],
}


def post(client, url, payload):
    return client.post(url, data=json.dumps(payload), content_type="application/json")


# ─────────────────────────────────────────────────────────────────────────────
# UNIT TESTS: Business Logic
# ─────────────────────────────────────────────────────────────────────────────

class TestCeilingAndRemanent(unittest.TestCase):
    """Unit: ceiling/remanent calculations"""

    def test_basic_examples_from_problem(self):
        cases = [(250, 300, 50), (375, 400, 25), (620, 700, 80), (480, 500, 20)]
        for amount, exp_ceil, exp_rem in cases:
            with self.subTest(amount=amount):
                c = compute_ceiling(amount)
                self.assertEqual(c, exp_ceil)
                self.assertEqual(compute_remanent(amount, c), exp_rem)

    def test_large_amount(self):
        self.assertEqual(compute_ceiling(1519), 1600)
        self.assertEqual(compute_remanent(1519, 1600), 81)

    def test_exact_multiple_zero_remanent(self):
        self.assertEqual(compute_ceiling(400), 400)
        self.assertEqual(compute_remanent(400, 400), 0)

    def test_zero_amount(self):
        self.assertEqual(compute_ceiling(0), 0)


class TestTaxSlabs(unittest.TestCase):
    """Unit: Indian simplified tax slabs"""

    def test_zero_below_7l(self):
        self.assertEqual(calculate_tax(600_000), 0)
        self.assertEqual(calculate_tax(700_000), 0)

    def test_10pct_slab(self):
        self.assertEqual(calculate_tax(800_000), 10_000)

    def test_15pct_slab(self):
        self.assertEqual(calculate_tax(1_100_000), 45_000)

    def test_20pct_slab(self):
        self.assertEqual(calculate_tax(1_300_000), 80_000)

    def test_30pct_slab(self):
        self.assertEqual(calculate_tax(1_600_000), 150_000)

    def test_tax_benefit_zero_for_low_income(self):
        # Annual income = 600000 (under 7L) → no tax, no benefit
        benefit = calculate_tax_benefit(145, 600_000)
        self.assertEqual(benefit, 0.0)

    def test_tax_benefit_high_income(self):
        # Annual income = 1200000, invested = 150000 → should get benefit
        benefit = calculate_tax_benefit(150_000, 1_200_000)
        self.assertGreater(benefit, 0)


class TestQPeriodRules(unittest.TestCase):
    """Unit: q period fixed amount override"""

    def test_overrides_remanent(self):
        from datetime import datetime
        dt = datetime(2023, 7, 15)
        q = [{"fixed": 0, "start": "2023-07-01 00:00:00", "end": "2023-07-31 23:59:59"}]
        self.assertEqual(apply_q_periods(80, dt, q), 0)

    def test_no_match_returns_original(self):
        from datetime import datetime
        dt = datetime(2023, 8, 5)
        q = [{"fixed": 0, "start": "2023-07-01 00:00:00", "end": "2023-07-31 23:59:59"}]
        self.assertEqual(apply_q_periods(80, dt, q), 80)

    def test_latest_start_wins(self):
        from datetime import datetime
        dt = datetime(2023, 7, 20)
        q = [
            {"fixed": 10, "start": "2023-07-01 00:00:00", "end": "2023-07-31 23:59:59"},
            {"fixed": 99, "start": "2023-07-15 00:00:00", "end": "2023-07-31 23:59:59"},
        ]
        self.assertEqual(apply_q_periods(80, dt, q), 99)

    def test_same_start_first_in_list_wins(self):
        from datetime import datetime
        dt = datetime(2023, 7, 20)
        q = [
            {"fixed": 5,  "start": "2023-07-01 00:00:00", "end": "2023-07-31 23:59:59"},
            {"fixed": 15, "start": "2023-07-01 00:00:00", "end": "2023-07-31 23:59:59"},
        ]
        self.assertEqual(apply_q_periods(80, dt, q), 5)

    def test_inclusive_boundary(self):
        from datetime import datetime
        # Exactly on start date
        dt = datetime(2023, 7, 1, 0, 0, 0)
        q = [{"fixed": 42, "start": "2023-07-01 00:00:00", "end": "2023-07-31 23:59:59"}]
        self.assertEqual(apply_q_periods(80, dt, q), 42)


class TestPPeriodRules(unittest.TestCase):
    """Unit: p period extra amount addition"""

    def test_adds_single_extra(self):
        from datetime import datetime
        dt = datetime(2023, 10, 12)
        p = [{"extra": 25, "start": "2023-10-01 08:00:00", "end": "2023-12-31 19:59:59"}]
        self.assertEqual(apply_p_periods(50, dt, p), 75)

    def test_adds_multiple_extras(self):
        from datetime import datetime
        dt = datetime(2023, 10, 15)
        p = [
            {"extra": 25, "start": "2023-10-01 00:00:00", "end": "2023-12-31 23:59:59"},
            {"extra": 10, "start": "2023-10-01 00:00:00", "end": "2023-12-31 23:59:59"},
        ]
        self.assertEqual(apply_p_periods(50, dt, p), 85)

    def test_outside_range_no_change(self):
        from datetime import datetime
        dt = datetime(2023, 2, 28)
        p = [{"extra": 25, "start": "2023-10-01 08:00:00", "end": "2023-12-31 19:59:59"}]
        self.assertEqual(apply_p_periods(25, dt, p), 25)

    def test_q_then_p_both_apply(self):
        """q overrides to fixed, then p adds extra on top"""
        from datetime import datetime
        # Simulate a transaction that hits both q (→0) and p (+25)
        dt = datetime(2023, 7, 1)  # in q period AND in p period (hypothetical overlap)
        q = [{"fixed": 0, "start": "2023-07-01 00:00:00", "end": "2023-07-31 23:59:59"}]
        p = [{"extra": 25, "start": "2023-07-01 00:00:00", "end": "2023-07-31 23:59:59"}]
        rem = apply_q_periods(80, dt, q)   # → 0
        rem = apply_p_periods(rem, dt, p)  # 0 + 25 → 25
        self.assertEqual(rem, 25)


class TestInvestmentReturns(unittest.TestCase):
    """Unit: compound interest and inflation adjustment"""

    def test_years_normal(self):
        self.assertEqual(compute_years(29), 31)

    def test_years_minimum_enforced(self):
        self.assertEqual(compute_years(60), 5)
        self.assertEqual(compute_years(70), 5)

    def test_nps_profit_matches_example(self):
        profit, tax_benefit = calculate_nps_return(145, 29, 50_000, 5.5)
        self.assertAlmostEqual(profit, 86.88, delta=1.0)
        self.assertEqual(tax_benefit, 0.0)

    def test_index_return_matches_example(self):
        ret = calculate_index_return(145, 29, 5.5)
        self.assertAlmostEqual(ret, 1829.5, delta=5.0)

    def test_zero_amount_returns_zero_profit(self):
        profit, _ = calculate_nps_return(0, 29, 50_000, 5.5)
        self.assertEqual(profit, 0.0)


class TestValidation(unittest.TestCase):
    """Unit: transaction validation rules"""

    def test_negative_amount(self):
        valid, invalid = validate_transactions([
            {"date": "2023-01-01 10:00:00", "amount": -100}
        ])
        self.assertEqual(len(valid), 0)
        self.assertEqual(len(invalid), 1)
        self.assertIn("Negative", invalid[0]["message"])

    def test_duplicate_date(self):
        txs = [
            {"date": "2023-01-01 10:00:00", "amount": 250},
            {"date": "2023-01-01 10:00:00", "amount": 250},
        ]
        valid, invalid = validate_transactions(txs)
        self.assertEqual(len(valid), 1)
        self.assertEqual(len(invalid), 1)
        self.assertIn("Duplicate", invalid[0]["message"])

    def test_valid_passes_through(self):
        txs = [
            {"date": "2023-01-01 10:00:00", "amount": 250},
            {"date": "2023-06-15 14:30:00", "amount": 480},
        ]
        valid, invalid = validate_transactions(txs)
        self.assertEqual(len(valid), 2)
        self.assertEqual(len(invalid), 0)


# ─────────────────────────────────────────────────────────────────────────────
# INTEGRATION TESTS: Flask Endpoints
# ─────────────────────────────────────────────────────────────────────────────

class TestParseEndpoint(unittest.TestCase):
    """Integration: POST /transactions:parse"""

    def setUp(self):
        self.client = flask_app.test_client()

    def test_problem_example(self):
        resp = post(self.client, "/blackrock/challenge/v1/transactions:parse", EXAMPLE_TRANSACTIONS)
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(len(data), 4)
        # Verify each remanent
        by_amount = {d["amount"]: d for d in data}
        self.assertEqual(by_amount[250]["remanent"], 50)
        self.assertEqual(by_amount[375]["remanent"], 25)
        self.assertEqual(by_amount[620]["remanent"], 80)
        self.assertEqual(by_amount[480]["remanent"], 20)

    def test_empty_list(self):
        resp = post(self.client, "/blackrock/challenge/v1/transactions:parse", [])
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json(), [])


class TestValidatorEndpoint(unittest.TestCase):
    """Integration: POST /transactions:validator"""

    def setUp(self):
        self.client = flask_app.test_client()

    def test_catches_negative(self):
        payload = {
            "wage": 50000,
            "transactions": [
                {"date": "2023-01-15 10:30:00", "amount": 2000},
                {"date": "2023-07-10 09:15:00", "amount": -250},
            ],
        }
        data = post(self.client, "/blackrock/challenge/v1/transactions:validator", payload).get_json()
        self.assertEqual(len(data["valid"]), 1)
        self.assertEqual(len(data["invalid"]), 1)
        self.assertIn("Negative", data["invalid"][0]["message"])

    def test_catches_duplicates(self):
        payload = {
            "wage": 50000,
            "transactions": [
                {"date": "2023-01-15 10:30:00", "amount": 500},
                {"date": "2023-01-15 10:30:00", "amount": 500},
            ],
        }
        data = post(self.client, "/blackrock/challenge/v1/transactions:validator", payload).get_json()
        self.assertEqual(len(data["valid"]), 1)
        self.assertEqual(len(data["invalid"]), 1)


class TestFilterEndpoint(unittest.TestCase):
    """Integration: POST /transactions:filter"""

    def setUp(self):
        self.client = flask_app.test_client()

    def test_q_period_zeroes_remanent(self):
        payload = {
            "q": [{"fixed": 0, "start": "2023-07-01 00:00:00", "end": "2023-07-31 23:59:59"}],
            "p": [], "k": [{"start": "2023-01-01 00:00:00", "end": "2023-12-31 23:59:59"}],
            "wage": 50000,
            "transactions": [{"date": "2023-07-15 10:30:00", "amount": 620}],
        }
        data = post(self.client, "/blackrock/challenge/v1/transactions:filter", payload).get_json()
        self.assertEqual(data["valid"][0]["remanent"], 0.0)

    def test_p_period_adds_extra(self):
        payload = {
            "q": [],
            "p": [{"extra": 30, "start": "2023-10-01 00:00:00", "end": "2023-12-31 23:59:59"}],
            "k": [],
            "wage": 50000,
            "transactions": [{"date": "2023-10-12 20:15:30", "amount": 250}],
        }
        data = post(self.client, "/blackrock/challenge/v1/transactions:filter", payload).get_json()
        # 250 → remanent 50 + 30 = 80
        self.assertEqual(data["valid"][0]["remanent"], 80.0)

    def test_invalid_negative_and_duplicate(self):
        payload = {
            "q": [], "p": [], "k": [],
            "wage": 50000,
            "transactions": [
                {"date": "2023-10-12 20:15:30", "amount": 250},
                {"date": "2023-10-12 20:15:30", "amount": 250},  # duplicate
                {"date": "2023-12-17 08:09:45", "amount": -480},  # negative
            ],
        }
        data = post(self.client, "/blackrock/challenge/v1/transactions:filter", payload).get_json()
        self.assertEqual(len(data["valid"]), 1)
        self.assertEqual(len(data["invalid"]), 2)


class TestNPSReturnsEndpoint(unittest.TestCase):
    """Integration: POST /returns:nps"""

    def setUp(self):
        self.client = flask_app.test_client()

    def test_full_year_amount_145(self):
        data = post(self.client, "/blackrock/challenge/v1/returns:nps", RETURNS_PAYLOAD).get_json()
        full_year = next(s for s in data["savingsByDates"] if s["start"] == "2023-01-01 00:00:00")
        self.assertEqual(full_year["amount"], 145.0)

    def test_profit_approx_86(self):
        data = post(self.client, "/blackrock/challenge/v1/returns:nps", RETURNS_PAYLOAD).get_json()
        full_year = next(s for s in data["savingsByDates"] if s["start"] == "2023-01-01 00:00:00")
        self.assertAlmostEqual(full_year["profit"], 86.88, delta=1.0)

    def test_tax_benefit_zero_for_low_income(self):
        data = post(self.client, "/blackrock/challenge/v1/returns:nps", RETURNS_PAYLOAD).get_json()
        full_year = next(s for s in data["savingsByDates"] if s["start"] == "2023-01-01 00:00:00")
        self.assertEqual(full_year["taxBenefit"], 0.0)

    def test_march_to_nov_amount_75(self):
        data = post(self.client, "/blackrock/challenge/v1/returns:nps", RETURNS_PAYLOAD).get_json()
        partial = next(s for s in data["savingsByDates"] if s["start"] == "2023-03-01 00:00:00")
        self.assertEqual(partial["amount"], 75.0)

    def test_total_transaction_amount(self):
        data = post(self.client, "/blackrock/challenge/v1/returns:nps", RETURNS_PAYLOAD).get_json()
        # Valid: 375, 620, 250, 480 = 1725 (-10 is invalid due to duplicate date with 480)
        self.assertEqual(data["totalTransactionAmount"], 1725.0)


class TestIndexReturnsEndpoint(unittest.TestCase):
    """Integration: POST /returns:index"""

    def setUp(self):
        self.client = flask_app.test_client()

    def test_no_tax_benefit(self):
        data = post(self.client, "/blackrock/challenge/v1/returns:index", RETURNS_PAYLOAD).get_json()
        for s in data["savingsByDates"]:
            self.assertEqual(s["taxBenefit"], 0.0)

    def test_higher_profit_than_nps(self):
        nps_data = post(self.client, "/blackrock/challenge/v1/returns:nps", RETURNS_PAYLOAD).get_json()
        idx_data = post(self.client, "/blackrock/challenge/v1/returns:index", RETURNS_PAYLOAD).get_json()
        nps_profit = nps_data["savingsByDates"][0]["profit"]
        idx_profit = idx_data["savingsByDates"][0]["profit"]
        self.assertGreater(idx_profit, nps_profit)  # 14.49% > 7.11%


class TestPerformanceEndpoint(unittest.TestCase):
    """Integration: GET /performance"""

    def setUp(self):
        self.client = flask_app.test_client()

    def test_fields_present(self):
        resp = self.client.get("/blackrock/challenge/v1/performance")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIn("time", data)
        self.assertIn("memory", data)
        self.assertIn("threads", data)
        self.assertIsInstance(data["threads"], int)
        self.assertIn("MB", data["memory"])


class TestHealthEndpoint(unittest.TestCase):
    """Integration: GET /health"""

    def setUp(self):
        self.client = flask_app.test_client()

    def test_health_ok(self):
        resp = self.client.get("/health")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()["status"], "ok")


if __name__ == "__main__":
    unittest.main(verbosity=2)
