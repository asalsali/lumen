from django.db import models
from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType


class TimestampedModel(models.Model):
    """Abstract base with created/updated timestamps."""

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class ProjectStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    COMPLETED = "completed", "Completed"
    ARCHIVED = "archived", "Archived"


class Project(TimestampedModel):
    """Top-level container for a single research effort. One Paper per Project."""

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="projects")
    name = models.CharField(max_length=200)
    abstract = models.TextField(blank=True)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=ProjectStatus.choices, default=ProjectStatus.ACTIVE)

    def __str__(self) -> str:
        return self.name


class PaperContentFormat(models.TextChoices):
    MARKDOWN = "md", "Markdown"
    LATEX = "tex", "LaTeX"
    MIXED = "mixed", "Mixed"


class Paper(TimestampedModel):
    """The primary manuscript for a Project. One-to-one with Project."""

    project = models.OneToOneField(Project, on_delete=models.CASCADE, related_name="paper")
    title = models.CharField(max_length=255)
    abstract = models.TextField(blank=True)
    content_raw = models.TextField(blank=True)
    content_format = models.CharField(max_length=10, choices=PaperContentFormat.choices, default=PaperContentFormat.MARKDOWN)
    metadata = models.JSONField(blank=True, null=True)

    def __str__(self) -> str:
        return f"{self.title}"


class PaperSectionKind(models.TextChoices):
    ABSTRACT = "abstract", "Abstract"
    INTRODUCTION = "introduction", "Introduction"
    METHODS = "methods", "Methods"
    RESULTS = "results", "Results"
    DISCUSSION = "discussion", "Discussion"
    CONCLUSION = "conclusion", "Conclusion"
    ACKNOWLEDGMENTS = "acknowledgments", "Acknowledgments"
    REFERENCES = "references", "References"
    CUSTOM = "custom", "Custom"


class PaperSection(TimestampedModel):
    """Optional structured sections for a Paper. Keep it simple and flexible."""

    paper = models.ForeignKey(Paper, on_delete=models.CASCADE, related_name="sections")
    order = models.PositiveIntegerField(default=0)
    title = models.CharField(max_length=200)
    kind = models.CharField(max_length=32, choices=PaperSectionKind.choices, default=PaperSectionKind.CUSTOM)
    content = models.TextField(blank=True)

    class Meta:
        ordering = ["order", "id"]

    def __str__(self) -> str:
        return f"{self.paper.title} — {self.title}"


class LiteratureSourceType(models.TextChoices):
    ARXIV = "arxiv", "arXiv"
    DOI = "doi", "DOI"
    URL = "url", "URL"
    UPLOAD = "upload", "Uploaded PDF"
    BOOK = "book", "Book"


def literature_upload_path(instance: "Literature", filename: str) -> str:
    return f"literature_pdfs/{filename}"


class Literature(TimestampedModel):
    """Stored reference material (external literature/library)."""

    title = models.CharField(max_length=500)
    authors = models.CharField(max_length=1000, blank=True)
    journal_or_publisher = models.CharField(max_length=255, blank=True)
    year = models.PositiveIntegerField(blank=True, null=True)
    published_date = models.DateField(blank=True, null=True)
    doi = models.CharField(max_length=255, blank=True)
    arxiv_id = models.CharField(max_length=50, blank=True)
    url = models.URLField(blank=True)
    source_type = models.CharField(max_length=20, choices=LiteratureSourceType.choices, default=LiteratureSourceType.URL)
    pdf = models.FileField(upload_to=literature_upload_path, blank=True, null=True)
    abstract = models.TextField(blank=True)
    full_text = models.TextField(blank=True)
    tags = models.CharField(max_length=500, blank=True, help_text="Comma-separated tags")
    is_open_access = models.BooleanField(default=False)

    def __str__(self) -> str:
        return self.title


class CitationStyle(models.TextChoices):
    APA = "apa", "APA"
    MLA = "mla", "MLA"
    CHICAGO = "chicago", "Chicago"
    IEEE = "ieee", "IEEE"
    OTHER = "other", "Other"


class Citation(TimestampedModel):
    """Join table linking a Paper (optionally a specific Section) to a Literature item."""

    paper = models.ForeignKey(Paper, on_delete=models.CASCADE, related_name="citations")
    literature = models.ForeignKey(Literature, on_delete=models.CASCADE, related_name="citations")
    section = models.ForeignKey(PaperSection, on_delete=models.SET_NULL, blank=True, null=True, related_name="citations")
    locator = models.CharField(max_length=100, blank=True, help_text="Page(s) or section locator, e.g., p. 12–14")
    quote = models.TextField(blank=True)
    note = models.TextField(blank=True)
    style = models.CharField(max_length=20, choices=CitationStyle.choices, default=CitationStyle.OTHER)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "id"]
        unique_together = ("paper", "literature", "section", "order")

    def __str__(self) -> str:
        return f"Citation: {self.paper.title} -> {self.literature.title}"


class HypothesisStatus(models.TextChoices):
    PROPOSED = "proposed", "Proposed"
    SUPPORTED = "supported", "Supported"
    REJECTED = "rejected", "Rejected"
    INCONCLUSIVE = "inconclusive", "Inconclusive"


class Hypothesis(TimestampedModel):
    """A testable idea explored within a Project (optionally tied to its Paper)."""

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="hypotheses")
    paper = models.ForeignKey(Paper, on_delete=models.SET_NULL, blank=True, null=True, related_name="hypotheses")
    title = models.CharField(max_length=255)
    statement = models.TextField()
    status = models.CharField(max_length=20, choices=HypothesisStatus.choices, default=HypothesisStatus.PROPOSED)
    confidence = models.DecimalField(max_digits=4, decimal_places=3, blank=True, null=True, help_text="0.000–1.000 subjective confidence")
    p_value = models.DecimalField(max_digits=6, decimal_places=5, blank=True, null=True)
    evaluation_summary = models.TextField(blank=True)
    references = models.ManyToManyField(Literature, blank=True, related_name="hypotheses")

    def __str__(self) -> str:
        return self.title


class Note(TimestampedModel):
    """Lightweight note attached to a Project (meeting notes, ideas, todos)."""

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="notes")
    title = models.CharField(max_length=200)
    body = models.TextField(blank=True)
    pinned = models.BooleanField(default=False)

    class Meta:
        ordering = ["-pinned", "-updated_at", "-id"]

    def __str__(self) -> str:
        return self.title


class SimulationStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    PENDING = "pending", "Pending"
    RUNNING = "running", "Running"
    SUCCESS = "success", "Success"
    FAILED = "failed", "Failed"


class CodeLanguage(models.TextChoices):
    PYTHON = "python", "Python"
    R = "r", "R"
    JULIA = "julia", "Julia"


class Simulation(TimestampedModel):
    """Code-based experiment. Results stored as JSON and/or file attachments."""

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="simulations")
    paper = models.ForeignKey(Paper, on_delete=models.SET_NULL, blank=True, null=True, related_name="simulations")
    hypothesis = models.ForeignKey(Hypothesis, on_delete=models.SET_NULL, blank=True, null=True, related_name="simulations")
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    code = models.TextField(help_text="Executable code snippet for the simulation")
    language = models.CharField(max_length=20, choices=CodeLanguage.choices, default=CodeLanguage.PYTHON)
    parameters = models.JSONField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=SimulationStatus.choices, default=SimulationStatus.DRAFT)
    started_at = models.DateTimeField(blank=True, null=True)
    finished_at = models.DateTimeField(blank=True, null=True)
    exit_code = models.IntegerField(blank=True, null=True)
    stdout = models.TextField(blank=True)
    stderr = models.TextField(blank=True)
    result_json = models.JSONField(blank=True, null=True)

    def __str__(self) -> str:
        return self.name

    def run(self, timeout_seconds: int = 30):
        from .utils.experiment_utils import run_simulation
        return run_simulation(self, timeout_seconds=timeout_seconds)


class SimulationRun(TimestampedModel):
    """Individual execution of a Simulation. Tracks run history."""
    simulation = models.ForeignKey(Simulation, on_delete=models.CASCADE, related_name="runs")
    parameters = models.JSONField(blank=True, null=True, help_text="Parameters used for this specific run")
    status = models.CharField(max_length=20, choices=SimulationStatus.choices, default=SimulationStatus.PENDING)
    started_at = models.DateTimeField(blank=True, null=True)
    finished_at = models.DateTimeField(blank=True, null=True)
    exit_code = models.IntegerField(blank=True, null=True)
    stdout = models.TextField(blank=True)
    stderr = models.TextField(blank=True)
    result_json = models.JSONField(blank=True, null=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Run #{self.pk} of {self.simulation.name} ({self.status})"


def attachment_upload_path(instance: "Attachment", filename: str) -> str:
    return f"attachments/{filename}"


class AttachmentKind(models.TextChoices):
    IMAGE = "image", "Image"
    TABLE = "table", "Table"
    TEXT = "text", "Text"
    JSON = "json", "JSON"
    ARCHIVE = "archive", "Archive"
    OTHER = "other", "Other"


class Attachment(TimestampedModel):
    """Generic file/text attachment associated to any object (e.g., Simulation, Paper)."""

    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey("content_type", "object_id")

    kind = models.CharField(max_length=20, choices=AttachmentKind.choices, default=AttachmentKind.OTHER)
    label = models.CharField(max_length=200, blank=True)
    mime_type = models.CharField(max_length=100, blank=True)
    file = models.FileField(upload_to=attachment_upload_path, blank=True, null=True)
    text_content = models.TextField(blank=True)
    metadata = models.JSONField(blank=True, null=True)

    def __str__(self) -> str:
        target = self.content_object.__class__.__name__ if self.content_object else "?"
        return f"Attachment({self.kind}) -> {target}"




class AutomationJobStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    RUNNING = "running", "Running"
    SUCCESS = "success", "Success"
    FAILED = "failed", "Failed"


class AutomationTaskStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    RUNNING = "running", "Running"
    SUCCESS = "success", "Success"
    FAILED = "failed", "Failed"
    CANCELLED = "cancelled", "Cancelled"


class AutomationJob(TimestampedModel):
    """Background automation run for a Project spanning multiple agent systems."""

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="automation_jobs")
    status = models.CharField(max_length=20, choices=AutomationJobStatus.choices, default=AutomationJobStatus.PENDING)
    message = models.TextField(blank=True)
    started_at = models.DateTimeField(blank=True, null=True)
    finished_at = models.DateTimeField(blank=True, null=True)

    def __str__(self) -> str:
        return f"AutomationJob[{self.id}] -> {self.project.name} ({self.status})"


class AutomationTask(TimestampedModel):
    """Individual system task within an AutomationJob (e.g., initial_research, initial_draft)."""

    job = models.ForeignKey(AutomationJob, on_delete=models.CASCADE, related_name="tasks")
    name = models.CharField(max_length=100)
    status = models.CharField(max_length=20, choices=AutomationTaskStatus.choices, default=AutomationTaskStatus.PENDING)
    progress = models.PositiveIntegerField(default=0)
    message = models.TextField(blank=True)
    result_json = models.JSONField(blank=True, null=True)
    started_at = models.DateTimeField(blank=True, null=True)
    finished_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        indexes = [models.Index(fields=["job", "name"]) ]

    def __str__(self) -> str:
        return f"AutomationTask[{self.name}] ({self.status})"


class ChatMessage(models.Model):
    """Persisted assistant chat conversation message."""

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="chat_messages")
    role = models.CharField(max_length=20)  # "user" or "assistant"
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"ChatMessage({self.role}) in {self.project.name}"


class MemberRole(models.TextChoices):
    OWNER = "owner", "Owner"
    EDITOR = "editor", "Editor"
    VIEWER = "viewer", "Viewer"


class ProjectMember(models.Model):
    """Collaborative project membership."""

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="members")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    role = models.CharField(max_length=20, choices=MemberRole.choices, default=MemberRole.EDITOR)
    invited_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("project", "user")

    def __str__(self) -> str:
        return f"{self.user} -> {self.project.name} ({self.role})"


class ProjectTemplate(models.Model):
    """Reusable project template."""

    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    abstract_template = models.TextField(blank=True, help_text="Default abstract text")
    tags = models.CharField(max_length=500, blank=True)
    is_public = models.BooleanField(default=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return self.name


class StepType(models.TextChoices):
    TOOL_CALL = "tool_call", "Tool Call"
    TOOL_RESULT = "tool_result", "Tool Result"
    THINKING = "thinking", "Thinking"
    OUTPUT = "output", "Output"


class AgentStep(models.Model):
    """Individual step within an AutomationTask for agent visualization."""

    task = models.ForeignKey(AutomationTask, on_delete=models.CASCADE, related_name="steps")
    step_type = models.CharField(max_length=20, choices=StepType.choices)
    tool_name = models.CharField(max_length=100, blank=True)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self) -> str:
        return f"AgentStep({self.step_type}) for {self.task.name}"