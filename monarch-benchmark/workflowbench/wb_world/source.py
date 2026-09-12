"""Human-readable provenance from frozen product metadata."""
from dataclasses import asdict, is_dataclass


def product_of(record):
    product = record.get("product") or (record.get("settings") or {}).get("product") or {}
    return asdict(product) if is_dataclass(product) else product if isinstance(product, dict) else {"name": product}


def comparison_notes(product):
    product = asdict(product) if is_dataclass(product) else product or {}
    source = product.get("source") or {}
    if not source:
        return []
    notes = [f"Tasks: {source['benchmark']} {source['version']}, split {source['split']}. "
             f"The source supplies {source['checker']}; WorkflowBench checks that nothing else changed "
             "and requires normal completion. These results are not the source benchmark's published score."]
    if not source.get("positive_half_is_end_state_only", True):
        notes.append("The original reward also evaluates the path or conversation; it is not an end-state-only score.")
    for participant in product.get("participants", []):
        notes.append(f"A paid {participant['role']} uses pinned model {participant['model']}; "
                     "its cost belongs to every attempt alongside the competitor's cost.")
    if source.get("benchmark") == "enterprise-ops-gym":
        notes.append("EnterpriseOps-Gym publishes no reference solution. No answer-key ceiling is asserted; "
                     "the initial task set uses reviewed rules for permitted changes.")
    return notes
