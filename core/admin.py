from django.contrib import admin
from .models import Tenant, DataSource, IngestionJob, EmissionRecord, ReviewStatus, AuditEntry

admin.site.register(Tenant)
admin.site.register(DataSource)
admin.site.register(IngestionJob)
admin.site.register(EmissionRecord)
admin.site.register(ReviewStatus)
admin.site.register(AuditEntry)