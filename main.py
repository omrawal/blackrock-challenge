"""
BlackRock Retirement Savings API
---------------------------------
Automated micro-savings system with investment projections.
Port: 5477
Framework: Flask
"""
import os
import time
import threading
import psutil
from flask import Flask, request, jsonify, abort

from business import (
    compute_ceiling, compute_remanent, parse_dt,
    validate_transactions, process_transactions,
    group_by_k, calculate_nps_return, calculate_index_return,
    is_in_range,
)

# ─── App Setup ─────────────────────────────────────────────────────────────────
app = Flask(__name__)
APP_START = time.time()

# ─── Helpers ──────────────────────────────────────────────────────────────────

def require_json():
    if not request.is_json:
        abort(400, description="Content-Type must be application/json")

def get_json_body():
    require_json()
    data = request.get_json(silent=True)
    if data is None:
        abort(400, description="Invalid JSON body")
    return data


# ─── Endpoint 1: Transaction Builder ──────────────────────────────────────────
@app.post("/blackrock/challenge/v1/transactions:parse")
def parse_transactions():
    """
    Enrich raw expenses with ceiling and remanent values.

    Input:  [{"date": "YYYY-MM-DD HH:mm:ss", "amount": float}, ...]
    Output: [{"date":..., "amount":..., "ceiling":..., "remanent":...}, ...]
    """
    expenses = get_json_body()
    result = []
    for exp in expenses:
        amount = float(exp["amount"])
        ceiling = compute_ceiling(amount)
        remanent = round(compute_remanent(amount, ceiling), 2)
        result.append({
            "date": exp["date"],
            "amount": amount,
            "ceiling": ceiling,
            "remanent": remanent,
        })
    return jsonify(result), 200


# ─── Endpoint 2: Transaction Validator ────────────────────────────────────────
@app.post("/blackrock/challenge/v1/transactions:validator")
def validate():
    """
    Validate transactions. Catches: negative amounts, duplicate dates.

    Input:  {"wage": float, "transactions": [...]}
    Output: {"valid": [...], "invalid": [...]}
    """
    body = get_json_body()
    raw = body.get("transactions", [])
    valid_raw, invalid_raw = validate_transactions(raw)

    def enrich(tx):
        amount = float(tx.get("amount", 0))
        ceiling = float(tx.get("ceiling") or compute_ceiling(amount))
        remanent = float(tx.get("remanent") or compute_remanent(amount, ceiling))
        return {
            "date": tx["date"],
            "amount": amount,
            "ceiling": ceiling,
            "remanent": remanent,
        }

    return jsonify({
        "valid": [enrich(tx) for tx in valid_raw],
        "invalid": [
            {**enrich(tx), "message": tx["message"]}
            for tx in invalid_raw
        ],
    }), 200


# ─── Endpoint 3: Temporal Constraints Filter ──────────────────────────────────
@app.post("/blackrock/challenge/v1/transactions:filter")
def filter_transactions():
    """
    Apply q/p/k period rules + basic validation.

    Rules:
    - q period: replace remanent with fixed amount (latest-start q wins on overlap)
    - p period: add extra to remanent (all matching p periods summed)
    - k period: sets inkPeriod flag on each transaction

    Input:  {"q":[], "p":[], "k":[], "wage":float, "transactions":[...]}
    Output: {"valid": [...], "invalid": [...]}
    """
    body = get_json_body()
    raw = body.get("transactions", [])
    q_list = body.get("q", [])
    p_list = body.get("p", [])
    k_list = body.get("k", [])

    valid_raw, invalid_raw = validate_transactions(raw)
    processed = process_transactions(valid_raw, q_list, p_list)

    valid_out = []
    for tx in processed:
        tx_dt = parse_dt(tx["date"])
        in_k = any(
            is_in_range(tx_dt, parse_dt(k["start"]), parse_dt(k["end"]))
            for k in k_list
        )
        valid_out.append({
            "date": tx["date"],
            "amount": float(tx["amount"]),
            "ceiling": float(tx["_ceiling"]),
            "remanent": float(tx["_remanent"]),
            "inkPeriod": in_k,
        })

    invalid_out = [
        {"date": tx["date"], "amount": float(tx.get("amount", 0)), "message": tx["message"]}
        for tx in invalid_raw
    ]

    return jsonify({"valid": valid_out, "invalid": invalid_out}), 200


# ─── Shared Returns Logic ──────────────────────────────────────────────────────
def _compute_returns(body: dict, mode: str) -> dict:
    raw = body.get("transactions", [])
    age = int(body["age"])
    wage = float(body["wage"])
    inflation = float(body["inflation"])
    q_list = body.get("q", [])
    p_list = body.get("p", [])
    k_list = body.get("k", [])

    valid_raw, _ = validate_transactions(raw)
    processed = process_transactions(valid_raw, q_list, p_list)

    total_amount = round(sum(tx["amount"] for tx in processed), 2)
    total_ceiling = round(sum(tx["_ceiling"] for tx in processed), 2)

    k_groups = group_by_k(processed, k_list)

    savings_by_dates = []
    for group in k_groups:
        amount = group["amount"]
        if mode == "nps":
            profit, tax_benefit = calculate_nps_return(amount, age, wage, inflation)
            savings_by_dates.append({
                "start": group["start"],
                "end": group["end"],
                "amount": amount,
                "profit": profit,
                "taxBenefit": tax_benefit,
            })
        else:
            ret = calculate_index_return(amount, age, inflation)
            savings_by_dates.append({
                "start": group["start"],
                "end": group["end"],
                "amount": amount,
                "profit": round(ret - amount, 2),
                "taxBenefit": 0.0,
            })

    return {
        "totalTransactionAmount": total_amount,
        "totalCeiling": total_ceiling,
        "savingsByDates": savings_by_dates,
    }


# ─── Endpoint 4a: NPS Returns ─────────────────────────────────────────────────
@app.post("/blackrock/challenge/v1/returns:nps")
def returns_nps():
    """NPS (7.11% annually). Tax deduction up to ₹2L or 10% of income."""
    body = get_json_body()
    return jsonify(_compute_returns(body, mode="nps")), 200


# ─── Endpoint 4b: Index Fund Returns ─────────────────────────────────────────
@app.post("/blackrock/challenge/v1/returns:index")
def returns_index():
    """NIFTY 50 Index Fund (14.49% annually). No restrictions."""
    body = get_json_body()
    return jsonify(_compute_returns(body, mode="index")), 200


# ─── Endpoint 5: Performance Report ───────────────────────────────────────────
@app.get("/blackrock/challenge/v1/performance")
def performance():
    uptime = time.time() - APP_START
    h = int(uptime // 3600)
    m = int((uptime % 3600) // 60)
    s = int(uptime % 60)
    ms = int((uptime % 1) * 1000)

    proc = psutil.Process(os.getpid())
    mem_mb = proc.memory_info().rss / (1024 * 1024)

    return jsonify({
        "time": f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}",
        "memory": f"{mem_mb:.2f} MB",
        "threads": threading.active_count(),
    }), 200


# ─── Health Check ──────────────────────────────────────────────────────────────
@app.get("/health")
def health():
    return jsonify({"status": "ok", "service": "blackrock-retirement-api"}), 200


# ─── Error Handlers ────────────────────────────────────────────────────────────
@app.errorhandler(400)
def bad_request(e):
    return jsonify({"error": "Bad Request", "message": str(e)}), 400

@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": "Not Found"}), 404

@app.errorhandler(500)
def server_error(e):
    return jsonify({"error": "Internal Server Error", "message": str(e)}), 500


# ─── Entry Point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5477, debug=False, threaded=True)
