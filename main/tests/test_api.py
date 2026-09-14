import pytest
from rest_framework.test import APIClient

from .factories import UserFactory, ProjectFactory, LiteratureFactory


class TestProjectsAPI:
    def test_projects_api_list(self):
        user = UserFactory()
        ProjectFactory(owner=user, name="API Project 1")
        ProjectFactory(owner=user, name="API Project 2")
        client = APIClient()
        client.force_authenticate(user=user)
        response = client.get("/api/projects/")
        assert response.status_code == 200
        names = [p["name"] for p in response.data["results"]]
        assert "API Project 1" in names
        assert "API Project 2" in names

    def test_projects_api_create(self):
        user = UserFactory()
        client = APIClient()
        client.force_authenticate(user=user)
        response = client.post("/api/projects/", {
            "name": "Created via API",
            "abstract": "Some abstract",
        })
        assert response.status_code == 201
        assert response.data["name"] == "Created via API"

    def test_literature_api_list(self):
        user = UserFactory()
        LiteratureFactory(title="Interesting Paper")
        client = APIClient()
        client.force_authenticate(user=user)
        response = client.get("/api/literature/")
        assert response.status_code == 200

    def test_unauthenticated_returns_403(self):
        client = APIClient()
        response = client.get("/api/projects/")
        assert response.status_code == 403
