from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.db.models import Q

from .models import (
    Project, Paper, Literature, Citation, Hypothesis, Note,
    Simulation, AutomationJob, AutomationTask, ChatMessage,
    ProjectMember, ProjectTemplate, AgentStep,
)
from .serializers import (
    ProjectSerializer, PaperSerializer, LiteratureSerializer,
    CitationSerializer, HypothesisSerializer, NoteSerializer,
    SimulationSerializer, AutomationJobSerializer, AutomationTaskSerializer,
    ChatMessageSerializer, ProjectMemberSerializer, ProjectTemplateSerializer,
    AgentStepSerializer,
)


class ProjectViewSet(viewsets.ModelViewSet):
    serializer_class = ProjectSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Project.objects.filter(owner=self.request.user)

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)

    @action(detail=True, methods=['post'])
    def archive(self, request, pk=None):
        project = self.get_object()
        project.status = 'archived'
        project.save()
        return Response({'status': 'archived'})

    @action(detail=True, methods=['delete'], url_path='delete')
    def destroy_project(self, request, pk=None):
        project = self.get_object()
        project.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class PaperViewSet(viewsets.ModelViewSet):
    serializer_class = PaperSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Paper.objects.filter(project__owner=self.request.user)


class LiteratureViewSet(viewsets.ModelViewSet):
    serializer_class = LiteratureSerializer
    permission_classes = [IsAuthenticated]
    queryset = Literature.objects.all()


class CitationViewSet(viewsets.ModelViewSet):
    serializer_class = CitationSerializer
    permission_classes = [IsAuthenticated]
    queryset = Citation.objects.all()


class HypothesisViewSet(viewsets.ModelViewSet):
    serializer_class = HypothesisSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Hypothesis.objects.filter(project__owner=self.request.user)


class NoteViewSet(viewsets.ModelViewSet):
    serializer_class = NoteSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Note.objects.filter(project__owner=self.request.user)


class SimulationViewSet(viewsets.ModelViewSet):
    serializer_class = SimulationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Simulation.objects.filter(project__owner=self.request.user)

    @action(detail=True, methods=['post'])
    def run(self, request, pk=None):
        simulation = self.get_object()
        timeout = int(request.data.get('timeout', 30))
        simulation.run(timeout_seconds=timeout)
        simulation.refresh_from_db()
        serializer = self.get_serializer(simulation)
        return Response(serializer.data)


class ChatMessageViewSet(viewsets.ModelViewSet):
    serializer_class = ChatMessageSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = ChatMessage.objects.filter(project__owner=self.request.user)
        project_id = self.request.query_params.get('project_id')
        if project_id:
            qs = qs.filter(project_id=project_id)
        return qs


class ProjectTemplateViewSet(viewsets.ModelViewSet):
    serializer_class = ProjectTemplateSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return ProjectTemplate.objects.filter(
            Q(is_public=True) | Q(created_by=self.request.user)
        )

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)


class AutomationJobViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = AutomationJobSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return AutomationJob.objects.filter(project__owner=self.request.user)


class AgentStepViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = AgentStepSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return AgentStep.objects.filter(task__job__project__owner=self.request.user)
