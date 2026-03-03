from langgraph.graph import END, START, StateGraph

from agents.shared.state import ResearcherState
from agents.researcher.nodes import grounded_research


def build_researcher_graph() -> StateGraph:
    g = StateGraph(ResearcherState)
    g.add_node("research", grounded_research)

    g.add_edge(START, "research")
    g.add_edge("research", END)

    return g.compile()
