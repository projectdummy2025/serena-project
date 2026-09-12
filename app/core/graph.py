import logging
from typing import Dict, Any, Literal
from langgraph.graph import StateGraph, START, END

from app.core.state import AgentState
from app.core.supervisor import supervisor_reason_node, supervisor_evaluate_node
from app.memory.obsidian_engine import search_obsidian_vault
from app.memory.vault_writer import append_to_daily_log
from app.services.research_service import conduct_research_task
from app.services import claude_service
from app.services import orchestrator

logger = logging.getLogger(__name__)

async def retrieve_node(state: AgentState) -> Dict[str, Any]:
    """Retrieve relevant second brain knowledge from Obsidian Vault."""
    prompt = state.get("user_prompt", "")
    context = search_obsidian_vault(prompt, top_k=2)
    return {"retrieved_context": context}

async def supervisor_reason_step(state: AgentState) -> Dict[str, Any]:
    """Reasoning step by Supervisor Serena."""
    prompt = state.get("user_prompt", "")
    user_id = state.get("user_id", 0)
    context = state.get("retrieved_context", "")
    
    res = await supervisor_reason_node(prompt, user_id, context)
    return {
        "intent": res["intent"],
        "chat_response": res["chat_response"],
        "claude_instruction": res["claude_instruction"]
    }

async def worker_claude_step(state: AgentState) -> Dict[str, Any]:
    """Execute technical task via Claude Code CLI Sub-Agent."""
    instruction = state.get("claude_instruction") or state.get("user_prompt", "")
    output = await claude_service.execute_claude_task(
        prompt=instruction,
        progress_callback=None
    )
    return {"worker_output": output}

async def worker_research_step(state: AgentState) -> Dict[str, Any]:
    """Execute web research task via DuckDuckGo Researcher Sub-Agent."""
    query = state.get("claude_instruction") or state.get("user_prompt", "")
    output = await conduct_research_task(query)
    return {"worker_output": output}

async def supervisor_evaluate_step(state: AgentState) -> Dict[str, Any]:
    """Evaluate worker output in ReAct loop."""
    prompt = state.get("user_prompt", "")
    output = state.get("worker_output", "")
    count = state.get("retry_count", 0)
    
    res = await supervisor_evaluate_node(prompt, output, count)
    status = res.get("status", "SUCCESS")
    improved = res.get("improved_instruction", "")
    
    updates = {
        "evaluation_status": status,
        "eval_feedback": res.get("feedback", ""),
        "retry_count": count + 1 if status == "RETRY" else count
    }
    if status == "RETRY" and improved:
        updates["claude_instruction"] = improved
    return updates

async def curate_report_step(state: AgentState) -> Dict[str, Any]:
    """Curate final executive report & log transaction to Obsidian Daily Log."""
    prompt = state.get("user_prompt", "")
    output = state.get("worker_output", "")
    user_id = state.get("user_id", 0)
    
    curated = await orchestrator.curate_claude_output(prompt, output, user_id=user_id)
    
    try:
        append_to_daily_log(title=f"Aktivitas Telegram: {prompt[:40]}", content=curated)
    except Exception as e:
        logger.warning(f"Gagal mencatat ke Obsidian Daily Log: {e}")
        
    return {"final_report": curated}

def route_intent(state: AgentState) -> Literal["worker_claude", "worker_research", "__end__"]:
    """Conditional router based on intent."""
    intent = state.get("intent")
    if intent in ("CHAT", "BRAINSTORMING", "SAVE_NOTE"):
        return END
    elif intent == "RESEARCH":
        return "worker_research"
    return "worker_claude"

def route_evaluation(state: AgentState) -> Literal["worker_claude", "curate_report"]:
    """Conditional router based on ReAct evaluation status."""
    if state.get("evaluation_status") == "RETRY" and state.get("retry_count", 0) < 2:
        return "worker_claude"
    return "curate_report"

def build_agent_graph():
    """Build and compile the LangGraph StateGraph workflow."""
    workflow = StateGraph(AgentState)

    workflow.add_node("retrieve", retrieve_node)
    workflow.add_node("supervisor_reason", supervisor_reason_step)
    workflow.add_node("worker_claude", worker_claude_step)
    workflow.add_node("worker_research", worker_research_step)
    workflow.add_node("supervisor_evaluate", supervisor_evaluate_step)
    workflow.add_node("curate_report", curate_report_step)

    workflow.add_edge(START, "retrieve")
    workflow.add_edge("retrieve", "supervisor_reason")
    
    workflow.add_conditional_edges(
        "supervisor_reason",
        route_intent,
        {
            "worker_claude": "worker_claude",
            "worker_research": "worker_research",
            END: END
        }
    )
    
    workflow.add_edge("worker_claude", "supervisor_evaluate")
    workflow.add_edge("worker_research", "supervisor_evaluate")
    
    workflow.add_conditional_edges(
        "supervisor_evaluate",
        route_evaluation,
        {
            "worker_claude": "worker_claude",
            "curate_report": "curate_report"
        }
    )
    
    workflow.add_edge("curate_report", END)

    return workflow.compile()

agent_app = build_agent_graph()
