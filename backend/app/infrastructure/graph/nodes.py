"""
LangGraph node functions — each represents a state in the conversation state machine.

States:
  conversation          → LLM generates response or signals tool intent
  tool_decision         → Parse LLM output for tool invocations
  confirmation_pending  → Create confirmation record in DB
  tool_execution        → Validate confirmation then dispatch background job
  response_generation   → Format final response text
"""

from __future__ import annotations

import json
import re
import uuid
from typing import Any, Dict

from langchain_core.messages import AIMessage, HumanMessage

from app.application.confirmation_service import ConfirmationService
from app.application.job_service import JobService
from app.domain.enums import ConfirmationStatus, ToolName
from app.domain.interfaces import IConfirmationRepository, IJobRepository
from app.infrastructure.graph.state import GraphStateDict
from app.infrastructure.llm.langchain_provider import get_llm


# ────────────────────────────────────────────────────────────
# Node 1: CONVERSATION
# ────────────────────────────────────────────────────────────

async def conversation_node(state: GraphStateDict) -> GraphStateDict:
    """
    Invoke the LLM with the current conversation context.
    The model may produce a normal reply or signal a tool request
    using a structured format:

    [TOOL_REQUEST]{"tool": "<name>", "payload": {...}}[/TOOL_REQUEST]
    """
    llm = get_llm()
    response = await llm.ainvoke(state["messages"])
    content = response.content if hasattr(response, "content") else str(response)

    state["messages"] = list(state["messages"]) + [AIMessage(content=content)]
    state["response_text"] = content
    state["current_state"] = "tool_decision"
    return state


# ────────────────────────────────────────────────────────────
# Node 2: TOOL DECISION
# ────────────────────────────────────────────────────────────

_TOOL_PATTERN = re.compile(
    r"\[TOOL_REQUEST\]\s*(?:```json)?\s*(\{.*?\})\s*(?:```)?\s*\[/TOOL_REQUEST\]", re.DOTALL
)


async def tool_decision_node(state: GraphStateDict) -> GraphStateDict:
    """
    Parse the latest AI message for a tool invocation signal.
    If found → transition to confirmation_pending.
    If not → transition to response_generation.
    """
    response_text = state.get("response_text", "")
    match = _TOOL_PATTERN.search(response_text)

    if match:
        try:
            tool_data = json.loads(match.group(1))
            tool_name = tool_data.get("tool", "")
            tool_payload = tool_data.get("payload", {})

            # Validate tool name
            try:
                ToolName(tool_name)
            except ValueError:
                state["current_state"] = "response_generation"
                state["tool_request"] = None
                return state

            state["tool_request"] = {
                "tool_name": tool_name,
                "tool_payload": tool_payload,
            }
            state["current_state"] = "confirmation_pending"
        except (json.JSONDecodeError, KeyError):
            state["current_state"] = "response_generation"
            state["tool_request"] = None
    else:
        state["current_state"] = "response_generation"
        state["tool_request"] = None

    return state


# ────────────────────────────────────────────────────────────
# Node 3: CONFIRMATION PENDING
# ────────────────────────────────────────────────────────────

async def confirmation_pending_node(
    state: GraphStateDict,
    confirmation_repo: IConfirmationRepository,
) -> GraphStateDict:
    """
    Create a pending confirmation record in the DB.
    The tool CANNOT execute until this confirmation is approved.
    """
    tool_request = state.get("tool_request")
    if not tool_request:
        state["current_state"] = "response_generation"
        return state

    service = ConfirmationService(confirmation_repo)
    confirmation = await service.request_confirmation(
        tenant_id=uuid.UUID(state["tenant_id"]),
        user_id=uuid.UUID(state["user_id"]),
        session_id=uuid.UUID(state["session_id"]),
        tool_name=ToolName(tool_request["tool_name"]),
        tool_payload=tool_request["tool_payload"],
    )

    state["confirmation_id"] = str(confirmation.id)
    state["confirmation_required"] = True
    state["confirmation_details"] = {
        "tool_name": tool_request["tool_name"],
        "tool_payload": tool_request["tool_payload"],
        "confirmation_id": str(confirmation.id),
    }

    # Clean the tool request from the response text
    clean_text = _TOOL_PATTERN.sub("", state.get("response_text", "")).strip()
    if not clean_text:
        tool_label = tool_request["tool_name"].replace("_", " ").title()
        clean_text = (
            f"I'd like to use the **{tool_label}** tool. "
            f"Please confirm to proceed."
        )
    state["response_text"] = clean_text
    state["current_state"] = "response_generation"
    return state


# ────────────────────────────────────────────────────────────
# Node 4: TOOL EXECUTION  (called after confirmation approval)
# ────────────────────────────────────────────────────────────

async def tool_execution_node(
    state: GraphStateDict,
    confirmation_repo: IConfirmationRepository,
    job_repo: IJobRepository,
) -> GraphStateDict:
    """
    Validate the confirmation and dispatch the tool as a background job.

    This node is ONLY reachable after the user has approved the confirmation
    via the /confirmations/{id}/decide endpoint. It is NOT reachable from
    the normal graph flow — the graph terminates at confirmation_pending.
    """
    tool_request = state.get("tool_request")
    confirmation_id = state.get("confirmation_id")

    if not tool_request or not confirmation_id:
        state["current_state"] = "response_generation"
        state["response_text"] = "No tool execution pending."
        return state

    service = ConfirmationService(confirmation_repo)
    try:
        await service.validate_for_execution(
            tenant_id=uuid.UUID(state["tenant_id"]),
            confirmation_id=uuid.UUID(confirmation_id),
            tool_name=tool_request["tool_name"],
            tool_payload=tool_request["tool_payload"],
        )
    except Exception as e:
        state["response_text"] = f"Tool execution denied: {str(e)}"
        state["current_state"] = "response_generation"
        return state

    # Create job and dispatch
    job_service = JobService(job_repo)
    job = await job_service.create_job(
        tenant_id=uuid.UUID(state["tenant_id"]),
        user_id=uuid.UUID(state["user_id"]),
        session_id=uuid.UUID(state["session_id"]),
        tool_name=ToolName(tool_request["tool_name"]),
    )

    from app.infrastructure.jobs.tasks import dispatch_tool_task

    dispatch_tool_task(
        job_id=str(job.id),
        tenant_id=state["tenant_id"],
        user_id=state["user_id"],
        session_id=state["session_id"],
        tool_name=tool_request["tool_name"],
        tool_payload=tool_request["tool_payload"],
    )

    state["tool_result"] = {"job_id": str(job.id), "status": "queued"}
    state["response_text"] = (
        f"Tool **{tool_request['tool_name']}** has been dispatched. "
        f"Job ID: `{job.id}`. I'll update you when it completes."
    )
    state["current_state"] = "response_generation"
    return state


# ────────────────────────────────────────────────────────────
# Node 5: RESPONSE GENERATION
# ────────────────────────────────────────────────────────────

async def response_generation_node(state: GraphStateDict) -> GraphStateDict:
    """
    Terminal node — formats the final response.
    No mutations needed unless we want post-processing.
    """
    state["current_state"] = "done"
    return state
