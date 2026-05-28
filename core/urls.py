from django.urls import path
from .views import IngestView, RecordsView, ReviewView, StatsView

urlpatterns = [
    path('ingest/<str:source_type>/', IngestView.as_view()),
    path('records/', RecordsView.as_view()),
    path('records/<str:record_id>/review/', ReviewView.as_view()),
    path('stats/', StatsView.as_view()),
]