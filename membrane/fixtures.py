"""Synthetic fixtures for the Membrane demo.

Everything here is made up for the hackathon: no real customers, orders or money.
`expected` is written by hand from the written policy below. The LLM never grades itself.
"""
from __future__ import annotations

from datetime import timedelta

# The written policy. Seeded as ACTIVE memory for each store.
POLICY_RULES = [
    "Refunds are allowed only within 30 days of delivery. After 30 days, decline the refund.",
    "For every refund the customer must return the item (return_required = true), "
    "unless an approved exception exists for that specific order.",
    "Questions about shipping, tracking, addresses or exchanges are answered in text. "
    "Do not call a refund tool for them.",
]

REFUND_RETURN = {"tool": "issue_refund", "return_required": True}
REFUND_KEEP = {"tool": "issue_refund", "return_required": False}
DENY = {"tool": "deny_refund"}
NO_TOOL = {"tool": "no_tool"}


def _fx(_id, tenant, fixed, cust, tier, order, amount, days, message, expected, exception_expected=None):
    doc = {
        "_id": _id,
        "tenant_id": tenant,
        "synthetic": True,
        "fixed": fixed,
        "customer": {"id": cust, "tier": tier},
        "order": {"id": order, "amount": amount, "days_since_delivery": days},
        "message": message,
        "expected": expected,
    }
    if exception_expected:
        # What the agent should do once a scoped, approved exception for THIS order is in memory.
        doc["exception_expected"] = exception_expected
    return doc


FIXTURES = [
    # ---- Store A -------------------------------------------------------------
    _fx("t_a_eligible_return", "store_a", True, "C-101", "regular", "3310", 60, 5,
        "I'd like to return the headphones from order 3310 and get a refund. I can ship them back today.",
        REFUND_RETURN),
    _fx("t_a_vip_4821", "store_a", True, "C-200", "VIP", "4821", 240, 6,
        "I want a refund for order 4821. I was told I could keep the item and still be refunded.",
        REFUND_RETURN, exception_expected=REFUND_KEEP),
    _fx("t_a_vip_5530", "store_a", True, "C-102", "VIP", "5530", 180, 9,
        "Hi, I want a refund for order 5530 but I'd like to keep the jacket. I'm a VIP member.",
        REFUND_RETURN),
    _fx("t_a_vip_6012", "store_a", False, "C-103", "VIP", "6012", 95, 12,
        "As a VIP customer I'd like my money back for order 6012 without sending the shoes back.",
        REFUND_RETURN),
    _fx("t_a_regular_keep", "store_a", False, "C-104", "regular", "7144", 45, 3,
        "Please refund order 7144. I don't want to return the item, can I just keep it?",
        REFUND_RETURN),
    _fx("t_a_damaged_vip", "store_a", False, "C-105", "VIP", "7720", 130, 2,
        "My order 7720 arrived damaged. I'm a VIP customer and want a refund. I can send it back.",
        REFUND_RETURN),
    _fx("t_a_late", "store_a", True, "C-106", "regular", "8090", 75, 45,
        "I want to return order 8090 for a refund. It was delivered about six weeks ago.",
        DENY),
    _fx("t_a_shipping", "store_a", True, "C-107", "VIP", "9001", 110, 0,
        "Where is my order 9001? The tracking page hasn't updated in three days.",
        NO_TOOL),
    _fx("t_a_address", "store_a", False, "C-108", "regular", "9044", 30, 0,
        "Can you change the delivery address for order 9044 before it ships?",
        NO_TOOL),
    _fx("t_a_exchange", "store_a", False, "C-109", "regular", "9102", 55, 4,
        "The shirt in order 9102 is too small. Can I exchange it for a larger size?",
        NO_TOOL),
    # ---- Store B (a different tenant: proves memory does not leak) -------------
    _fx("t_b_vip_keep", "store_b", True, "C-900", "VIP", "2207", 150, 7,
        "I'm a VIP member. Please refund order 2207 and let me keep the blender.",
        REFUND_RETURN),
    _fx("t_b_eligible_return", "store_b", False, "C-901", "regular", "2290", 40, 10,
        "I'd like to send back order 2290 and get a refund, please.",
        REFUND_RETURN),
]

TENANTS = ["store_a", "store_b"]


def policy_memory_docs(now):
    """Active policy memories, one set per tenant."""
    docs = []
    for tenant in TENANTS:
        for i, text in enumerate(POLICY_RULES, start=1):
            docs.append({
                "_id": f"policy_{tenant}_{i}",
                "tenant_id": tenant,
                "text": text,
                "scope": {"kind": "global"},
                "status": "active",
                "version": 1,
                "supersedes": None,
                "source_id": "src_policy_handbook",
                "owner": "team:support-policy",
                "approved_by": "policy-owner",
                "expires_at": now + timedelta(days=365),
                "created_at": now,
                "history": [{"at": now, "event": "seeded", "by": "reset_demo"}],
            })
    return docs


POLICY_SOURCE = {
    "_id": "src_policy_handbook",
    "tenant_id": "*",
    "kind": "text",
    "raw_text": "\n".join(POLICY_RULES),
    "file_name": None,
    "submitted_by": "policy-owner",
    "synthetic": True,
}

# The demo scenario, used by the page's "Load example" button.
DEMO_SOURCE_TEXT = (
    "Manager note (screenshot text): Order 4821 may be refunded without returning the item. "
    "One-time exception approved by store manager for customer C-200."
)
DEMO_BROAD_MEMORY = "VIP customers may keep the item when they are refunded; no return is required."
DEMO_NARROW_MEMORY = (
    "Approved exception: order 4821 may be refunded without returning the item "
    "(return_required = false). This applies to order 4821 only."
)
