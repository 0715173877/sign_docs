"""
Webline SMS integration for sending OTP messages.

API Documentation: https://sms.webline.co.tz/api/v3/sms/send

Credentials:
- API Token: Configured via WEBLINE_API_TOKEN in .env
- Sender ID: TAARIFA
"""

import requests
from django.conf import settings


def _get_headers():
    """Get common headers for Webline API requests."""
    api_token = settings.WEBLINE_API_TOKEN
    if not api_token:
        raise ValueError(
            "Webline SMS credentials not configured. "
            "Set WEBLINE_API_TOKEN in your .env file."
        )
    return {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json",
    }


def _clean_phone_number(phone_number):
    """
    Ensure phone number is in the correct format (no +, no leading 0).
    The number should be like 255715173877.
    """
    clean_number = phone_number.strip()
    if clean_number.startswith('+'):
        clean_number = clean_number[1:]
    if clean_number.startswith('0'):
        clean_number = '255' + clean_number[1:]
    # If it's a short number without country code (e.g., 715173877), assume 255
    if not clean_number.startswith('255') and len(clean_number) == 9:
        clean_number = '255' + clean_number
    return clean_number


def check_balance():
    """
    Check the Webline account balance.

    Returns:
        dict: Balance info with keys 'balance' (str), 'expired_on' (str or None),
              and 'has_balance' (bool), or None if the API doesn't support balance checking.

    Raises:
        ValueError: If API token is not configured
        requests.RequestException: If the API call fails
    """
    try:
        response = requests.get(
            "https://sms.webline.co.tz/api/v3/balance",
            headers=_get_headers(),
            timeout=15,
        )
        if response.status_code == 200:
            data = response.json()
            if data.get("status") == "success":
                balance_data = data.get("data", {})
                expired_on = balance_data.get("expired_on")
                balance_str = balance_data.get("remaining_balance", "0 TZS")
                # Extract numeric balance value
                try:
                    balance_value = float(balance_str.split()[0])
                except (ValueError, IndexError):
                    balance_value = 0
                return {
                    "balance": balance_str,
                    "balance_value": balance_value,
                    "expired_on": expired_on,
                    "has_balance": balance_value > 0,
                }
    except Exception:
        pass

    return None


def send_sms(phone_number, message):
    """
    Send an SMS via Webline SMS API.

    Args:
        phone_number (str): Recipient phone number (e.g., 255715173877)
        message (str): The SMS message content

    Returns:
        dict: API response data on success

    Raises:
        ValueError: If API token is not configured
        requests.RequestException: If the API call fails
    """
    api_url = settings.WEBLINE_API_URL
    sender_id = settings.WEBLINE_SENDER_ID

    clean_number = _clean_phone_number(phone_number)

    # Webline API uses query parameters
    params = {
        "recipient": clean_number,
        "sender_id": sender_id,
        "message": message,
    }

    response = requests.post(
        api_url,
        params=params,
        headers=_get_headers(),
        timeout=30,
    )

    if response.status_code == 200:
        result = response.json()
        if result.get("status") == "success":
            return result.get("data", {})
        else:
            raise requests.RequestException(
                f"SMS sending failed. API response: {response.text}"
            )
    else:
        raise requests.RequestException(
            f"SMS sending failed. Status code: {response.status_code}, "
            f"Response: {response.text}"
        )
