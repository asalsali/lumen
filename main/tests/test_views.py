import pytest
from django.test import Client

from main.models import Project
from .factories import UserFactory, ProjectFactory


class TestHomeView:
    def test_home_page(self, client):
        response = client.get("/")
        assert response.status_code == 200


class TestDashboardView:
    def test_dashboard_requires_login(self, client):
        response = client.get("/dashboard/")
        assert response.status_code == 302
        assert "/login/" in response.url

    def test_dashboard_authenticated(self, client):
        user = UserFactory()
        client.force_login(user)
        response = client.get("/dashboard/")
        assert response.status_code == 200


class TestProjectsViews:
    def test_projects_list(self, client):
        user = UserFactory()
        ProjectFactory(owner=user, name="Alpha Project")
        ProjectFactory(owner=user, name="Beta Project")
        client.force_login(user)
        response = client.get("/projects/")
        assert response.status_code == 200
        content = response.content.decode()
        assert "Alpha Project" in content
        assert "Beta Project" in content

    def test_projects_create(self, client):
        user = UserFactory()
        client.force_login(user)
        response = client.post("/projects/new/", {
            "name": "New Project",
            "abstract": "Test abstract",
            "description": "Test description",
        })
        assert response.status_code == 302
        assert Project.objects.filter(owner=user, name="New Project").exists()

    def test_projects_detail_404(self, client):
        user = UserFactory()
        client.force_login(user)
        response = client.get("/projects/99999/")
        assert response.status_code == 404

    def test_project_delete(self, client):
        user = UserFactory()
        project = ProjectFactory(owner=user, name="Doomed")
        client.force_login(user)
        response = client.post(f"/projects/{project.pk}/delete/")
        assert response.status_code == 302
        assert not Project.objects.filter(pk=project.pk).exists()


class TestGlobalSearch:
    def test_global_search(self, client):
        user = UserFactory()
        ProjectFactory(owner=user, name="Quantum Entanglement Study")
        client.force_login(user)
        response = client.get("/search/?q=Quantum")
        assert response.status_code == 200
        assert "Quantum Entanglement Study" in response.content.decode()


class TestSettingsView:
    def test_settings_email_update(self, client):
        user = UserFactory()
        client.force_login(user)
        response = client.post("/settings/", {
            "action": "update_email",
            "email": "newemail@example.com",
        })
        assert response.status_code == 200
        user.refresh_from_db()
        assert user.email == "newemail@example.com"
