from django import template
from ..hashid_utils import encode_id

register = template.Library()


@register.filter
def encode_id_filter(value):
    """Template filter to encode an integer ID into a hashid string."""
    try:
        return encode_id(int(value))
    except (ValueError, TypeError):
        return value
