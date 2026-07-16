"""
Management command: encrypt_existing_oauth_tokens

Run once after applying migration 0002_security_remediations to re-encrypt
any plaintext OAuth tokens that were stored before SEC-001 was applied.

Usage:
    python manage.py encrypt_existing_oauth_tokens [--dry-run] [--batch-size N]
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from core.crypto import encrypt_value, decrypt_value


class Command(BaseCommand):
    help = "Re-encrypt existing plaintext OAuth tokens in OAuthAccount rows."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print what would be done without writing to the database.",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=500,
            help="Number of rows to process per database batch (default 500).",
        )

    def handle(self, *args, **options):
        from apps.authentication.models import OAuthAccount

        dry_run = options["dry_run"]
        batch_size = options["batch_size"]

        qs = OAuthAccount.objects.all()
        total = qs.count()
        self.stdout.write(f"Found {total} OAuthAccount rows to inspect.")

        processed = 0
        encrypted = 0

        for offset in range(0, total, batch_size):
            batch = list(qs[offset : offset + batch_size])
            to_update = []

            for account in batch:
                changed = False

                for field_name in ("access_token", "refresh_token"):
                    raw = account.__dict__.get(field_name, "")
                    if not raw:
                        continue
                    # Fernet ciphertext always starts with 'gAAAAA'; plaintext never does.
                    if not raw.startswith("gAAAAA"):
                        if not dry_run:
                            setattr(account, field_name, encrypt_value(raw))
                        changed = True

                if changed:
                    to_update.append(account)
                    encrypted += 1

            if to_update and not dry_run:
                with transaction.atomic():
                    OAuthAccount.objects.bulk_update(
                        to_update, ["access_token", "refresh_token"]
                    )

            processed += len(batch)
            self.stdout.write(f"  Processed {processed}/{total} rows…")

        label = "[DRY RUN] Would have encrypted" if dry_run else "Encrypted"
        self.stdout.write(
            self.style.SUCCESS(f"{label} {encrypted} OAuthAccount token(s).")
        )
