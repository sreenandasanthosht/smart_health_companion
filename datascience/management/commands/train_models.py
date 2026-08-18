"""
python manage.py train_models

Runs the recommendation-engine pipeline end to end: trains the model on
whatever synthetic cohort currently exists (run `generate_cohort` first if
there isn't one), evaluates it with grouped cross-validation, and prints a
short summary table. Every artifact this writes is regenerable by running
this command again.
"""
from django.core.management.base import BaseCommand, CommandError

from datascience.evaluate import evaluate_recommender
from datascience.models import SyntheticPatient
from datascience.recommend import train_recommender


class Command(BaseCommand):
    help = 'Train and evaluate the CareNest recommendation engine on the synthetic cohort.'

    def handle(self, *args, **options):
        if not SyntheticPatient.objects.exists():
            raise CommandError('No synthetic patients found. Run `python manage.py generate_cohort` first.')

        self.stdout.write('Training recommendation engine...')
        train_recommender()

        self.stdout.write('Evaluating with grouped cross-validation...')
        results = evaluate_recommender()

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(
            f"Trained on {results['trained_on_patients']} synthetic patients."))
        self.stdout.write(f"{'Candidate':<16}{'Accuracy':>10}{'Precision':>11}{'Recall':>9}{'F1':>8}{'ROC-AUC':>10}")
        for key, m in results['candidates'].items():
            def fmt(entry):
                return f"{entry['mean']:.2f}" if entry['mean'] is not None else '  n/a'
            self.stdout.write(
                f"{key:<16}{fmt(m['accuracy']):>10}{fmt(m['precision']):>11}"
                f"{fmt(m['recall']):>9}{fmt(m['f1']):>8}{fmt(m['roc_auc']):>10}")
        self.stdout.write('')
        self.stdout.write('Full results: datascience/artifacts/metrics.json')
