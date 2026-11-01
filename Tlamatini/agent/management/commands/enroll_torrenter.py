# Tlamatini Author Banner — Created by Angela López Mendoza · @angelahack1
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from agent.agents.torrenter.client import session
from agent.agents.torrenter.contract import TorrentError
from agent.models import TorrenterProfile


class Command(BaseCommand):
    help = "Check whether a local Tlamatini user can reach the installed Jobs service."

    def add_arguments(self, parser):
        parser.add_argument("--username", required=True)

    def handle(self, *args, **options):
        user = (
            get_user_model()
            .objects.filter(username=options["username"], is_active=True)
            .first()
        )
        if not user:
            raise CommandError("Choose an existing active Tlamatini user.")
        profile, _ = TorrenterProfile.objects.get_or_create(user=user)
        try:
            session(str(profile.account))
        except TorrentError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write("Jobs is ready. Open Torrenter workspace from the signed-in account.")
