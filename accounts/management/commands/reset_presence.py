from django.core.management.base import BaseCommand

from accounts.models import User


class Command(BaseCommand):
    help = "Server qulagandan keyin 'osilib qolgan' online statuslarni tozalaydi."

    def handle(self, *args, **options):
        count = User.objects.filter(active_connections__gt=0).update(active_connections=0)
        self.stdout.write(self.style.SUCCESS(f"{count} ta user offline qilindi."))
