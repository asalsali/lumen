from rest_framework import serializers
from .models import (
    Project, Paper, Literature, Citation, Hypothesis, Note,
    Simulation, AutomationJob, AutomationTask, ChatMessage,
    ProjectMember, ProjectTemplate, AgentStep,
)


class AgentStepSerializer(serializers.ModelSerializer):
    class Meta:
        model = AgentStep
        fields = ['id', 'task', 'step_type', 'tool_name', 'content', 'created_at']


class AutomationTaskSerializer(serializers.ModelSerializer):
    steps = AgentStepSerializer(many=True, read_only=True)

    class Meta:
        model = AutomationTask
        fields = [
            'id', 'job', 'name', 'status', 'progress', 'message',
            'result_json', 'started_at', 'finished_at', 'steps',
        ]


class AutomationJobSerializer(serializers.ModelSerializer):
    tasks = AutomationTaskSerializer(many=True, read_only=True)

    class Meta:
        model = AutomationJob
        fields = [
            'id', 'project', 'status', 'message',
            'started_at', 'finished_at', 'tasks',
        ]


class PaperSerializer(serializers.ModelSerializer):
    class Meta:
        model = Paper
        fields = [
            'id', 'project', 'title', 'abstract', 'content_raw',
            'content_format', 'metadata', 'created_at', 'updated_at',
        ]


class ProjectSerializer(serializers.ModelSerializer):
    paper_title = serializers.SerializerMethodField()
    hypothesis_count = serializers.SerializerMethodField()
    experiment_count = serializers.SerializerMethodField()
    citation_count = serializers.SerializerMethodField()

    class Meta:
        model = Project
        fields = [
            'id', 'owner', 'name', 'abstract', 'description', 'status',
            'created_at', 'updated_at', 'paper_title',
            'hypothesis_count', 'experiment_count', 'citation_count',
        ]
        read_only_fields = ['owner', 'created_at', 'updated_at']

    def get_paper_title(self, obj):
        try:
            return obj.paper.title
        except Paper.DoesNotExist:
            return None

    def get_hypothesis_count(self, obj):
        return obj.hypotheses.count()

    def get_experiment_count(self, obj):
        return obj.simulations.count()

    def get_citation_count(self, obj):
        try:
            return obj.paper.citations.count()
        except Paper.DoesNotExist:
            return 0


class LiteratureSerializer(serializers.ModelSerializer):
    class Meta:
        model = Literature
        fields = [
            'id', 'title', 'authors', 'journal_or_publisher', 'year',
            'published_date', 'doi', 'arxiv_id', 'url', 'source_type',
            'abstract', 'tags', 'is_open_access', 'created_at', 'updated_at',
        ]


class CitationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Citation
        fields = [
            'id', 'paper', 'literature', 'section', 'locator',
            'quote', 'note', 'style', 'order', 'created_at', 'updated_at',
        ]


class HypothesisSerializer(serializers.ModelSerializer):
    class Meta:
        model = Hypothesis
        fields = [
            'id', 'project', 'paper', 'title', 'statement', 'status',
            'confidence', 'p_value', 'evaluation_summary',
            'created_at', 'updated_at',
        ]


class NoteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Note
        fields = [
            'id', 'project', 'title', 'body', 'pinned',
            'created_at', 'updated_at',
        ]


class SimulationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Simulation
        fields = [
            'id', 'project', 'paper', 'hypothesis', 'name', 'description',
            'code', 'language', 'parameters', 'status', 'started_at',
            'finished_at', 'exit_code', 'stdout', 'stderr', 'result_json',
            'created_at', 'updated_at',
        ]


class ChatMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ChatMessage
        fields = ['id', 'project', 'role', 'content', 'created_at']


class ProjectMemberSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProjectMember
        fields = ['id', 'project', 'user', 'role', 'invited_at']


class ProjectTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProjectTemplate
        fields = [
            'id', 'name', 'description', 'abstract_template', 'tags',
            'is_public', 'created_by', 'created_at',
        ]
