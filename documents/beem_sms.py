"""
Beem SMS (Tanzania) integration for sending OTP messages.

API Documentation: https://developers.beem.africa/#sms-api

Credentials:
- API Key: Configured via BEEM_API_KEY in .env
- Secret Key: Configured via BEEM_SECRET_KEY in .env
- Sender Name: Configured via BEEM_SENDER_NAME in .env (e.g., CARLKASA)
"""

import requests
from requests.auth import HTTPBasicAuth
from django.conf import settings


def send_sms(phone_number, message):
    """
    Send an SMS via Beem Africa SMS API.

    Args:
        phone_number (str): Recipient phone number (e.g., 255715173877)
        message (str): The SMS message content

    Returns:
        dict: API response data on success with keys like 'successful', 'request_id'

    Raises:
        ValueError: If API credentials are not configured
        requests.RequestException: If the API call fails
    """
    api_key = settings.BEEM_API_KEY
    secret_key = settings.BEEM_SECRET_KEY
    sender_name = settings.BEEM_SENDER_NAME
    api_url = settings.BEEM_API_URL

    if not api_key or not secret_key:
        raise ValueError(
            "Beem SMS credentials not configured. "
            "Set BEEM_API_KEY and BEEM_SECRET_KEY in your .env file."
        )

    # Clean phone number: remove + and leading 0, ensure starts with country code
    clean_number = phone_number.strip()
    if clean_number.startswith('+'):
        clean_number = clean_number[1:]
    if clean_number.startswith('0'):
        clean_number = '255' + clean_number[1:]
    if not clean_number.startswith('255') and len(clean_number) == 9:
        clean_number = '255' + clean_number

    # Beem API expects JSON payload
    payload = {
        "source_addr": sender_name,
        "schedule_time": "",
        "encoding": "0",
        "message": message,
        "recipients": [
            {
                "recipient_id": "1",
                "dest_addr": clean_number,
            }
        ],
    }

    # Beem uses HTTP Basic Auth (API Key as username, Secret Key as password)
    auth = HTTPBasicAuth(api_key, secret_key)
    headers = {
        "Content-Type": "application/json",
    }

    response = requests.post(
        api_url,
        json=payload,
        headers=headers,
        auth=auth,
        timeout=30,
    )

    if response.status_code == 200:
        result = response.json()
        # Check if the API returned success
        if result.get("successful"):
            return result
        else:
            raise requests.RequestException(
                f"SMS sending failed. API response: {response.text}"
            )
    else:
        raise requests.RequestException(
            f"SMS sending failed. Status code: {response.status_code}, "
            f"Response: {response.text}"
        )
