from django.core.management.base import BaseCommand
from main.models import Literature
from main.utils.pdf_ingestion import ingest_literature_pdf


class Command(BaseCommand):
    help = 'Download and extract text from PDFs for literature records missing full_text'

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=50, help='Max records to process')

    def handle(self, *args, **options):
        limit = options['limit']
        qs = Literature.objects.filter(full_text='').exclude(url='').order_by('-updated_at')[:limit]
        total = qs.count()
        self.stdout.write(f'Found {total} literature records without full text')

        success = 0
        for lit in qs:
            self.stdout.write(f'  Processing: {lit.title[:60]}...', ending='')
            if ingest_literature_pdf(lit.pk):
                success += 1
                self.stdout.write(' OK')
            else:
                self.stdout.write(' SKIP')

        self.stdout.write(self.style.SUCCESS(f'Done: {success}/{total} ingested'))
