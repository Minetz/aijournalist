from langgraph.graph import END, START, StateGraph

from agents.shared.state import EditorState
from agents.editor.nodes import (
    decompose_mandate,
    select_story,
    spawn_researchers,
    synthesise_results,
)
from agents.editor.publish_nodes import synthesise_and_publish


def _compliance_gate(state: EditorState) -> str:
    """Route to publish if compliance passed, else end the cycle."""
    return "publish" if state.get("compliance_passed", False) else "end"


def build_graph() -> StateGraph:
    # Import here to avoid circular imports at module level
    from agents.researcher.graph import build_researcher_graph

    researcher_graph = build_researcher_graph()

    g = StateGraph(EditorState)
    g.add_node("select_story", select_story)
    g.add_node("decompose_mandate", decompose_mandate)
    g.add_node("researcher_worker", researcher_graph)
    g.add_node("synthesise_results", synthesise_results)   # runs compliance
    g.add_node("publish", synthesise_and_publish)          # legal tree + Ghost

    g.add_edge(START, "select_story")
    g.add_edge("select_story", "decompose_mandate")
    g.add_conditional_edges("decompose_mandate", spawn_researchers, ["researcher_worker"])
    g.add_edge("researcher_worker", "synthesise_results")
    g.add_conditional_edges(
        "synthesise_results",
        _compliance_gate,
        {"publish": "publish", "end": END},
    )
    g.add_edge("publish", END)

    return g.compile()
