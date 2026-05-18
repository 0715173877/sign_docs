from hashids import Hashids
from django.conf import settings

# Use Django's SECRET_KEY as the salt for Hashids so IDs are unique per installation
_hashids = Hashids(salt=settings.SECRET_KEY, min_length=8)


def encode_id(obj_id):
    """Encode an integer ID into a hashid string."""
    return _hashids.encode(obj_id)


def decode_id(hashid):
    """Decode a hashid string back to an integer ID. Returns None if invalid."""
    decoded = _hashids.decode(hashid)
    if decoded:
        return decoded[0]
    return None
