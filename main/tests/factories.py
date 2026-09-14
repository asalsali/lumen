import factory
from django.contrib.auth.models import User

from main.models import Project, Paper, Literature, Hypothesis, Simulation, Note


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User

    username = factory.Sequence(lambda n: f"user{n}")
    email = factory.LazyAttribute(lambda obj: f"{obj.username}@example.com")
    password = factory.PostGenerationMethodCall("set_password", "testpass123")


class ProjectFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Project

    owner = factory.SubFactory(UserFactory)
    name = factory.Faker("sentence")
    status = "active"


class PaperFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Paper

    project = factory.SubFactory(ProjectFactory)
    title = factory.Faker("sentence")


class LiteratureFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Literature

    title = factory.Faker("sentence")
    source_type = "url"


class HypothesisFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Hypothesis

    project = factory.SubFactory(ProjectFactory)
    title = factory.Faker("sentence")
    statement = factory.Faker("paragraph")
    status = "proposed"


class SimulationFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Simulation

    project = factory.SubFactory(ProjectFactory)
    name = factory.Faker("sentence")
    code = 'print("hello")'
    language = "python"
    status = "draft"


class NoteFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Note

    project = factory.SubFactory(ProjectFactory)
    title = factory.Faker("sentence")
