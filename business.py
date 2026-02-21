"""
Business logic for Retirement Savings API.
Handles all financial calculations.
"""
import math
from datetime import datetime
from typing import List, Optional, Tuple

NPS_RATE = 0.0711
INDEX_RATE = 0.1449
NPS_MAX_DEDUCTION = 200_000.0
NPS_MAX_DEDUCTION_PCT = 0.10
RETIREMENT_AGE = 60
MIN_YEARS = 5
ROUND_BASE = 100

DATETIME_FORMATS = [
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
]

def parse_dt(dt_str: str) -> datetime:
    """Parse a datetime string flexibly."""
    cleaned = dt_str.strip()
    for fmt in DATETIME_FORMATS:
        try:
            return datetime.strptime(cleaned, fmt)
        except ValueError:
            continue
    raise ValueError(f"Cannot parse datetime: '{dt_str}'. Expected format: YYYY-MM-DD HH:mm:ss")

def is_in_range(dt: datetime, start: datetime, end: datetime) -> bool:
    return start <= dt <= end


def compute_ceiling(amount: float) -> float:
    if amount <= 0:
        return 0.0
    remainder = amount % ROUND_BASE
    if remainder == 0:
        return float(amount)
    return float(amount + (ROUND_BASE - remainder))

def compute_remanent(amount: float, ceiling: float) -> float:
    return round(ceiling - amount, 10)


# q Period (Fixed Override)
def apply_q_periods(remanent: float, tx_dt: datetime, q_periods: list) -> float:
    matching = [
        (i, q) for i, q in enumerate(q_periods)
        if is_in_range(tx_dt, parse_dt(q["start"]), parse_dt(q["end"]))
    ]
    if not matching:
        return remanent

    best_idx, best_q = max(matching, key=lambda t: (parse_dt(t[1]["start"]), -t[0]))
    return float(best_q["fixed"])


# p Period (Extra Addition)
def apply_p_periods(remanent: float, tx_dt: datetime, p_periods: list) -> float:
    total_extra = sum(
        p["extra"]
        for p in p_periods
        if is_in_range(tx_dt, parse_dt(p["start"]), parse_dt(p["end"]))
    )
    return remanent + total_extra


# k Period Grouping
def group_by_k(transactions: list, k_periods: list) -> List[dict]:
    """
    For each k period, sum the remanents of transactions within that range.
    A transaction can belong to multiple k periods.
    """
    results = []
    for k in k_periods:
        k_start = parse_dt(k["start"])
        k_end = parse_dt(k["end"])
        total = sum(
            tx["_remanent"]
            for tx in transactions
            if is_in_range(parse_dt(tx["date"]), k_start, k_end)
        )
        results.append({
            "start": k["start"],
            "end": k["end"],
            "amount": round(total, 2),
        })
    return results


# Tax Calculation
def calculate_tax(income: float) -> float:
    """Simplified Indian tax slab calculation (pre-tax income)."""
    if income <= 700_000:
        return 0.0
    elif income <= 1_000_000:
        return (income - 700_000) * 0.10
    elif income <= 1_200_000:
        return 300_000 * 0.10 + (income - 1_000_000) * 0.15
    elif income <= 1_500_000:
        return 300_000 * 0.10 + 200_000 * 0.15 + (income - 1_200_000) * 0.20
    else:
        return 300_000 * 0.10 + 200_000 * 0.15 + 300_000 * 0.20 + (income - 1_500_000) * 0.30


def calculate_tax_benefit(invested: float, annual_income: float) -> float:
    """NPS tax benefit based on invested amount and annual income."""
    deduction = min(invested, NPS_MAX_DEDUCTION_PCT * annual_income, NPS_MAX_DEDUCTION)
    return calculate_tax(annual_income) - calculate_tax(annual_income - deduction)


# Investment Returns
def compute_years(age: int) -> int:
    """Years until retirement (min 5)."""
    return max(RETIREMENT_AGE - age, MIN_YEARS)

def compound_value(principal: float, rate: float, years: int) -> float:
    """A = P * (1 + r)^t  (annually compounded, n=1)."""
    return principal * math.pow(1 + rate, years)

def inflation_adjust(amount: float, inflation_rate_pct: float, years: int) -> float:
    """Deflate future value to today's purchasing power."""
    return amount / math.pow(1 + inflation_rate_pct / 100, years)

def calculate_nps_return(amount: float, age: int, wage: float, inflation: float) -> Tuple[float, float]:
    """
    Returns (profit, tax_benefit) for NPS investment.
    profit = real_value - principal  (inflation-adjusted net gain)
    """
    years = compute_years(age)
    future_value = compound_value(amount, NPS_RATE, years)
    real_value = inflation_adjust(future_value, inflation, years)
    profit = round(real_value - amount, 2)
    annual_income = wage * 12
    tax_benefit = round(calculate_tax_benefit(amount, annual_income), 2)
    return profit, tax_benefit

def calculate_index_return(amount: float, age: int, inflation: float) -> float:
    """
    Returns total real return (inflation-adjusted final value) for Index Fund.
    """
    years = compute_years(age)
    future_value = compound_value(amount, INDEX_RATE, years)
    real_value = inflation_adjust(future_value, inflation, years)
    return round(real_value, 2)


#  Transaction Validators
def validate_transactions(transactions: list) -> Tuple[list, list]:
    """
    Returns (valid_list, invalid_list).
    Checks for: negative amounts, duplicate dates.
    """
    valid, invalid = [], []
    seen_dates = {}

    for tx in transactions:
        errors = []
        if tx.get("amount", 0) < 0:
            errors.append("Negative amounts are not allowed")

        date_key = tx.get("date", "")
        if date_key in seen_dates:
            errors.append("Duplicate transaction")

        if errors:
            invalid.append({**tx, "message": errors[0]})
        else:
            seen_dates[date_key] = True
            valid.append(tx)

    return valid, invalid



def process_transactions(transactions: list, q_periods: list, p_periods: list) -> list:
    """
    Apply all period rules to a list of raw expense dicts.
    Adds _ceiling and _remanent (private fields for internal use).
    """
    processed = []
    for tx in transactions:
        amount = tx["amount"]
        ceiling = compute_ceiling(amount)
        remanent = compute_remanent(amount, ceiling)

        # Step 2: q override
        tx_dt = parse_dt(tx["date"])
        remanent = apply_q_periods(remanent, tx_dt, q_periods)

        # Step 3: p addition
        remanent = apply_p_periods(remanent, tx_dt, p_periods)

        processed.append({
            **tx,
            "_ceiling": ceiling,
            "_remanent": round(remanent, 2),
        })
    return processed
