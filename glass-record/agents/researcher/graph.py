from langgraph.graph import END, START, StateGraph

from agents.shared.state import ResearcherState
from agents.researcher.nodes import analyse_and_store_evidence, scrape_node, search_node


def build_researcher_graph() -> StateGraph:
    g = StateGraph(ResearcherState)
    g.add_node("search", search_node)
    g.add_node("scrape", scrape_node)
    g.add_node("analyse_store", analyse_and_store_evidence)

    g.add_edge(START, "search")
    g.add_edge("search", "scrape")
    g.add_edge("scrape", "analyse_store")
    g.add_edge("analyse_store", END)

    return g.compile()
