"""Background tasks for django-q2 task queue."""

import time
import logging
from django.utils import timezone

from .models import (
    AutomationJob, AutomationTask, AutomationJobStatus, AutomationTaskStatus, Paper,
    AgentStep,
)

logger = logging.getLogger(__name__)

MAX_RETRIES = 2
RETRY_DELAY = 5  # seconds


def _run_with_retry(fn, task, *args, **kwargs):
    """Run a function with retries on connection/timeout errors."""
    last_error = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            if attempt > 0:
                AgentStep.objects.create(
                    task=task, step_type='output',
                    content=f'Retrying (attempt {attempt + 1}/{MAX_RETRIES + 1})...'
                )
                time.sleep(RETRY_DELAY * attempt)
            return fn(*args, **kwargs)
        except Exception as e:
            last_error = e
            error_str = str(e).lower()
            # Only retry on connection/timeout/rate-limit errors
            is_retryable = any(kw in error_str for kw in [
                'connection', 'timeout', 'rate limit', '429', '503', '502',
                'temporarily unavailable', 'overloaded', 'retry'
            ])
            if not is_retryable or attempt == MAX_RETRIES:
                raise
            logger.warning(f'Retryable error on attempt {attempt + 1}: {e}')
    raise last_error


def run_automation_pipeline(project_id: int):
    """Run the full automation pipeline for a project."""
    job = AutomationJob.objects.create(
        project_id=project_id,
        status=AutomationJobStatus.RUNNING,
        started_at=timezone.now(),
    )

    def start_task(name: str) -> AutomationTask:
        return AutomationTask.objects.create(
            job=job, name=name, status=AutomationTaskStatus.RUNNING, started_at=timezone.now()
        )

    def complete_task(task: AutomationTask, status: str, message: str = "", result: dict | None = None):
        task.status = status
        task.message = message
        task.result_json = result
        task.progress = 100
        task.finished_at = timezone.now()
        task.save(update_fields=['status', 'message', 'result_json', 'progress', 'finished_at', 'updated_at'])

    def fail_job(message: str):
        job.status = AutomationJobStatus.FAILED
        job.message = message
        job.finished_at = timezone.now()
        job.save(update_fields=['status', 'message', 'finished_at', 'updated_at'])

    try:
        # 1) Initial research
        t1 = start_task('initial_research')
        AgentStep.objects.create(task=t1, step_type='output', content='Searching literature and generating hypotheses...')
        try:
            from agents_sdk.initial_research_agents.manager import InitialResearchServiceManager

            def _run_research():
                return InitialResearchServiceManager().run_for_project_sync(project_id)

            out1 = _run_with_retry(_run_research, t1)
            complete_task(t1, AutomationTaskStatus.SUCCESS, result=out1.dict())
            AgentStep.objects.create(task=t1, step_type='output', content='Literature review complete')
        except Exception as e:
            complete_task(t1, AutomationTaskStatus.FAILED, message=str(e)[:500])
            AgentStep.objects.create(task=t1, step_type='output', content=f'Failed: {str(e)[:200]}')
            fail_job(str(e)[:500])
            return

        # 2) Initial draft (only if paper empty)
        t2 = start_task('initial_draft')
        try:
            paper = Paper.objects.filter(project_id=project_id).first()
            if paper and (paper.content_raw or '').strip():
                complete_task(t2, AutomationTaskStatus.CANCELLED, message='Skipped: paper already has content')
            else:
                AgentStep.objects.create(task=t2, step_type='output', content='Drafting abstract and literature review...')
                from agents_sdk.paper_draft_agents.manager import PaperDraftServiceManager

                def _run_draft():
                    return PaperDraftServiceManager().run_for_project_sync(project_id)

                out2 = _run_with_retry(_run_draft, t2)
                complete_task(t2, AutomationTaskStatus.SUCCESS, result=out2.dict())
                AgentStep.objects.create(task=t2, step_type='output', content='Draft complete')
        except Exception as e:
            complete_task(t2, AutomationTaskStatus.FAILED, message=str(e)[:500])
            AgentStep.objects.create(task=t2, step_type='output', content=f'Failed: {str(e)[:200]}')
            fail_job(str(e)[:500])
            return

        # 3) Hypothesis testing
        t3 = start_task('hypothesis_testing')
        AgentStep.objects.create(task=t3, step_type='output', content='Testing hypotheses with experiments...')
        try:
            from agents_sdk.hypothesis_testing_agents.manager import HypothesisTestingServiceManager

            def _run_testing():
                return HypothesisTestingServiceManager().run_for_project_sync(project_id)

            out3 = _run_with_retry(_run_testing, t3)
            complete_task(t3, AutomationTaskStatus.SUCCESS, result=out3.dict())
            AgentStep.objects.create(task=t3, step_type='output', content='Hypothesis testing complete')
        except Exception as e:
            complete_task(t3, AutomationTaskStatus.FAILED, message=str(e)[:500])
            AgentStep.objects.create(task=t3, step_type='output', content=f'Failed: {str(e)[:200]}')
            fail_job(str(e)[:500])
            return

        # 4) Compilation
        t4 = start_task('compilation')
        AgentStep.objects.create(task=t4, step_type='output', content='Compiling LaTeX manuscript...')
        try:
            from agents_sdk.compilation_agents.manager import CompilationServiceManager

            def _run_compilation():
                return CompilationServiceManager().run_for_project_sync(project_id)

            out4 = _run_with_retry(_run_compilation, t4)
            complete_task(t4, AutomationTaskStatus.SUCCESS, result=out4.dict())
            AgentStep.objects.create(task=t4, step_type='output', content='Paper compiled successfully')
        except Exception as e:
            complete_task(t4, AutomationTaskStatus.FAILED, message=str(e)[:500])
            AgentStep.objects.create(task=t4, step_type='output', content=f'Failed: {str(e)[:200]}')
            fail_job(str(e)[:500])
            return

        # Done
        job.status = AutomationJobStatus.SUCCESS
        job.finished_at = timezone.now()
        job.save(update_fields=['status', 'finished_at', 'updated_at'])
    except Exception as e:
        fail_job(str(e)[:500])
