from rest_framework.routers import DefaultRouter
from . import api_views

router = DefaultRouter()
router.register(r'projects', api_views.ProjectViewSet, basename='project')
router.register(r'papers', api_views.PaperViewSet, basename='paper')
router.register(r'literature', api_views.LiteratureViewSet, basename='literature')
router.register(r'citations', api_views.CitationViewSet, basename='citation')
router.register(r'hypotheses', api_views.HypothesisViewSet, basename='hypothesis')
router.register(r'notes', api_views.NoteViewSet, basename='note')
router.register(r'simulations', api_views.SimulationViewSet, basename='simulation')
router.register(r'chat-messages', api_views.ChatMessageViewSet, basename='chatmessage')
router.register(r'templates', api_views.ProjectTemplateViewSet, basename='projecttemplate')
router.register(r'automation-jobs', api_views.AutomationJobViewSet, basename='automationjob')
router.register(r'agent-steps', api_views.AgentStepViewSet, basename='agentstep')

urlpatterns = router.urls
