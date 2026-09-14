import pytest

from main.models import (
    Project, Paper, Hypothesis, Simulation, ChatMessage,
    HypothesisStatus, SimulationStatus,
)
from .factories import (
    UserFactory, ProjectFactory, PaperFactory, HypothesisFactory, SimulationFactory,
)


class TestProjectModel:
    def test_project_creation(self):
        project = ProjectFactory(name="My Research")
        assert project.pk is not None
        assert str(project) == "My Research"
        assert project.status == "active"
        assert project.owner is not None

    def test_paper_one_to_one(self):
        project = ProjectFactory()
        paper = PaperFactory(project=project, title="Test Paper")
        assert paper.project == project
        assert project.paper == paper
        assert str(paper) == "Test Paper"

    def test_hypothesis_statuses(self):
        project = ProjectFactory()
        for status_value, _label in HypothesisStatus.choices:
            hyp = HypothesisFactory(project=project, status=status_value)
            assert hyp.status == status_value

    def test_simulation_defaults(self):
        sim = SimulationFactory()
        assert sim.status == SimulationStatus.DRAFT

    def test_chat_message_ordering(self):
        project = ProjectFactory()
        msg1 = ChatMessage.objects.create(project=project, role="user", content="First")
        msg2 = ChatMessage.objects.create(project=project, role="assistant", content="Second")
        msg3 = ChatMessage.objects.create(project=project, role="user", content="Third")
        msgs = list(ChatMessage.objects.filter(project=project).order_by("created_at"))
        assert msgs == [msg1, msg2, msg3]
