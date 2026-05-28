import uuid
from django.db import models
from django.contrib.auth.models import User


class Tenant(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    slug = models.SlugField(unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class DataSource(models.Model):
    SOURCE_TYPES = [
        ('sap_flat_file', 'SAP Flat File'),
        ('utility_csv', 'Utility CSV'),
        ('concur_csv', 'Concur Travel CSV'),
    ]
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='sources')
    source_type = models.CharField(max_length=50, choices=SOURCE_TYPES)
    label = models.CharField(max_length=255)
    config = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.tenant.name} — {self.label}"


class IngestionJob(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('done', 'Done'),
        ('failed', 'Failed'),
    ]
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    datasource = models.ForeignKey(DataSource, on_delete=models.CASCADE, related_name='jobs')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    filename = models.CharField(max_length=500, blank=True)
    rows_total = models.IntegerField(default=0)
    rows_ok = models.IntegerField(default=0)
    rows_failed = models.IntegerField(default=0)
    error_log = models.JSONField(default=list, blank=True)
    ingested_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Job {self.id} — {self.status}"


class EmissionRecord(models.Model):
    SCOPE_CHOICES = [('1', 'Scope 1'), ('2', 'Scope 2'), ('3', 'Scope 3')]
    CATEGORY_CHOICES = [
        ('fuel_combustion', 'Fuel Combustion'),
        ('purchased_goods', 'Purchased Goods'),
        ('electricity', 'Electricity'),
        ('business_travel_air', 'Business Travel — Air'),
        ('business_travel_hotel', 'Business Travel — Hotel'),
        ('business_travel_ground', 'Business Travel — Ground'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='records')
    ingestion_job = models.ForeignKey(IngestionJob, on_delete=models.CASCADE, related_name='records')

    scope = models.CharField(max_length=1, choices=SCOPE_CHOICES)
    category = models.CharField(max_length=50, choices=CATEGORY_CHOICES)

    # Raw — exactly what came in, never modified
    raw_activity_value = models.CharField(max_length=100)
    raw_unit = models.CharField(max_length=50)
    raw_payload = models.JSONField(default=dict)

    # Normalized
    normalized_value = models.FloatField(null=True, blank=True)
    normalized_unit = models.CharField(max_length=20, default='kg')
    emission_factor = models.FloatField(null=True, blank=True)
    emission_factor_source = models.CharField(max_length=255, blank=True)
    co2e_kg = models.FloatField(null=True, blank=True)

    activity_date = models.DateField(null=True, blank=True)

    # Review flags
    is_flagged = models.BooleanField(default=False)
    flag_reason = models.TextField(blank=True)
    is_locked = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.category} | {self.co2e_kg} kgCO2e | {self.activity_date}"


class ReviewStatus(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    record = models.OneToOneField(EmissionRecord, on_delete=models.CASCADE, related_name='review')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    reviewed_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)
    note = models.TextField(blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)


class AuditEntry(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    record = models.ForeignKey(EmissionRecord, on_delete=models.CASCADE, related_name='audit_trail')
    actor = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)
    action = models.CharField(max_length=100)
    before = models.JSONField(default=dict)
    after = models.JSONField(default=dict)
    ts = models.DateTimeField(auto_now_add=True)