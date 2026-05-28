from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.utils import timezone
from .models import (Tenant, DataSource, IngestionJob,
                     EmissionRecord, ReviewStatus, AuditEntry)
from .parsers.sap_parser import parse_sap_csv
from .parsers.utility_parser import parse_utility_csv
from .parsers.travel_parser import parse_travel_csv
import traceback


def create_records_bulk(records_data):
    objs = [EmissionRecord(**r) for r in records_data]
    created = EmissionRecord.objects.bulk_create(objs)
    # Create pending review for each
    ReviewStatus.objects.bulk_create([
        ReviewStatus(record=r, status='pending') for r in created
    ])
    return created


class IngestView(APIView):
    def post(self, request, source_type):
        tenant_slug = request.data.get('tenant_slug', 'default')
        tenant, _ = Tenant.objects.get_or_create(
            slug=tenant_slug,
            defaults={'name': tenant_slug.title()}
        )

        datasource, _ = DataSource.objects.get_or_create(
            tenant=tenant, source_type=source_type,
            defaults={'label': f'{source_type} — {tenant.name}'}
        )

        file_obj = request.FILES.get('file')
        if not file_obj:
            return Response({'error': 'No file uploaded'}, status=400)

        job = IngestionJob.objects.create(
            datasource=datasource,
            status='processing',
            filename=file_obj.name,
        )

        try:
            if source_type == 'sap_flat_file':
                records, errors = parse_sap_csv(file_obj, tenant, job)
            elif source_type == 'utility_csv':
                region = request.data.get('grid_region', 'default')
                records, errors = parse_utility_csv(file_obj, tenant, job, region)
            elif source_type == 'concur_csv':
                records, errors = parse_travel_csv(file_obj, tenant, job)
            else:
                job.status = 'failed'
                job.save()
                return Response({'error': f'Unknown source type: {source_type}'}, status=400)

            create_records_bulk(records)
            job.rows_total = len(records) + len(errors)
            job.rows_ok = len(records)
            job.rows_failed = len(errors)
            job.error_log = errors
            job.status = 'done'
            job.save()

            return Response({
                'job_id': str(job.id),
                'rows_ok': job.rows_ok,
                'rows_failed': job.rows_failed,
                'errors': errors[:10],
            }, status=201)
        except Exception as e:
            traceback.print_exc()
            print("FULL ERROR:", str(e))

            job.status = 'failed'
            job.error_log = [{'error': str(e)}]
            job.save()

            return Response({'error': str(e)}, status=500)

        
    


class RecordsView(APIView):
    def get(self, request):
        tenant_slug = request.query_params.get('tenant_slug', 'default')
        qs = EmissionRecord.objects.filter(
            tenant__slug=tenant_slug
        ).select_related('review', 'ingestion_job').order_by('-created_at')

        # Filters
        scope = request.query_params.get('scope')
        flagged = request.query_params.get('flagged')
        review_status = request.query_params.get('status')

        if scope:
            qs = qs.filter(scope=scope)
        if flagged == 'true':
            qs = qs.filter(is_flagged=True)
        if review_status:
            qs = qs.filter(review__status=review_status)

        data = []
        for r in qs[:500]:
            data.append({
                'id': str(r.id),
                'scope': r.scope,
                'category': r.category,
                'co2e_kg': r.co2e_kg,
                'activity_date': str(r.activity_date) if r.activity_date else None,
                'is_flagged': r.is_flagged,
                'flag_reason': r.flag_reason,
                'is_locked': r.is_locked,
                'review_status': r.review.status if hasattr(r, 'review') else 'pending',
                'raw_activity_value': r.raw_activity_value,
                'raw_unit': r.raw_unit,
                'normalized_value': r.normalized_value,
                'normalized_unit': r.normalized_unit,
                'emission_factor_source': r.emission_factor_source,
                'source_type': r.ingestion_job.datasource.source_type,
            })
        return Response(data)


class ReviewView(APIView):
    def post(self, request, record_id):
        try:
            record = EmissionRecord.objects.get(id=record_id)
        except EmissionRecord.DoesNotExist:
            return Response({'error': 'Record not found'}, status=404)

        if record.is_locked:
            return Response({'error': 'Record is locked'}, status=400)

        new_status = request.data.get('status')
        note = request.data.get('note', '')

        if new_status not in ('approved', 'rejected'):
            return Response({'error': 'status must be approved or rejected'}, status=400)

        review, _ = ReviewStatus.objects.get_or_create(record=record)
        old_status = review.status
        review.status = new_status
        review.note = note
        review.reviewed_at = timezone.now()
        review.save()

        # Lock on approval
        if new_status == 'approved':
            record.is_locked = True
            record.save()

        # Write audit entry
        AuditEntry.objects.create(
            record=record,
            action=f'review_{new_status}',
            before={'status': old_status},
            after={'status': new_status, 'note': note},
        )

        return Response({'status': new_status, 'locked': record.is_locked})


class StatsView(APIView):
    def get(self, request):
        tenant_slug = request.query_params.get('tenant_slug', 'default')
        qs = EmissionRecord.objects.filter(tenant__slug=tenant_slug)

        from django.db.models import Sum, Count
        stats = {
            'total_co2e_kg': qs.aggregate(t=Sum('co2e_kg'))['t'] or 0,
            'by_scope': {},
            'by_status': {},
            'flagged_count': qs.filter(is_flagged=True).count(),
            'total_records': qs.count(),
        }
        for s in ['1', '2', '3']:
            val = qs.filter(scope=s).aggregate(t=Sum('co2e_kg'))['t']
            stats['by_scope'][f'scope_{s}'] = round(val or 0, 2)
        for st in ['pending', 'approved', 'rejected']:
            stats['by_status'][st] = qs.filter(review__status=st).count()

        return Response(stats)