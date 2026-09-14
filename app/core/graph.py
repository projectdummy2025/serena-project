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

import re
from datetime import datetime
from app.services import system_service
from app.memory import vault_writer

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
        "intent": res.get("intent", "TASK"),
        "chat_response": res.get("chat_response", ""),
        "claude_instruction": res.get("claude_instruction", ""),
        "system_action": res.get("system_action", ""),
        "project_name": res.get("project_name", ""),
        "repo_url": res.get("repo_url", ""),
        "env_content": res.get("env_content", ""),
        "linux_command": res.get("linux_command", "")
    }

async def worker_system_step(state: AgentState) -> Dict[str, Any]:
    """Execute deterministic Linux/System operational tasks instantly (< 1s)."""
    system_action = state.get("system_action", "SETUP_PROJECT")
    repo_url = state.get("repo_url", "")
    project_name = state.get("project_name", "")
    env_content = state.get("env_content", "")
    linux_cmd = state.get("linux_command", "")
    prompt = state.get("user_prompt", "")

    # Eksekusi setup proyek jika terdapat git clone / URL repo
    if system_action == "SETUP_PROJECT" or "github.com" in prompt or repo_url:
        if not repo_url and "github.com" in prompt:
            matches = re.findall(r"https?://github\.com/[^\s]+\.git", prompt)
            repo_url = matches[0] if matches else ""

        if not project_name and repo_url:
            project_name = repo_url.rstrip("/").split("/")[-1].replace(".git", "")
        elif not project_name:
            project_name = "active-project"

        if not env_content and ("PORT_" in prompt or "DATABASE_URL" in prompt or "API_KEY" in prompt):
            env_content = prompt

        setup_res = await system_service.setup_full_project(
            repo_url=repo_url,
            project_name=project_name,
            env_content=env_content
        )

        # Catat ke Obsidian Second Brain (Worker 5: Penulis)
        today_date = datetime.now().strftime("%Y-%m-%d")
        project_doc = (
            f"# Proyek Aktif: {project_name}\n\n"
            f"- Status : Aktif\n"
            f"- Repositori : {repo_url}\n"
            f"- Direktori : `{setup_res.get('project_path', '')}`\n\n"
            f"## Konfigurasi Lingkungan :\n"
            f"{setup_res.get('env_output', '')}\n\n"
            f"## Status Inisialisasi :\n"
            f"- Kloning : {setup_res.get('clone_output', 'Selesai')}\n"
            f"- CodeGraph : {setup_res.get('codegraph_output', 'Selesai')}\n\n"
            f"## Konsep Terkait :\n"
            f"- [[Catatan Harian/{today_date}]] — Inisialisasi awal proyek.\n"
        )
        vault_writer.save_active_project(project_name, project_doc)

        report = (
            f"*Inisialisasi Proyek Selesai*\n\n"
            f"- *Nama Proyek* : `{project_name}`\n"
            f"- *Repositori* : `{repo_url}`\n"
            f"- *Status Kloning* : Berhasil\n"
            f"- *File .env* : {'Tersimpan' if env_content else 'Tidak disertakan'}\n"
            f"- *Dokumentasi* : Berkas `Proyek Aktif/{project_name}.md` tercatat di Obsidian Second Brain.\n\n"
            f"Lingkungan proyek siap digunakan untuk pembedahan dan pengembangan kode."
        )
        return {"worker_output": report}

    # Eksekusi perintah Linux umum
    command_to_run = linux_cmd or prompt
    cmd_res = await system_service.execute_linux_command(command_to_run)
    output = cmd_res.get("output") or cmd_res.get("error") or "Perintah telah dieksekusi."
    return {"worker_output": output}

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
    """Curate final executive report & selectively log transactions to Obsidian Daily Log."""
    prompt = state.get("user_prompt", "")
    output = state.get("worker_output", "")
    user_id = state.get("user_id", 0)
    
    curation_res = await orchestrator.curate_claude_output(prompt, output, user_id=user_id)
    
    is_logworthy = curation_res.get("is_logworthy", True)
    log_title = curation_res.get("log_title", f"Aktivitas: {prompt[:30]}")
    curated = curation_res.get("curated_text", output)
    
    if is_logworthy:
        try:
            append_to_daily_log(title=log_title, content=curated)
        except Exception as e:
            logger.warning(f"Gagal mencatat ke Obsidian Daily Log: {e}")
    else:
        logger.info(f"Mengabaikan pencatatan ke Daily Log untuk instruksi transient/keisengan: '{prompt[:30]}'")
        
    return {"final_report": curated}

def route_intent(state: AgentState) -> Literal["worker_system", "worker_claude", "worker_research", "__end__"]:
    """Conditional router based on intent."""
    intent = state.get("intent")
    if intent in ("CHAT", "BRAINSTORMING", "SAVE_NOTE"):
        return END
    elif intent == "SYSTEM":
        return "worker_system"
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
    workflow.add_node("worker_system", worker_system_step)
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
            "worker_system": "worker_system",
            "worker_claude": "worker_claude",
            "worker_research": "worker_research",
            END: END
        }
    )
    
    workflow.add_edge("worker_system", "curate_report")
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

