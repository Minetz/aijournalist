import json

import structlog
from google.cloud import firestore
from langchain_core.messages import HumanMessage
from pydantic import BaseModel

from agents.shared.base_agent import get_journalist_doc, log_action
from agents.shared.gemini import get_llm
from agents.shared.state import ComplianceState
from agents.compliance.prompts import INJECTION_SCAN_PROMPT, MANDATE_DRIFT_PROMPT

log = structlog.get_logger()


class DriftAssessment(BaseModel):
    passed: bool
    mandate_alignment_score: float
    drift_flags: list[str]
    injection_flags: list[str]
    reasoning: str


class InjectionScan(BaseModel):
    injection_detected: bool
    confidence: float
    patterns_found: list[str]


async def scan_for_injection(state: ComplianceState) -> dict:
    """
    Scan story title and sub-questions for prompt injection patterns.
    Runs before mandate drift check — a detected injection is an immediate fail.
    """
    texts_to_scan = [state["selected_story"]] + state["sub_questions"]
    combined = "\n".join(texts_to_scan)

    llm = get_llm(temperature=0.0).with_structured_output(InjectionScan)
    prompt = INJECTION_SCAN_PROMPT.format(text=combined)
    scan: InjectionScan = await llm.ainvoke([HumanMessage(content=prompt)])

    db = firestore.AsyncClient()
    await log_action(
        db,
        state["config"].journalist_id,
        state["cycle_id"],
        "injection_scan",
        {
            "injection_detected": scan.injection_detected,
            "confidence": scan.confidence,
            "patterns_found": scan.patterns_found,
        },
    )

    if scan.injection_detected and scan.confidence > 0.7:
        log.warning(
            "injection_detected",
            journalist_id=state["config"].journalist_id,
            confidence=scan.confidence,
            patterns=scan.patterns_found,
        )
        return {
            "passed": False,
            "reasoning": f"Prompt injection detected (confidence {scan.confidence:.2f}): "
                         + "; ".join(scan.patterns_found),
        }

    return {}  # no injection — continue to mandate drift check


async def check_mandate_drift(state: ComplianceState) -> dict:
    """
    Compare the selected story and sub-questions against the original mandate
    loaded from Firestore (never from the request payload).
    """
    # Short-circuit if injection was already caught
    if not state.get("passed", True):
        return {}

    db = firestore.AsyncClient()
    journalist_doc = await get_journalist_doc(db, state["config"].journalist_id)
    mandate = journalist_doc["mandate"]
    jurisdiction = journalist_doc["jurisdiction"]

    sub_q_text = "\n".join(f"- {q}" for q in state["sub_questions"])

    llm = get_llm(temperature=0.0).with_structured_output(DriftAssessment)
    prompt = MANDATE_DRIFT_PROMPT.format(
        mandate=mandate,
        jurisdiction=jurisdiction,
        story_title=state["selected_story"],
        sub_questions=sub_q_text,
    )
    assessment: DriftAssessment = await llm.ainvoke([HumanMessage(content=prompt)])

    await log_action(
        db,
        state["config"].journalist_id,
        state["cycle_id"],
        "compliance_check",
        {
            "passed": assessment.passed,
            "mandate_alignment_score": assessment.mandate_alignment_score,
            "drift_flags": assessment.drift_flags,
            "injection_flags": assessment.injection_flags,
            "reasoning": assessment.reasoning,
        },
    )

    # Write to dedicated compliance_log collection for public audit trail
    await (
        db.collection("journalists")
        .document(state["config"].journalist_id)
        .collection("compliance_log")
        .add(
            {
                "cycle_id": state["cycle_id"],
                "check_type": "mandate_drift",
                "passed": assessment.passed,
                "mandate_alignment_score": assessment.mandate_alignment_score,
                "drift_flags": assessment.drift_flags,
                "injection_flags": assessment.injection_flags,
                "reasoning": assessment.reasoning,
            }
        )
    )

    if not assessment.passed:
        log.warning(
            "compliance_failed",
            journalist_id=state["config"].journalist_id,
            alignment_score=assessment.mandate_alignment_score,
            flags=assessment.drift_flags,
        )
    else:
        log.info(
            "compliance_passed",
            journalist_id=state["config"].journalist_id,
            alignment_score=assessment.mandate_alignment_score,
        )

    return {
        "passed": assessment.passed,
        "reasoning": assessment.reasoning,
    }
