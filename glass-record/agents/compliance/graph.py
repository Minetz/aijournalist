from langgraph.graph import END, START, StateGraph

from agents.shared.state import ComplianceState
from agents.compliance.nodes import check_mandate_drift, scan_for_injection


def _should_continue(state: ComplianceState) -> str:
    """Skip mandate drift check if injection was already caught."""
    if state.get("passed") is False:
        return "end"
    return "check_drift"


def build_compliance_graph() -> StateGraph:
    g = StateGraph(ComplianceState)
    g.add_node("scan_injection", scan_for_injection)
    g.add_node("check_drift", check_mandate_drift)

    g.add_edge(START, "scan_injection")
    g.add_conditional_edges(
        "scan_injection",
        _should_continue,
        {"check_drift": "check_drift", "end": END},
    )
    g.add_edge("check_drift", END)

    return g.compile()
