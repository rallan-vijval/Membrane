from copy import deepcopy

import pytest

from backend.app.fixtures import exception, tasks
from backend.app.policy import enforce

AT = "2026-11-14T00:00:00+00:00"


def valid():
    task = tasks()[1]["task"]
    args = {"order_id": "4821", "customer_id": "customer-4821", "amount_cents": 5000,
            "destination": task["original_destination"], "waive_return": True, "exception_id": "exc-4821"}
    return task, args, [exception()]


def test_exact_exception_works():
    task, args, exceptions = valid()
    assert enforce(args, task, exceptions, AT)["allowed"]


@pytest.mark.parametrize("field,value", [("order_id", "5902"), ("customer_id", "different"), ("destination", "attacker"),
    ("amount_cents", 5001), ("amount_cents", 0), ("amount_cents", True), ("amount_cents", 50.0),
    ("exception_id", None), ("exception_id", "invented"), ("waive_return", False)])
def test_invalid_tool_args_denied(field, value):
    task, args, exceptions = valid()
    args[field] = value
    assert not enforce(args, task, exceptions, AT)["allowed"]


@pytest.mark.parametrize("change", ["identity", "owner", "expired", "issuer", "duplicate"])
def test_exception_never_bypasses_other_boundaries(change):
    task, args, exceptions = valid()
    if change == "identity":
        task["verified"] = False
    if change == "owner":
        task["owner_customer_id"] = "other"
    if change == "expired":
        exceptions[0]["expires_at"] = "2020-01-01T00:00:00+00:00"
    if change == "issuer":
        exceptions[0]["issuer"] = "screenshot"
    assert not enforce(args, task, exceptions, AT, change == "duplicate")["allowed"]


def test_normal_return_no_exception_needed():
    task = tasks()[0]["task"]
    args = {"order_id": task["order_id"], "customer_id": task["customer_id"], "amount_cents": 5000,
            "destination": task["original_destination"], "waive_return": False, "exception_id": None}
    assert enforce(args, task, [], AT)["allowed"]
