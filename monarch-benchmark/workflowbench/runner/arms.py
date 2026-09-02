"""Pilot arms. Scripted, deterministic — they prove the pipeline, not the models.

OracleArm  = WorkArena's cheat(): reads the task's assertions and performs the
             correct API calls through the same tool surface agents get.
SloppyArm  = oracle plus one collateral write. Exists so the dual invariant has
             something to catch; if SloppyArm ever passes, the guard is broken.
NullArm    = does nothing. If NullArm ever passes, the task is vacuous (P3).
"""
from __future__ import annotations

import json
from typing import Any

from wb_world.episode import Episode

_SF_FIELD = {
    "phone": "Phone", "email": "Email", "title": "Title", "mailing_city": "MailingCity",
    "mobile_phone": "MobilePhone", "department": "Department", "fax": "Fax",
    "assistant_name": "AssistantName", "description": "Description",
    "stage_name": "StageName", "stage": "StageName", "amount": "Amount", "close_date": "CloseDate",
    "probability": "Probability", "next_step": "NextStep", "type": "Type",
}
_SF_BASE = "https://yourinstance.salesforce.com/services/data/v61.0/sobjects"
_SF_OBJECT = {"contacts": "Contact", "opportunities": "Opportunity", "leads": "Lead"}


def _sf_updates_from_assertions(task: dict[str, Any]):
    for a in task["info"]["assertions"]:
        if a["type"] == "salesforce_field_equals":
            yield _SF_OBJECT[a["collection"]], a["record_id"], _SF_FIELD[a["field"]], a["value"]
        elif a["type"] == "salesforce_contact_field_equals":
            yield "Contact", a["contact_id"], _SF_FIELD[a["field"]], a["value"]


class OracleArm:
    name = "oracle/scripted"

    def run(self, ep: Episode) -> None:
        # A minimal honest trajectory: discover, read, act.
        ep.api_search("salesforce update")
        for obj, rid, field, value in _sf_updates_from_assertions(ep.task):
            ep.api_fetch("PATCH", f"{_SF_BASE}/{obj}/{rid}", body=json.dumps({field: value}))


class SloppyArm(OracleArm):
    name = "sloppy/collateral"

    def run(self, ep: Episode) -> None:
        super().run(ep)
        # Collateral damage: trash the first Gmail message in the world, if any.
        msgs = getattr(getattr(ep.world, "gmail", None), "messages", None) or []
        if msgs:
            ep.api_fetch("POST",
                f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{msgs[0].id}/trash")


class NullArm:
    name = "null/no-action"

    def run(self, ep: Episode) -> None:
        return
