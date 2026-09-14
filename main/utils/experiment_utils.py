import json
import os
import sys
import tempfile
import subprocess
from typing import Optional

from django.utils import timezone


def _write_wrapper_and_code(temp_dir: str, user_code: str) -> str:
    """Create wrapper and user code files; return wrapper path.

    The wrapper exposes `params` and `record_result(data: any)` to the user code.
    User code should call `record_result` to persist a JSON-serializable result.
    """

    user_code_path = os.path.join(temp_dir, "user_code.py")
    with open(user_code_path, "w", encoding="utf-8") as f:
        f.write(user_code)

    wrapper_path = os.path.join(temp_dir, "wrapper.py")
    wrapper_src = (
        "import json, os, sys, traceback\n"
        "params = json.loads(os.environ.get('SIM_PARAMS_JSON', '{}'))\n"
        "_result_path = os.environ.get('SIM_RESULT_PATH')\n"
        "def record_result(obj):\n"
        "    if not _result_path: return\n"
        "    with open(_result_path, 'w', encoding='utf-8') as rf:\n"
        "        json.dump(obj, rf)\n"
        "g = {'params': params, 'record_result': record_result}\n"
        "try:\n"
        "    with open('user_code.py', 'r', encoding='utf-8') as uc:\n"
        "        code = uc.read()\n"
        "    exec(compile(code, 'user_code.py', 'exec'), g, g)\n"
        "except SystemExit as e:\n"
        "    raise\n"
        "except Exception as e:\n"
        "    traceback.print_exc()\n"
        "    sys.exit(1)\n"
    )
    with open(wrapper_path, "w", encoding="utf-8") as f:
        f.write(wrapper_src)
    return wrapper_path


def run_python_simulation(simulation, timeout_seconds: int = 30, python_executable: Optional[str] = None):
    """Execute Python code for the given Simulation instance.

    - Expects `simulation.code` to be Python code string.
    - Provides globals: `params` (dict from simulation.parameters) and `record_result(data)`.
    - Captures stdout/stderr, exit code; writes `result_json` if `record_result` is called.

    Security: The subprocess is sandboxed by stripping sensitive environment
    variables, restricting HOME/TMPDIR to the temp directory, and using '--'
    to prevent flag injection. The timeout is configurable via the SIM_TIMEOUT
    environment variable.
    """

    from main.models import SimulationStatus  # local import to avoid cycles

    if python_executable is None:
        python_executable = sys.executable

    # Allow the timeout to be configured via environment variable
    default_timeout = int(os.getenv('SIM_TIMEOUT', '30'))
    if timeout_seconds == 30:
        timeout_seconds = default_timeout

    # Mark as running
    simulation.status = SimulationStatus.RUNNING
    simulation.started_at = timezone.now()
    simulation.stdout = ""
    simulation.stderr = ""
    simulation.exit_code = None
    simulation.save(update_fields=["status", "started_at", "stdout", "stderr", "exit_code", "updated_at"])

    with tempfile.TemporaryDirectory(prefix="sim_") as temp_dir:
        result_path = os.path.join(temp_dir, "result.json")
        wrapper_path = _write_wrapper_and_code(temp_dir, simulation.code or "")

        env = os.environ.copy()
        env["SIM_PARAMS_JSON"] = json.dumps(simulation.parameters or {})
        env["SIM_RESULT_PATH"] = result_path

        # Strip sensitive env vars for sandboxing
        for key in ['OPENAI_API_KEY', 'SECRET_KEY', 'DATABASE_URL', 'SEMANTIC_SCHOLAR_API_KEY']:
            env.pop(key, None)
        env['HOME'] = temp_dir
        env['TMPDIR'] = temp_dir

        try:
            # Use '--' to prevent flag injection in the python command
            proc = subprocess.run(
                [python_executable, '--', wrapper_path],
                cwd=temp_dir,
                env=env,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
            )
            simulation.stdout = (proc.stdout or "")
            simulation.stderr = (proc.stderr or "")
            simulation.exit_code = int(proc.returncode)

            # Read result if produced
            if os.path.exists(result_path):
                try:
                    with open(result_path, "r", encoding="utf-8") as rf:
                        simulation.result_json = json.load(rf)
                except Exception:
                    simulation.result_json = None

            simulation.finished_at = timezone.now()
            if proc.returncode == 0:
                simulation.status = SimulationStatus.SUCCESS
            else:
                simulation.status = SimulationStatus.FAILED
            simulation.save(update_fields=[
                "stdout",
                "stderr",
                "exit_code",
                "result_json",
                "finished_at",
                "status",
                "updated_at",
            ])
        except subprocess.TimeoutExpired as e:
            simulation.stdout = e.stdout or ""
            simulation.stderr = (e.stderr or "") + "\n[TimeoutExpired]"
            simulation.exit_code = None
            simulation.finished_at = timezone.now()
            simulation.status = SimulationStatus.FAILED
            simulation.save(update_fields=[
                "stdout",
                "stderr",
                "exit_code",
                "finished_at",
                "status",
                "updated_at",
            ])
        except Exception as e:
            simulation.stderr = (simulation.stderr or "") + f"\n[RunnerError] {e}"
            simulation.finished_at = timezone.now()
            simulation.status = SimulationStatus.FAILED
            simulation.save(update_fields=["stderr", "finished_at", "status", "updated_at"])

    return simulation


def run_simulation(simulation, timeout_seconds: int = 30):
    """Dispatch to language-specific runner based on simulation.language."""
    from main.models import CodeLanguage

    lang = (simulation.language or CodeLanguage.PYTHON)
    if lang == CodeLanguage.PYTHON:
        return run_python_simulation(simulation, timeout_seconds=timeout_seconds)
    else:
        # Unsupported language
        simulation.stderr = (simulation.stderr or "") + f"\n[RunnerError] Unsupported language: {lang}"
        simulation.status = "failed"
        simulation.finished_at = timezone.now()
        simulation.save(update_fields=["stderr", "status", "finished_at", "updated_at"])
        return simulation


