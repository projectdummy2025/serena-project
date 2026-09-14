from typing import TypedDict, List, Dict, Any, Optional

class AgentState(TypedDict, total=False):
    """
    LangGraph Agent State representation for the Hierarchical Multi-Agent System.
    """
    user_id: int
    user_prompt: str
    retrieved_context: str
    intent: str
    chat_response: str
    claude_instruction: str
    worker_output: str
    evaluation_status: str
    eval_feedback: str
    retry_count: int
    final_report: str
    sessionTopicBuffer: List[str]
    pendingConceptSummary: str
    system_action: str
    project_name: str
    repo_url: str
    env_content: str
    linux_command: str
    progress_callback: Optional[Any]

