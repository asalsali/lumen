from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth import login
from django.contrib.auth.forms import UserCreationForm
from django.contrib import messages
from asgiref.sync import async_to_sync
from django import forms
from django.db.models import Q, Count
from django.utils import timezone
from django.urls import reverse
from .models import Simulation, Project, Paper, Hypothesis, Note, Literature, Citation, LiteratureSourceType, ProjectStatus, AutomationJob, AutomationTask, AutomationJobStatus, AutomationTaskStatus
from django.http import JsonResponse
import threading
from .utils.transcriptions import transcribe_file_like
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt
from django.middleware.csrf import get_token



def home(request):
    """Landing page using templates/home.html."""
    return render(request, 'home.html')


@login_required
def settings_view(request):
    from django.contrib.auth.forms import PasswordChangeForm
    from django.contrib.auth import update_session_auth_hash

    password_form = PasswordChangeForm(request.user)
    email_saved = False

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'update_email':
            new_email = request.POST.get('email', '').strip()
            if new_email:
                request.user.email = new_email
                request.user.save(update_fields=['email'])
                messages.success(request, 'Email updated.')
                email_saved = True
        elif action == 'change_password':
            password_form = PasswordChangeForm(request.user, request.POST)
            if password_form.is_valid():
                user = password_form.save()
                update_session_auth_hash(request, user)
                messages.success(request, 'Password changed.')
            else:
                messages.error(request, 'Please fix the errors below.')

    return render(request, 'settings.html', {
        'password_form': password_form,
        'email_saved': email_saved,
    })


@login_required
def dashboard(request):
    """Dashboard: research command center."""
    user = request.user

    # Build rich project cards with progress data
    projects = []
    for p in Project.objects.filter(owner=user).select_related('paper').order_by('-updated_at')[:6]:
        paper = getattr(p, 'paper', None)
        hyps = Hypothesis.objects.filter(project=p)
        sims = Simulation.objects.filter(project=p)
        job = p.automation_jobs.order_by('-created_at').first()

        has_paper = bool(paper and (paper.content_raw or '').strip())
        hyp_total = hyps.count()
        hyp_tested = hyps.exclude(status='proposed').count()
        sim_total = sims.count()
        sim_success = sims.filter(status='success').count()
        lit_count = Literature.objects.filter(citations__paper=paper).distinct().count() if paper else 0

        # Compute research phase
        if not job:
            phase = 'new'
        elif job.status == 'running':
            phase = 'automating'
        elif job.status == 'failed':
            phase = 'needs_attention'
        elif has_paper and hyp_total > 0 and hyp_tested == hyp_total:
            phase = 'complete'
        elif has_paper and hyp_total > 0:
            phase = 'testing'
        elif has_paper:
            phase = 'drafted'
        elif lit_count > 0:
            phase = 'reviewing'
        else:
            phase = 'starting'

        projects.append({
            'obj': p,
            'phase': phase,
            'has_paper': has_paper,
            'hyp_total': hyp_total,
            'hyp_tested': hyp_tested,
            'sim_total': sim_total,
            'sim_success': sim_success,
            'lit_count': lit_count,
            'job_status': job.status if job else None,
        })

    # Items needing attention
    needs_attention = []
    failed_jobs = AutomationJob.objects.filter(
        project__owner=user, status='failed'
    ).select_related('project').order_by('-created_at')[:3]
    for j in failed_jobs:
        needs_attention.append({
            'type': 'automation_failed',
            'title': f'Automation failed for "{j.project.name}"',
            'url': reverse('projects_detail', kwargs={'pk': j.project.pk}) + '?tab=automation',
        })

    proposed_hyps = Hypothesis.objects.filter(
        project__owner=user, status='proposed'
    ).select_related('project').order_by('-created_at')[:3]
    for h in proposed_hyps:
        needs_attention.append({
            'type': 'hypothesis_pending',
            'title': f'Hypothesis "{h.title}" awaiting evaluation',
            'url': reverse('projects_detail', kwargs={'pk': h.project.pk}) + '?tab=hypotheses',
        })

    failed_sims = Simulation.objects.filter(
        project__owner=user, status='failed'
    ).select_related('project').order_by('-updated_at')[:3]
    for s in failed_sims:
        needs_attention.append({
            'type': 'experiment_failed',
            'title': f'Experiment "{s.name}" failed',
            'url': reverse('experiments_detail', kwargs={'pk': s.pk}),
        })

    # Summary stats
    total_projects = Project.objects.filter(owner=user).count()
    total_hypotheses = Hypothesis.objects.filter(project__owner=user).count()
    total_supported = Hypothesis.objects.filter(project__owner=user, status='supported').count()
    total_experiments = Simulation.objects.filter(project__owner=user).count()
    total_exp_success = Simulation.objects.filter(project__owner=user, status='success').count()
    total_literature = Literature.objects.filter(citations__paper__project__owner=user).distinct().count()

    context = {
        'projects': projects,
        'needs_attention': needs_attention[:5],
        'total_projects': total_projects,
        'total_hypotheses': total_hypotheses,
        'total_supported': total_supported,
        'total_experiments': total_experiments,
        'total_exp_success': total_exp_success,
        'total_literature': total_literature,
    }
    return render(request, 'dashboard.html', context)


def signup(request):
    """User registration with auto-login, redirects to dashboard."""
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect('dashboard')
    else:
        form = UserCreationForm()
    return render(request, 'signup.html', {'form': form})


@login_required
def literature_search(request):
    """Synchronous wrapper view that runs async provider searches and renders results.

    Query via GET param `q`. Shows grouped results by source.
    """
    query = request.GET.get('q', '').strip()
    selected_project_id = request.GET.get('project') or None
    user_projects = Project.objects.filter(owner=request.user).order_by('name')
    results_by_source = None
    error = None
    if query:
        from .research_services import HttpClient, search_all

        def _run():
            async def go():
                client = HttpClient()
                try:
                    mailto = request.GET.get('mailto') or None
                    return await search_all(client, query=query, limit_per_source=10, mailto=mailto)
                finally:
                    await client.aclose()

            return async_to_sync(go)()

        from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
        try:
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(_run)
                results_by_source = future.result(timeout=10)
        except FuturesTimeout:
            error = "Search timed out — some providers may be rate-limiting. Try again shortly."
        except Exception as exc:
            error = str(exc)

    context = {
        'query': query,
        'results_by_source': results_by_source,
        'error': error,
        'projects': user_projects,
        'selected_project_id': int(selected_project_id) if selected_project_id else None,
    }
    return render(request, 'literature_search.html', context)


@login_required
def literature_link_to_project(request, project_pk: int):
    """Create or update a Literature entry from posted search result payload and link to the project's paper as a Citation.

    Expected POST fields (best-effort, many optional): title, url, doi, arxiv_id, open_access_pdf_url, year, authors (comma-separated), venue, abstract
    """
    project = get_object_or_404(Project, pk=project_pk, owner=request.user)
    paper, _ = Paper.objects.get_or_create(project=project, defaults={'title': project.name, 'abstract': project.abstract})
    if request.method == 'POST':
        title = (request.POST.get('title') or '').strip() or 'Untitled'
        doi = (request.POST.get('doi') or '').strip()
        arxiv_id = (request.POST.get('arxiv_id') or '').strip()
        url = (request.POST.get('url') or '').strip() or (request.POST.get('open_access_pdf_url') or '').strip()
        year = request.POST.get('year') or None
        abstract = request.POST.get('abstract') or ''
        authors_list = (request.POST.get('authors') or '').strip()
        venue = (request.POST.get('venue') or '').strip()

        # Heuristic: prefer DOI, then arXiv id, else title+url
        lit_q = Literature.objects.all()
        if doi:
            lit_q = lit_q.filter(doi=doi)
        elif arxiv_id:
            lit_q = lit_q.filter(arxiv_id=arxiv_id)
        else:
            lit_q = lit_q.filter(title=title, url=url)

        literature = lit_q.first()
        if not literature:
            literature = Literature.objects.create(
                title=title,
                authors=authors_list,
                journal_or_publisher=venue,
                year=int(year) if (year and year.isdigit()) else None,
                doi=doi,
                arxiv_id=arxiv_id,
                url=url,
                source_type=LiteratureSourceType.DOI if doi else (LiteratureSourceType.ARXIV if arxiv_id else LiteratureSourceType.URL),
                abstract=abstract,
            )

        # Link to paper via Citation (append to end)
        last_order = paper.citations.order_by('-order').first().order if paper.citations.exists() else 0
        Citation.objects.create(paper=paper, literature=literature, order=last_order + 1)

        # Trigger PDF ingestion in background
        def _ingest():
            from .utils.pdf_ingestion import ingest_literature_pdf
            ingest_literature_pdf(literature.pk)
        threading.Thread(target=_ingest, daemon=True).start()

        # Redirect back to literature search, preserving q and project selection
        q = request.GET.get('q') or ''
        return redirect(f"/literature/search/?q={q}&project={project.pk}")
    return redirect('literature_search')


class SimulationForm(forms.ModelForm):
    class Meta:
        model = Simulation
        fields = [
            'project', 'paper', 'hypothesis', 'name', 'description', 'code', 'language', 'parameters'
        ]
        widgets = {
            'project': forms.Select(attrs={'class': 'w-full rounded-xl border border-warm-200 bg-warm-50 px-3.5 py-2.5 text-[14px] text-warm-800 focus:bg-white focus:border-accent-500 focus:ring-2 focus:ring-accent-500/20 focus:outline-none transition-all'}),
            'language': forms.Select(attrs={'class': 'w-full rounded-xl border border-warm-200 bg-warm-50 px-3.5 py-2.5 text-[14px] text-warm-800 focus:bg-white focus:border-accent-500 focus:ring-2 focus:ring-accent-500/20 focus:outline-none transition-all'}),
            'name': forms.TextInput(attrs={'class': 'w-full rounded-xl border border-warm-200 bg-warm-50 px-3.5 py-2.5 text-[14px] text-warm-800 focus:bg-white focus:border-accent-500 focus:ring-2 focus:ring-accent-500/20 focus:outline-none transition-all', 'placeholder': 'e.g. Monte Carlo pricing simulation'}),
            'description': forms.Textarea(attrs={'class': 'w-full rounded-xl border border-warm-200 bg-warm-50 px-3.5 py-2.5 text-[14px] text-warm-800 focus:bg-white focus:border-accent-500 focus:ring-2 focus:ring-accent-500/20 focus:outline-none transition-all', 'rows': 3, 'placeholder': 'What does this experiment test?'}),
            'code': forms.Textarea(attrs={'class': 'w-full rounded-xl border border-warm-200 bg-warm-50 px-3.5 py-2.5 text-[13px] font-mono text-warm-800 focus:bg-white focus:border-accent-500 focus:ring-2 focus:ring-accent-500/20 focus:outline-none transition-all', 'rows': 15, 'placeholder': '# Your simulation code here...'}),
            'parameters': forms.Textarea(attrs={'class': 'w-full rounded-xl border border-warm-200 bg-warm-50 px-3.5 py-2.5 text-[13px] font-mono text-warm-800 focus:bg-white focus:border-accent-500 focus:ring-2 focus:ring-accent-500/20 focus:outline-none transition-all', 'rows': 4, 'placeholder': '{"key": "value"}'}),
        }


@login_required
def experiments_list(request):
    sims = Simulation.objects.filter(project__owner=request.user).order_by('-created_at')
    return render(request, 'experiments_list.html', {"simulations": sims})


@login_required
def experiments_create(request):
    if request.method == 'POST':
        form = SimulationForm(request.POST)
        if form.is_valid():
            sim = form.save()
            return redirect('experiments_detail', pk=sim.pk)
    else:
        # Limit project choices to the user's own projects
        form = SimulationForm()
        form.fields['project'].queryset = Project.objects.filter(owner=request.user)
    return render(request, 'experiments_create.html', {"form": form})


@login_required
def experiments_detail(request, pk: int):
    sim = get_object_or_404(Simulation, pk=pk, project__owner=request.user)
    return render(request, 'experiments_detail.html', {
        "simulation": sim,
        "csrf_token_value": get_token(request),
    })


@login_required
def experiments_run(request, pk: int):
    sim = get_object_or_404(Simulation, pk=pk, project__owner=request.user)
    sim.run(timeout_seconds=60)
    from .models import SimulationRun
    SimulationRun.objects.create(
        simulation=sim,
        parameters=sim.parameters,
        status=sim.status,
        started_at=sim.started_at,
        finished_at=sim.finished_at,
        exit_code=sim.exit_code,
        stdout=sim.stdout,
        stderr=sim.stderr,
        result_json=sim.result_json,
    )
    return redirect('experiments_detail', pk=sim.pk)


@login_required
def transcribe_audio(request):
    """Accept an uploaded audio blob and return a transcription as JSON.

    Expects multipart/form-data with field name 'audio'. Optional 'prompt'.
    """
    if request.method != 'POST':
        return JsonResponse({"error": "Method not allowed"}, status=405)

    audio = request.FILES.get('audio') or request.FILES.get('file')
    if not audio:
        return JsonResponse({"error": "Missing audio file"}, status=400)

    prompt = (request.POST.get('prompt') or '').strip() or None
    try:
        # Ensure file is at start
        if hasattr(audio, 'seek'):
            try:
                audio.seek(0)
            except Exception:
                pass
        text = transcribe_file_like(audio, response_format="json", prompt=prompt)
        return JsonResponse({"text": text})
    except Exception as exc:
        return JsonResponse({"error": str(exc)}, status=500)


class ProjectForm(forms.ModelForm):
    class Meta:
        model = Project
        fields = ['name', 'abstract', 'description']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'w-full rounded-xl border border-warm-200 bg-warm-50 px-3.5 py-2.5 text-[14px] text-warm-800 focus:bg-white focus:border-accent-500 focus:ring-2 focus:ring-accent-500/20 focus:outline-none transition-all', 'placeholder': 'Research project name'}),
            'abstract': forms.Textarea(attrs={'class': 'w-full rounded-xl border border-warm-200 bg-warm-50 px-3.5 py-2.5 text-[14px] text-warm-800 focus:bg-white focus:border-accent-500 focus:ring-2 focus:ring-accent-500/20 focus:outline-none transition-all', 'rows': 4, 'placeholder': 'A brief abstract of your research...'}),
            'description': forms.Textarea(attrs={'class': 'w-full rounded-xl border border-warm-200 bg-warm-50 px-3.5 py-2.5 text-[14px] text-warm-800 focus:bg-white focus:border-accent-500 focus:ring-2 focus:ring-accent-500/20 focus:outline-none transition-all', 'rows': 5, 'placeholder': 'Describe your research idea...'}),
        }


class PaperForm(forms.ModelForm):
    class Meta:
        model = Paper
        fields = ['title', 'abstract', 'content_raw', 'content_format']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'w-full rounded-xl border border-warm-200 bg-warm-50 px-3.5 py-2.5 text-[14px] text-warm-800 focus:bg-white focus:border-accent-500 focus:ring-2 focus:ring-accent-500/20 focus:outline-none transition-all', 'placeholder': 'Paper title'}),
            'abstract': forms.Textarea(attrs={'class': 'w-full rounded-xl border border-warm-200 bg-warm-50 px-3.5 py-2.5 text-[14px] text-warm-800 focus:bg-white focus:border-accent-500 focus:ring-2 focus:ring-accent-500/20 focus:outline-none transition-all', 'rows': 4, 'placeholder': 'Paper abstract...'}),
            'content_raw': forms.Textarea(attrs={'class': 'w-full rounded-xl border border-warm-200 bg-warm-50 px-3.5 py-2.5 text-[13px] font-mono text-warm-800 focus:bg-white focus:border-accent-500 focus:ring-2 focus:ring-accent-500/20 focus:outline-none transition-all', 'rows': 15, 'placeholder': 'Paper content...'}),
            'content_format': forms.Select(attrs={'class': 'w-full rounded-xl border border-warm-200 bg-warm-50 px-3.5 py-2.5 text-[14px] text-warm-800 focus:bg-white focus:border-accent-500 focus:ring-2 focus:ring-accent-500/20 focus:outline-none transition-all'}),
        }


class NoteForm(forms.ModelForm):
    class Meta:
        model = Note
        fields = ['title', 'body', 'pinned']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'w-full rounded-xl border border-warm-200 bg-warm-50 px-3.5 py-2.5 text-[14px] text-warm-800 focus:bg-white focus:border-accent-500 focus:ring-2 focus:ring-accent-500/20 focus:outline-none transition-all', 'placeholder': 'Note title'}),
            'body': forms.Textarea(attrs={'class': 'w-full rounded-xl border border-warm-200 bg-warm-50 px-3.5 py-2.5 text-[14px] text-warm-800 focus:bg-white focus:border-accent-500 focus:ring-2 focus:ring-accent-500/20 focus:outline-none transition-all', 'rows': 8, 'placeholder': 'Write your note...'}),
        }


class HypothesisForm(forms.ModelForm):
    class Meta:
        model = Hypothesis
        fields = ['title', 'statement']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'w-full rounded-xl border border-warm-200 bg-warm-50 px-3.5 py-2.5 text-[14px] text-warm-800 focus:bg-white focus:border-accent-500 focus:ring-2 focus:ring-accent-500/20 focus:outline-none transition-all', 'placeholder': 'Hypothesis title'}),
            'statement': forms.Textarea(attrs={'class': 'w-full rounded-xl border border-warm-200 bg-warm-50 px-3.5 py-2.5 text-[14px] text-warm-800 focus:bg-white focus:border-accent-500 focus:ring-2 focus:ring-accent-500/20 focus:outline-none transition-all', 'rows': 4, 'placeholder': 'State your hypothesis...'}),
        }


@login_required
def projects_list(request):
    projects = Project.objects.filter(owner=request.user).order_by('-updated_at')
    return render(request, 'projects_list.html', {'projects': projects})


@login_required
def projects_create(request):
    class ProjectUploadForm(ProjectForm):
        paper_file = forms.FileField(required=False, help_text="Optional. Upload a .pdf or .txt paper draft.")

    def extract_text(file) -> str:
        name = getattr(file, 'name', '') or ''
        if name.lower().endswith('.txt'):
            return file.read().decode('utf-8', errors='ignore')
        # Fallback to PDF
        try:
            from pypdf import PdfReader
            reader = PdfReader(file)
            pages = []
            for page in reader.pages:
                try:
                    pages.append(page.extract_text() or '')
                except Exception:
                    continue
            return "\n\n".join(pages)
        except Exception:
            return ""

    if request.method == 'POST':
        form = ProjectUploadForm(request.POST, request.FILES)
        if form.is_valid():
            project = form.save(commit=False)
            project.owner = request.user
            project.save()

            # Create or update the associated paper
            paper = Paper.objects.create(project=project, title=project.name, abstract=project.abstract)

            uploaded = form.cleaned_data.get('paper_file')
            if uploaded:
                full_text = extract_text(uploaded)
                # Placeholder: set first chars to abstract/description
                snippet = (full_text or '')[:500]
                paper.abstract = snippet[:300]
                paper.content_raw = full_text
                paper.save(update_fields=['abstract', 'content_raw', 'updated_at'])
                if not project.abstract:
                    project.abstract = paper.abstract
                if not project.description:
                    project.description = snippet
                project.save(update_fields=['abstract', 'description', 'updated_at'])

            # Start automation in background (parallel systems)
            _start_automation_background(project.pk)
            return redirect(f"/projects/{project.pk}/?tab=automation")
    else:
        form = ProjectUploadForm()
    return render(request, 'projects_create.html', {'form': form})


@login_required
def projects_detail(request, pk: int):
    project = get_object_or_404(Project, pk=pk, owner=request.user)
    paper, _ = Paper.objects.get_or_create(project=project, defaults={'title': project.name, 'abstract': project.abstract})

    experiments = Simulation.objects.filter(project=project).only(
        'id', 'name', 'status', 'description', 'updated_at'
    ).order_by('-updated_at')[:10]
    citations = paper.citations.select_related('literature').order_by('order')
    hypotheses = Hypothesis.objects.filter(project=project).only(
        'id', 'title', 'statement', 'status', 'updated_at'
    ).order_by('-updated_at')
    notes = project.notes.all()
    # Simpler query: only literature linked via citations (avoids expensive OR + DISTINCT)
    related_literature = Literature.objects.filter(
        citations__paper=paper
    ).only('id', 'title', 'url', 'year', 'tags', 'updated_at').distinct().order_by('-updated_at')

    initial_tab = request.GET.get('tab') or 'overview'
    return render(request, 'projects_detail.html', {
        'project': project,
        'paper': paper,
        'paper_form': PaperForm(instance=paper),
        'experiments': experiments,
        'citations': citations,
        'hypotheses': hypotheses,
        'notes': notes,
        'related_literature': related_literature,
        'note_form': NoteForm(),
        'hypothesis_form': HypothesisForm(),
        'initial_tab': initial_tab,
        'csrf_token_value': get_token(request),
    })


# -----------------------
# Automation background
# -----------------------
def _start_automation_background(project_id: int):
    def run():
        job = AutomationJob.objects.create(project_id=project_id, status=AutomationJobStatus.RUNNING, started_at=timezone.now())

        def start_task(name: str) -> AutomationTask:
            return AutomationTask.objects.create(job=job, name=name, status=AutomationTaskStatus.RUNNING, started_at=timezone.now())

        def complete_task(task: AutomationTask, status: str, message: str = "", result: dict | None = None):
            task.status = status
            task.message = message
            task.result_json = result
            task.progress = 100
            task.finished_at = timezone.now()
            task.save(update_fields=['status', 'message', 'result_json', 'progress', 'finished_at', 'updated_at'])

        try:
            # 1) Initial research
            t1 = start_task('initial_research')
            try:
                from agents_sdk.initial_research_agents.manager import InitialResearchServiceManager
                out1 = InitialResearchServiceManager().run_for_project_sync(project_id)
                complete_task(t1, AutomationTaskStatus.SUCCESS, result=out1.dict())
            except Exception as e:
                complete_task(t1, AutomationTaskStatus.FAILED, message=str(e))
                job.status = AutomationJobStatus.FAILED
                job.finished_at = timezone.now()
                job.save(update_fields=['status', 'finished_at', 'updated_at'])
                return

            # 2) Initial draft (only if paper empty)
            t2 = start_task('initial_draft')
            try:
                paper = Paper.objects.filter(project_id=project_id).first()
                if paper and (paper.content_raw or '').strip():
                    complete_task(t2, AutomationTaskStatus.CANCELLED, message='Skipped: paper already has content')
                else:
                    from agents_sdk.paper_draft_agents.manager import PaperDraftServiceManager
                    out2 = PaperDraftServiceManager().run_for_project_sync(project_id)
                    complete_task(t2, AutomationTaskStatus.SUCCESS, result=out2.dict())
            except Exception as e:
                complete_task(t2, AutomationTaskStatus.FAILED, message=str(e))
                job.status = AutomationJobStatus.FAILED
                job.finished_at = timezone.now()
                job.save(update_fields=['status', 'finished_at', 'updated_at'])
                return

            # 3) Hypothesis testing
            t3 = start_task('hypothesis_testing')
            try:
                from agents_sdk.hypothesis_testing_agents.manager import HypothesisTestingServiceManager
                out3 = HypothesisTestingServiceManager().run_for_project_sync(project_id)
                complete_task(t3, AutomationTaskStatus.SUCCESS, result=out3.dict())
            except Exception as e:
                complete_task(t3, AutomationTaskStatus.FAILED, message=str(e))
                job.status = AutomationJobStatus.FAILED
                job.finished_at = timezone.now()
                job.save(update_fields=['status', 'finished_at', 'updated_at'])
                return

            # 4) Compilation
            t4 = start_task('compilation')
            try:
                from agents_sdk.compilation_agents.manager import CompilationServiceManager
                out4 = CompilationServiceManager().run_for_project_sync(project_id)
                complete_task(t4, AutomationTaskStatus.SUCCESS, result=out4.dict())
            except Exception as e:
                complete_task(t4, AutomationTaskStatus.FAILED, message=str(e))
                job.status = AutomationJobStatus.FAILED
                job.finished_at = timezone.now()
                job.save(update_fields=['status', 'finished_at', 'updated_at'])
                return

            # Done
            job.status = AutomationJobStatus.SUCCESS
            job.finished_at = timezone.now()
            job.save(update_fields=['status', 'finished_at', 'updated_at'])
        except Exception as e:
            job.status = AutomationJobStatus.FAILED
            job.message = str(e)
            job.finished_at = timezone.now()
            job.save(update_fields=['status', 'message', 'finished_at', 'updated_at'])

    try:
        from django_q.tasks import async_task
        async_task('main.tasks.run_automation_pipeline', project_id)
    except ImportError:
        # Fallback to threading if django-q not available
        threading.Thread(target=run, daemon=True).start()


@login_required
def project_automation_status(request, pk: int):
    project = get_object_or_404(Project, pk=pk, owner=request.user)
    job = project.automation_jobs.order_by('-created_at').first()
    payload = {'job': None, 'tasks': []}
    if job:
        payload['job'] = {
            'id': job.id,
            'status': job.status,
            'message': job.message,
            'started_at': job.started_at.isoformat() if job.started_at else None,
            'finished_at': job.finished_at.isoformat() if job.finished_at else None,
        }
        for t in job.tasks.order_by('created_at'):
            task_data = {
                'id': t.id,
                'name': t.name,
                'status': t.status,
                'progress': t.progress,
                'message': t.message,
                'started_at': t.started_at.isoformat() if t.started_at else None,
                'finished_at': t.finished_at.isoformat() if t.finished_at else None,
            }
            if request.GET.get('include_steps'):
                from .models import AgentStep
                steps = AgentStep.objects.filter(task=t).order_by('created_at')[:50]
                task_data['steps'] = [{
                    'id': s.pk,
                    'step_type': s.step_type,
                    'tool_name': s.tool_name,
                    'content': s.content,
                    'created_at': s.created_at.isoformat(),
                } for s in steps]
            payload['tasks'].append(task_data)
    return JsonResponse(payload)


@login_required
def projects_update_paper(request, pk: int):
    project = get_object_or_404(Project, pk=pk, owner=request.user)
    paper = get_object_or_404(Paper, project=project)
    if request.method == 'POST':
        form = PaperForm(request.POST, instance=paper)
        if form.is_valid():
            form.save()
    tab = request.GET.get('tab') or request.POST.get('tab') or 'paper'
    return redirect(f"/projects/{project.pk}/?tab={tab}")


@login_required
def projects_recompile_paper(request, pk: int):
    if request.method != 'POST':
        return redirect('projects_detail', pk=pk)
    project = get_object_or_404(Project, pk=pk, owner=request.user)
    # If user submitted edits, save them first so the compilation agent sees latest content
    try:
        paper = Paper.objects.get(project=project)
        updated_fields = []
        title = request.POST.get('title')
        if title is not None and title != paper.title:
            paper.title = title
            updated_fields.append('title')
        abstract = request.POST.get('abstract')
        if abstract is not None and abstract != paper.abstract:
            paper.abstract = abstract
            updated_fields.append('abstract')
        content_raw = request.POST.get('content_raw')
        if content_raw is not None and content_raw != paper.content_raw:
            paper.content_raw = content_raw
            updated_fields.append('content_raw')
        content_format = request.POST.get('content_format')
        if content_format and content_format != paper.content_format:
            paper.content_format = content_format
            updated_fields.append('content_format')
        if updated_fields:
            paper.save(update_fields=updated_fields + ['updated_at'])
    except Paper.DoesNotExist:
        pass
    try:
        from agents_sdk.compilation_agents.manager import CompilationServiceManager
        out = CompilationServiceManager().run_for_project_sync(project.id)
        if getattr(out, 'changed', False):
            messages.success(request, "Paper recompiled and updated.")
        else:
            messages.info(request, "Recompile completed. No changes detected.")
        return redirect(f"/projects/{project.pk}/?tab=paper")
    except Exception as exc:
        messages.error(request, f"Recompile failed: {exc}")
        return redirect(f"/projects/{project.pk}/?tab=paper")


@login_required
@require_POST
def project_chat(request, pk: int):
    """Chat endpoint: accepts JSON body {message, history?} and replies JSON {reply}.

    history is optional list of {role, content}, newest last. We always pin project_id to pk.
    """
    import json
    try:
        project = Project.objects.get(pk=pk, owner=request.user)
    except Project.DoesNotExist:
        return JsonResponse({"error": "Not found"}, status=404)

    try:
        data = json.loads(request.body.decode('utf-8')) if request.body else {}
    except Exception:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    message = (data.get('message') or '').strip()
    history = data.get('history') or []
    if not message:
        return JsonResponse({"error": "Missing message"}, status=400)

    # Build turns
    from agents_sdk.project_chat_agents import ProjectChatServiceManager, ChatTurn
    turns = [ChatTurn(role=str(item.get('role') or 'user'), content=str(item.get('content') or '')) for item in history if (item and isinstance(item, dict))]
    turns.append(ChatTurn(role='user', content=message))

    try:
        manager = ProjectChatServiceManager()
        result = manager.run_for_project_sync(project.id, turns)
        from .models import ChatMessage
        ChatMessage.objects.create(project=project, role='user', content=message)
        ChatMessage.objects.create(project=project, role='assistant', content=result.reply.text)
        return JsonResponse({
            "reply": result.reply.text,
            "project_id": result.project_id,
        })
    except Exception as exc:
        return JsonResponse({"error": str(exc)}, status=500)


@login_required
def projects_add_note(request, pk: int):
    project = get_object_or_404(Project, pk=pk, owner=request.user)
    if request.method == 'POST':
        form = NoteForm(request.POST)
        if form.is_valid():
            note = form.save(commit=False)
            note.project = project
            note.save()
    return redirect(f"/projects/{project.pk}/?tab=notes")


@login_required
def projects_add_hypothesis(request, pk: int):
    project = get_object_or_404(Project, pk=pk, owner=request.user)
    if request.method == 'POST':
        form = HypothesisForm(request.POST)
        if form.is_valid():
            hyp = form.save(commit=False)
            hyp.project = project
            # By default, tie to the project's paper if present
            try:
                hyp.paper = project.paper
            except Paper.DoesNotExist:
                pass
            hyp.save()
    return redirect(f"/projects/{project.pk}/?tab=hypotheses")


@login_required
def literature_fulltext_search(request):
    """Search within the full text of ingested literature."""
    q = request.GET.get('q', '').strip()
    project_id = request.GET.get('project')
    results = []
    if q and len(q) >= 3:
        qs = Literature.objects.filter(full_text__icontains=q)
        if project_id:
            qs = qs.filter(
                Q(citations__paper__project_id=project_id) |
                Q(hypotheses__project_id=project_id)
            ).distinct()
        for lit in qs[:20]:
            # Find matching snippet
            text = lit.full_text or ''
            idx = text.lower().find(q.lower())
            snippet = ''
            if idx >= 0:
                start = max(0, idx - 100)
                end = min(len(text), idx + len(q) + 100)
                snippet = ('...' if start > 0 else '') + text[start:end] + ('...' if end < len(text) else '')
            results.append({
                'literature': lit,
                'snippet': snippet,
            })
    return render(request, 'literature_fulltext_search.html', {'q': q, 'results': results, 'project_id': project_id})


@login_required
def global_search(request):
    q = request.GET.get('q', '').strip()
    results = {'projects': [], 'literature': [], 'hypotheses': [], 'experiments': []}
    if q:
        results['projects'] = Project.objects.filter(owner=request.user, name__icontains=q)[:10]
        results['literature'] = Literature.objects.filter(
            Q(citations__paper__project__owner=request.user) | Q(hypotheses__project__owner=request.user),
            Q(title__icontains=q) | Q(authors__icontains=q)
        ).distinct()[:10]
        results['hypotheses'] = Hypothesis.objects.filter(project__owner=request.user, title__icontains=q)[:10]
        results['experiments'] = Simulation.objects.filter(project__owner=request.user, name__icontains=q)[:10]
    total = sum(len(v) for v in results.values())
    return render(request, 'search_results.html', {'q': q, 'results': results, 'total': total})


@login_required
@require_POST
def projects_delete(request, pk: int):
    project = get_object_or_404(Project, pk=pk, owner=request.user)
    project.delete()
    messages.success(request, f'Project "{project.name}" deleted.')
    return redirect('projects_list')


@login_required
@require_POST
def projects_archive(request, pk: int):
    project = get_object_or_404(Project, pk=pk, owner=request.user)
    if project.status == ProjectStatus.ARCHIVED:
        project.status = ProjectStatus.ACTIVE
        messages.success(request, f'Project "{project.name}" restored.')
    else:
        project.status = ProjectStatus.ARCHIVED
        messages.success(request, f'Project "{project.name}" archived.')
    project.save(update_fields=['status', 'updated_at'])
    return redirect('projects_detail', pk=pk)


@login_required
def projects_export_paper(request, pk: int):
    from django.http import HttpResponse
    project = get_object_or_404(Project, pk=pk, owner=request.user)
    paper = get_object_or_404(Paper, project=project)
    content = paper.content_raw or ''
    response = HttpResponse(content, content_type='application/x-tex')
    filename = f'{project.name.replace(" ", "_")}.tex'
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@login_required
def project_chat_history(request, pk: int):
    project = get_object_or_404(Project, pk=pk, owner=request.user)
    from .models import ChatMessage
    msgs = ChatMessage.objects.filter(project=project).order_by('created_at')[:100]
    return JsonResponse({
        'messages': [{'role': m.role, 'content': m.content, 'created_at': m.created_at.isoformat()} for m in msgs]
    })


@login_required
def projects_tab_data(request, pk: int):
    """Lazy-load tab data as JSON so switching tabs doesn't require a page reload."""
    project = get_object_or_404(Project, pk=pk, owner=request.user)
    paper, _ = Paper.objects.get_or_create(project=project, defaults={'title': project.name, 'abstract': project.abstract})
    tab = request.GET.get('tab', '')

    if tab == 'literature':
        items = Literature.objects.filter(citations__paper=paper).distinct().order_by('-updated_at')
        return JsonResponse({'items': [
            {'id': l.pk, 'title': l.title, 'url': l.url, 'year': l.year, 'tags': l.tags}
            for l in items
        ]})
    elif tab == 'experiments':
        items = Simulation.objects.filter(project=project).order_by('-updated_at')[:10]
        return JsonResponse({'items': [
            {'id': s.pk, 'name': s.name, 'status': s.status, 'description': s.description or ''}
            for s in items
        ]})
    elif tab == 'hypotheses':
        items = Hypothesis.objects.filter(project=project).order_by('-updated_at')
        return JsonResponse({'items': [
            {'id': h.pk, 'title': h.title, 'statement': h.statement, 'status': h.status}
            for h in items
        ]})
    elif tab == 'notes':
        items = project.notes.all()
        return JsonResponse({'items': [
            {'id': n.pk, 'title': n.title, 'body': n.body, 'pinned': n.pinned}
            for n in items
        ]})
    return JsonResponse({'items': []})


@login_required
@require_POST
def projects_parse_sections(request, pk: int):
    """Parse paper content_raw into PaperSection records by splitting on \\section{} commands."""
    from .models import PaperSection, PaperSectionKind
    project = get_object_or_404(Project, pk=pk, owner=request.user)
    paper = get_object_or_404(Paper, project=project)

    import re
    content = paper.content_raw or ''

    # Split on \section{...}
    pattern = r'\\section\*?\{([^}]*)\}'
    parts = re.split(pattern, content)

    # parts[0] is preamble, then alternating: title, content, title, content...
    sections_data = []
    preamble = parts[0].strip()
    if preamble:
        sections_data.append(('Preamble', 'custom', preamble))

    for i in range(1, len(parts), 2):
        title = parts[i].strip()
        body = parts[i+1].strip() if i+1 < len(parts) else ''
        # Map title to kind
        kind = 'custom'
        title_lower = title.lower()
        for k in ['introduction', 'methods', 'results', 'discussion', 'conclusion', 'abstract', 'acknowledgments', 'references']:
            if k in title_lower:
                kind = k
                break
        sections_data.append((title, kind, body))

    # Delete existing sections and recreate
    PaperSection.objects.filter(paper=paper).delete()
    for idx, (title, kind, body) in enumerate(sections_data):
        PaperSection.objects.create(paper=paper, order=idx, title=title, kind=kind, content=body)

    messages.success(request, f'Parsed {len(sections_data)} sections from paper.')
    return redirect(f"/projects/{project.pk}/?tab=paper")


@login_required
@require_POST
def projects_update_section(request, pk: int, section_id: int):
    """Update a single paper section's content."""
    project = get_object_or_404(Project, pk=pk, owner=request.user)
    from .models import PaperSection
    section = get_object_or_404(PaperSection, pk=section_id, paper__project=project)

    new_content = request.POST.get('content', '')
    old_content = section.content
    section.content = new_content
    section.save(update_fields=['content', 'updated_at'])

    # Return JSON with diff info
    import difflib
    diff = list(difflib.unified_diff(
        old_content.splitlines(keepends=True),
        new_content.splitlines(keepends=True),
        fromfile='before', tofile='after', lineterm=''
    ))

    return JsonResponse({
        'status': 'ok',
        'section_id': section.pk,
        'diff_lines': len(diff),
        'diff': '\n'.join(diff[:100]),  # Truncate large diffs
    })


@login_required
def projects_sections_json(request, pk: int):
    """Return paper sections as JSON for the section editor."""
    project = get_object_or_404(Project, pk=pk, owner=request.user)
    paper = get_object_or_404(Paper, project=project)
    from .models import PaperSection
    sections = PaperSection.objects.filter(paper=paper).order_by('order')
    return JsonResponse({
        'sections': [{
            'id': s.pk,
            'order': s.order,
            'title': s.title,
            'kind': s.kind,
            'content': s.content,
        } for s in sections],
        'has_sections': sections.exists(),
    })


@login_required
@require_POST
def projects_recompile_section(request, pk: int, section_id: int):
    """Recompile a single section using the AI agent and return a diff."""
    project = get_object_or_404(Project, pk=pk, owner=request.user)
    from .models import PaperSection
    section = get_object_or_404(PaperSection, pk=section_id, paper__project=project)

    old_content = section.content
    instruction = request.POST.get('instruction', '').strip() or f'Improve and expand the {section.title} section.'

    # For now, return the existing content with a note - the actual AI recompilation
    # would call the compilation agent with section-specific context
    return JsonResponse({
        'status': 'ok',
        'section_id': section.pk,
        'old_content': old_content,
        'new_content': old_content,  # Placeholder - would be AI-generated
        'message': 'Section recompilation requires AI agent integration.',
    })


@login_required
@require_POST
def experiments_run_ajax(request, pk: int):
    """Run an experiment via AJAX. Optionally accepts updated code/params."""
    import json as json_mod
    sim = get_object_or_404(Simulation, pk=pk, project__owner=request.user)

    # Allow updating code and params before running
    if request.content_type == 'application/json':
        try:
            data = json_mod.loads(request.body)
            if 'code' in data:
                sim.code = data['code']
            if 'parameters' in data:
                sim.parameters = data['parameters']
            sim.save(update_fields=['code', 'parameters', 'updated_at'])
        except Exception:
            pass

    sim.run(timeout_seconds=int(request.POST.get('timeout', 60)))

    # Save to run history
    from .models import SimulationRun
    SimulationRun.objects.create(
        simulation=sim,
        parameters=sim.parameters,
        status=sim.status,
        started_at=sim.started_at,
        finished_at=sim.finished_at,
        exit_code=sim.exit_code,
        stdout=sim.stdout,
        stderr=sim.stderr,
        result_json=sim.result_json,
    )

    return JsonResponse({
        'status': sim.status,
        'exit_code': sim.exit_code,
        'stdout': sim.stdout,
        'stderr': sim.stderr,
        'result_json': sim.result_json,
        'started_at': sim.started_at.isoformat() if sim.started_at else None,
        'finished_at': sim.finished_at.isoformat() if sim.finished_at else None,
    })


@login_required
def experiments_run_history(request, pk: int):
    """Return run history for an experiment as JSON."""
    sim = get_object_or_404(Simulation, pk=pk, project__owner=request.user)
    from .models import SimulationRun
    runs = SimulationRun.objects.filter(simulation=sim).order_by('-created_at')[:20]
    return JsonResponse({
        'runs': [{
            'id': r.pk,
            'status': r.status,
            'exit_code': r.exit_code,
            'parameters': r.parameters,
            'stdout': r.stdout[:500],
            'stderr': r.stderr[:500],
            'result_json': r.result_json,
            'started_at': r.started_at.isoformat() if r.started_at else None,
            'finished_at': r.finished_at.isoformat() if r.finished_at else None,
            'created_at': r.created_at.isoformat(),
        } for r in runs]
    })


@login_required
def experiments_templates(request):
    """Return experiment templates as JSON."""
    from .experiment_templates import EXPERIMENT_TEMPLATES
    return JsonResponse({'templates': EXPERIMENT_TEMPLATES})


@login_required
@require_POST
def experiments_create_ajax(request, project_pk: int):
    """Create an experiment from within a project page via AJAX."""
    import json as json_mod
    project = get_object_or_404(Project, pk=project_pk, owner=request.user)
    try:
        data = json_mod.loads(request.body)
    except Exception:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    name = data.get('name', '').strip() or 'Untitled Experiment'
    code = data.get('code', '')
    parameters = data.get('parameters')
    description = data.get('description', '')

    sim = Simulation.objects.create(
        project=project,
        name=name,
        code=code,
        parameters=parameters,
        description=description,
    )
    return JsonResponse({
        'id': sim.pk,
        'name': sim.name,
        'url': reverse('experiments_detail', kwargs={'pk': sim.pk}),
    }, status=201)


@login_required
@require_POST
def experiments_duplicate(request, pk: int):
    """Duplicate an experiment."""
    sim = get_object_or_404(Simulation, pk=pk, project__owner=request.user)
    new_sim = Simulation.objects.create(
        project=sim.project,
        name=f"{sim.name} (copy)",
        description=sim.description,
        code=sim.code,
        language=sim.language,
        parameters=sim.parameters,
    )
    return redirect('experiments_detail', pk=new_sim.pk)


@login_required
@require_POST
def projects_rerun_stage(request, pk: int):
    """Re-run a specific automation stage for a project."""
    project = get_object_or_404(Project, pk=pk, owner=request.user)
    stage = request.POST.get('stage', '')

    valid_stages = ['initial_research', 'initial_draft', 'hypothesis_testing', 'compilation']
    if stage not in valid_stages:
        return JsonResponse({'error': f'Invalid stage. Must be one of: {valid_stages}'}, status=400)

    # Create a new job for just this stage
    job = AutomationJob.objects.create(
        project=project,
        status=AutomationJobStatus.RUNNING,
        started_at=timezone.now(),
        message=f'Re-running: {stage}'
    )
    task = AutomationTask.objects.create(
        job=job,
        name=stage,
        status=AutomationTaskStatus.RUNNING,
        started_at=timezone.now()
    )

    def run_stage():
        try:
            if stage == 'initial_research':
                from agents_sdk.initial_research_agents.manager import InitialResearchServiceManager
                out = InitialResearchServiceManager().run_for_project_sync(project.id)
                result = out.dict()
            elif stage == 'initial_draft':
                from agents_sdk.paper_draft_agents.manager import PaperDraftServiceManager
                out = PaperDraftServiceManager().run_for_project_sync(project.id)
                result = out.dict()
            elif stage == 'hypothesis_testing':
                from agents_sdk.hypothesis_testing_agents.manager import HypothesisTestingServiceManager
                out = HypothesisTestingServiceManager().run_for_project_sync(project.id)
                result = out.dict()
            elif stage == 'compilation':
                from agents_sdk.compilation_agents.manager import CompilationServiceManager
                out = CompilationServiceManager().run_for_project_sync(project.id)
                result = out.dict()

            task.status = AutomationTaskStatus.SUCCESS
            task.result_json = result
            task.progress = 100
            task.finished_at = timezone.now()
            task.save(update_fields=['status', 'result_json', 'progress', 'finished_at', 'updated_at'])
            job.status = AutomationJobStatus.SUCCESS
            job.finished_at = timezone.now()
            job.save(update_fields=['status', 'finished_at', 'updated_at'])
        except Exception as e:
            task.status = AutomationTaskStatus.FAILED
            task.message = str(e)
            task.finished_at = timezone.now()
            task.save(update_fields=['status', 'message', 'finished_at', 'updated_at'])
            job.status = AutomationJobStatus.FAILED
            job.message = str(e)
            job.finished_at = timezone.now()
            job.save(update_fields=['status', 'message', 'finished_at', 'updated_at'])

    import threading
    threading.Thread(target=run_stage, daemon=True).start()

    return JsonResponse({
        'status': 'started',
        'job_id': job.pk,
        'stage': stage,
    })


@login_required
@require_POST
def projects_rerun_full(request, pk: int):
    """Re-run the entire automation pipeline for a project."""
    project = get_object_or_404(Project, pk=pk, owner=request.user)
    _start_automation_background(project.pk)
    messages.success(request, 'Full research pipeline restarted.')
    return redirect(f"/projects/{project.pk}/?tab=automation")
