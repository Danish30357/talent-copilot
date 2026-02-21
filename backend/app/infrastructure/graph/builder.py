"""
LangGraph builder — constructs the StateGraph with conditional edges.

State machine flow:
  conversation → tool_decision → confirmation_pending → response_generation
                                                      ↘ (after approval via API)
                                                        tool_execution → response_generation

Tool execution is NEVER reachable directly from the graph.
It is only invoked programmatically after confirmation approval.
"""

from __future__ import annotations

from functools import partial

from langgraph.graph import END, StateGraph

from app.domain.interfaces import IConfirmationRepository, IJobRepository
from app.infrastructure.graph.nodes import (
    confirmation_pending_node,
    conversation_node,
    response_generation_node,
    tool_decision_node,
    tool_execution_node,
)
from app.infrastructure.graph.state import GraphStateDict


def _route_from_tool_decision(state: GraphStateDict) -> str:
    """Route based on whether a tool was detected."""
    if state.get("tool_request"):
        return "confirmation_pending"
    return "response_generation"


def build_graph(
    confirmation_repo: IConfirmationRepository,
    job_repo: IJobRepository,
) -> StateGraph:
    """
    Build and compile the LangGraph.

    The graph is intentionally linear for the normal chat flow:
      conversation → tool_decision → [confirmation_pending | response_generation]

    tool_execution is registered but only routed to programmatically
    after confirmation approval (from the Confirmations API endpoint).
    """
    graph = StateGraph(GraphStateDict)

    # Register nodes
    graph.add_node("conversation", conversation_node)
    graph.add_node("tool_decision", tool_decision_node)
    graph.add_node(
        "confirmation_pending",
        partial(confirmation_pending_node, confirmation_repo=confirmation_repo),
    )
    graph.add_node(
        "tool_execution",
        partial(
            tool_execution_node,
            confirmation_repo=confirmation_repo,
            job_repo=job_repo,
        ),
    )
    graph.add_node("response_generation", response_generation_node)

    # Edges
    graph.set_entry_point("conversation")
    graph.add_edge("conversation", "tool_decision")
    graph.add_conditional_edges(
        "tool_decision",
        _route_from_tool_decision,
        {
            "confirmation_pending": "confirmation_pending",
            "response_generation": "response_generation",
        },
    )
    graph.add_edge("confirmation_pending", "response_generation")
    graph.add_edge("tool_execution", "response_generation")
    graph.add_edge("response_generation", END)

    return graph.compile()
