import os
from django.core.management.base import BaseCommand
from allauth.socialaccount.models import SocialApp
from django.contrib.sites.models import Site

class Command(BaseCommand):
    help = "Adds Google OAuth Social Application if it doesn't exist"

    def handle(self, *args, **kwargs):
        client_id = os.getenv("GOOGLE_CLIENT_ID")
        secret = os.getenv("GOOGLE_CLIENT_ID")

        if not client_id or not secret:
            self.stderr.write(self.style.ERROR("Google OAuth credentials are missing from .env"))
            return

        site, _ = Site.objects.get_or_create(domain="nine0northassignment.onrender.com", name="90North")

        # Check if the app already exists
        social_app, created = SocialApp.objects.get_or_create(
            provider="google",
            defaults={"name": "Google OAuth", "client_id": client_id, "secret": secret}
        )

        # Ensure the app is linked to the site
        social_app.sites.add(site)

        if created:
            self.stdout.write(self.style.SUCCESS("Google Social Application added successfully!"))
        else:
            self.stdout.write(self.style.WARNING("Google Social Application already exists!"))
