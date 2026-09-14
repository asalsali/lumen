"""Real-time activity logging for agent pipeline steps."""
import logging
from django.utils import timezone

logger = logging.getLogger(__name__)


def log_agent_step(task_id: int, step_type: str, content: str, tool_name: str = ""):
    """Log an agent step to the database for real-time display.

    Args:
        task_id: The AutomationTask ID this step belongs to
        step_type: One of 'tool_call', 'tool_result', 'thinking', 'output'
        content: Description of what happened
        tool_name: Name of the tool called (for tool_call/tool_result types)
    """
    try:
        from main.models import AutomationTask, AgentStep
        task = AutomationTask.objects.get(pk=task_id)
        AgentStep.objects.create(
            task=task,
            step_type=step_type,
            tool_name=tool_name,
            content=content[:500],  # Truncate long content
        )
    except Exception as e:
        logger.warning(f"Failed to log agent step: {e}")


def log_activity(task_id: int, message: str):
    """Shortcut for logging a thinking/output step."""
    log_agent_step(task_id, 'output', message)


def log_tool_use(task_id: int, tool_name: str, description: str):
    """Shortcut for logging a tool call."""
    log_agent_step(task_id, 'tool_call', description, tool_name=tool_name)
