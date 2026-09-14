from types import SimpleNamespace
from unittest.mock import patch

from django.test import TestCase, tag
from django.contrib.auth import get_user_model

from main.models import Project, Paper, Hypothesis, HypothesisStatus


class TestAgentManagers(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="agent_user", password="pw")
        self.project = Project.objects.create(owner=self.user, name="AgentsProj", abstract="Initial objective")
        # Ensure paper exists for convenience
        Paper.objects.get_or_create(project=self.project, defaults={"title": self.project.name, "abstract": self.project.abstract})

    @tag("initial_research_manager", "agents_sdk")
    def test_initial_research_manager(self):
        from agents_sdk.initial_research_agents.manager import InitialResearchServiceManager
        from agents_sdk.initial_research_agents.agents.formalizer_agent import FormalizedAsk
        from agents_sdk.initial_research_agents.agents.literature_reviewer_agent import LiteratureReviewOutcome
        from agents_sdk.initial_research_agents.agents.literature_summarizer_agent import ProjectFocusedSummary
        from agents_sdk.initial_research_agents.agents.hypothesizer_agent import HypothesesOutput
        from main.models import Note

        with patch("agents_sdk.initial_research_agents.manager.Runner") as MockRunner:
            r = MockRunner.return_value
            r.run.side_effect = [
                SimpleNamespace(final_output=FormalizedAsk(improved_abstract="Improved abstract")),
                SimpleNamespace(final_output=LiteratureReviewOutcome(selected=[])),
                SimpleNamespace(final_output=ProjectFocusedSummary(combined_summary="Summary body")),
                SimpleNamespace(final_output=HypothesesOutput(created=[])),
            ]

            out = InitialResearchServiceManager().run_for_project_sync(self.project.id)

        self.assertEqual(out.project_id, self.project.id)
        self.assertIsInstance(out.paper_id, int)
        self.assertTrue(out.improved_abstract)
        self.assertIsNotNone(out.literature_summary_note_id)
        self.assertTrue(Note.objects.filter(project=self.project, id=out.literature_summary_note_id).exists())

    @tag("paper_draft_manager", "agents_sdk")
    def test_paper_draft_manager(self):
        from agents_sdk.paper_draft_agents.manager import PaperDraftServiceManager
        from agents_sdk.paper_draft_agents.agents.drafting_agent import DraftSections

        # Start with empty/minimal paper content
        paper = Paper.objects.get(project=self.project)
        paper.abstract = ""
        paper.content_raw = ""
        paper.save(update_fields=["abstract", "content_raw", "updated_at"])

        with patch("agents_sdk.paper_draft_agents.manager.Runner") as MockRunner:
            r = MockRunner.return_value
            r.run.return_value = SimpleNamespace(final_output=DraftSections(
                abstract="New better abstract",
                literature_review="Some literature review text."
            ))
            out = PaperDraftServiceManager().run_for_project_sync(self.project.id)

        paper.refresh_from_db()
        self.assertEqual(out.project_id, self.project.id)
        self.assertEqual(out.paper_id, paper.id)
        self.assertTrue(out.literature_review_added)
        self.assertIn("New better abstract", paper.abstract)
        self.assertIn("# Literature Review", paper.content_raw)

    @tag("compilation_manager", "agents_sdk")
    def test_compilation_manager(self):
        from agents_sdk.compilation_agents.manager import CompilationServiceManager
        from agents_sdk.compilation_agents.agents.compilation_agent import FullLatexPaper

        paper = Paper.objects.get(project=self.project)
        paper.content_raw = "Intro...\nTARGET\n...End"
        paper.save(update_fields=["content_raw", "updated_at"])

        with patch("agents_sdk.compilation_agents.manager.Runner") as MockRunner:
            r = MockRunner.return_value
            r.run.return_value = SimpleNamespace(final_output=FullLatexPaper(
                latex="\\documentclass{article}\n\\begin{document}\nREPLACED content\n\\end{document}"
            ))
            out = CompilationServiceManager().run_for_project_sync(self.project.id)

        paper.refresh_from_db()
        self.assertEqual(out.project_id, self.project.id)
        self.assertTrue(out.changed)
        self.assertIn("REPLACED", paper.content_raw)

    @tag("hypothesis_testing_manager", "agents_sdk")
    def test_hypothesis_testing_manager(self):
        from agents_sdk.hypothesis_testing_agents.manager import HypothesisTestingServiceManager
        from agents_sdk.hypothesis_testing_agents.agents.research_agent import HypothesisResearch
        from agents_sdk.hypothesis_testing_agents.agents.sim_decider_agent import SimulationDecision
        from agents_sdk.hypothesis_testing_agents.agents.answer_agent import HypothesisAnswer

        h = Hypothesis.objects.create(project=self.project, title="H1", statement="S1")

        with patch("agents_sdk.hypothesis_testing_agents.manager.Runner") as MockRunner:
            r = MockRunner.return_value
            r.run.side_effect = [
                SimpleNamespace(final_output=HypothesisResearch(background_summary="Background")),
                SimpleNamespace(final_output=SimulationDecision(needed=False, rationale="No sim needed")),
                SimpleNamespace(final_output=HypothesisAnswer(status="supported", justification="J")),
            ]
            out = HypothesisTestingServiceManager().run_for_project_sync(self.project.id)

        self.assertEqual(out.project_id, self.project.id)
        self.assertEqual(len(out.results), 1)
        h.refresh_from_db()
        self.assertEqual(h.status, HypothesisStatus.SUPPORTED)

    @tag("full_cycle", "agents_sdk")
    def test_full_cycle_sequential(self):
        # Ensure a hypothesis exists so hypothesis testing has something to process
        Hypothesis.objects.create(project=self.project, title="H full", statement="S full")

        # 1) Initial research
        from agents_sdk.initial_research_agents.manager import InitialResearchServiceManager
        from agents_sdk.initial_research_agents.agents.formalizer_agent import FormalizedAsk
        from agents_sdk.initial_research_agents.agents.literature_reviewer_agent import LiteratureReviewOutcome
        from agents_sdk.initial_research_agents.agents.literature_summarizer_agent import ProjectFocusedSummary
        from agents_sdk.initial_research_agents.agents.hypothesizer_agent import HypothesesOutput

        with patch("agents_sdk.initial_research_agents.manager.Runner") as MR:
            r = MR.return_value
            r.run.side_effect = [
                SimpleNamespace(final_output=FormalizedAsk(improved_abstract="Better A")),
                SimpleNamespace(final_output=LiteratureReviewOutcome(selected=[])),
                SimpleNamespace(final_output=ProjectFocusedSummary(combined_summary="Summary full")),
                SimpleNamespace(final_output=HypothesesOutput(created=[])),
            ]
            InitialResearchServiceManager().run_for_project_sync(self.project.id)

        # 2) Paper draft
        from agents_sdk.paper_draft_agents.manager import PaperDraftServiceManager
        from agents_sdk.paper_draft_agents.agents.drafting_agent import DraftSections
        with patch("agents_sdk.paper_draft_agents.manager.Runner") as MR2:
            r2 = MR2.return_value
            r2.run.return_value = SimpleNamespace(final_output=DraftSections(
                abstract="Draft A",
                literature_review="LR"
            ))
            PaperDraftServiceManager().run_for_project_sync(self.project.id)

        # Prepare content for compilation
        paper = Paper.objects.get(project=self.project)
        paper.content_raw = (paper.content_raw or "") + "\nTARGET"
        paper.save(update_fields=["content_raw", "updated_at"])

        # 3) Hypothesis testing
        from agents_sdk.hypothesis_testing_agents.manager import HypothesisTestingServiceManager
        from agents_sdk.hypothesis_testing_agents.agents.research_agent import HypothesisResearch
        from agents_sdk.hypothesis_testing_agents.agents.sim_decider_agent import SimulationDecision
        from agents_sdk.hypothesis_testing_agents.agents.answer_agent import HypothesisAnswer
        with patch("agents_sdk.hypothesis_testing_agents.manager.Runner") as MR3:
            r3 = MR3.return_value
            r3.run.side_effect = [
                SimpleNamespace(final_output=HypothesisResearch(background_summary="B")),
                SimpleNamespace(final_output=SimulationDecision(needed=False, rationale="No")),
                SimpleNamespace(final_output=HypothesisAnswer(status="supported", justification="J")),
            ]
            HypothesisTestingServiceManager().run_for_project_sync(self.project.id)

        # 4) Compilation
        from agents_sdk.compilation_agents.manager import CompilationServiceManager
        from agents_sdk.compilation_agents.agents.compilation_agent import FullLatexPaper
        with patch("agents_sdk.compilation_agents.manager.Runner") as MR4:
            r4 = MR4.return_value
            r4.run.return_value = SimpleNamespace(final_output=FullLatexPaper(
                latex="\\documentclass{article}\n\\begin{document}\nREPLACED content\n\\end{document}"
            ))
            CompilationServiceManager().run_for_project_sync(self.project.id)

        # Assertions after full cycle
        paper.refresh_from_db()
        self.assertIn("REPLACED", paper.content_raw)
        from main.models import Note
        self.assertTrue(Note.objects.filter(project=self.project).exists())


