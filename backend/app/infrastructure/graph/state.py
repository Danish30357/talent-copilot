"""
LangGraph state definition — TypedDict describing the state passed between nodes.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, TypedDict

from langchain_core.messages import BaseMessage


class GraphStateDict(TypedDict, total=False):
    """
    State schema for the TalentCopilot LangGraph.

    Fields:
        messages:               LangChain messages (context + conversation)
        current_state:          Current node in the state machine
        tool_request:           Detected tool invocation request (or None)
        confirmation_id:        UUID of the confirmation record (if created)
        confirmation_details:   Human-readable confirmation details for the frontend
        tool_result:            Result from executed tool (or None)
        tenant_id:              Tenant UUID (string)
        user_id:                User UUID (string)
        session_id:             Session UUID (string)
        response_text:          Final text response to return
        confirmation_required:  Whether a confirmation prompt was generated
    """

    messages: List[BaseMessage]
    current_state: str
    tool_request: Optional[Dict[str, Any]]
    confirmation_id: Optional[str]
    confirmation_details: Optional[Dict[str, Any]]
    tool_result: Optional[Dict[str, Any]]
    tenant_id: str
    user_id: str
    session_id: str
    response_text: str
    confirmation_required: bool
