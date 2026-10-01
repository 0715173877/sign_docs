from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from documents.beem_sms import send_sms


class Command(BaseCommand):
    help = (
        "Send a test SMS to verify that the SMS (OTP) gateway is correctly "
        "configured. Prints the exact provider response so delivery problems "
        "can be diagnosed."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "phone_number",
            help="Recipient phone number, e.g. 0715173877 or +255715173877",
        )
        parser.add_argument(
            "--message",
            default="SignDocs test SMS. If you received this, SMS delivery is working.",
            help="Text of the message to send",
        )

    def handle(self, *args, **options):
        phone = options["phone_number"]
        message = options["message"]

        self.stdout.write("SMS provider : Beem")
        self.stdout.write(f"API URL      : {settings.BEEM_API_URL}")
        self.stdout.write(f"Sender name  : {settings.BEEM_SENDER_NAME}")
        self.stdout.write(f"API key      : {settings.BEEM_API_KEY or '(not set)'}")
        self.stdout.write(f"Recipient    : {phone}")
        self.stdout.write("")

        if not settings.BEEM_API_KEY or not settings.BEEM_SECRET_KEY:
            raise CommandError(
                "Beem credentials are not configured. "
                "Set BEEM_API_KEY and BEEM_SECRET_KEY in your .env file."
            )

        try:
            result = send_sms(phone, message)
        except Exception as exc:
            self.stderr.write(self.style.ERROR(f"✗ SMS sending failed: {exc}"))
            self.stderr.write(
                "  Common causes: invalid/expired API credentials (HTTP 401 "
                "\"Invalid Authentication Parameters\"), sender name not "
                "approved, or no account balance."
            )
            raise CommandError("SMS was not sent. See error above.")

        self.stdout.write(
            self.style.SUCCESS(f"✓ SMS sent successfully. Provider response: {result}")
        )
