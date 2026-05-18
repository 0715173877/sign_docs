from django.urls import path, register_converter
from . import views
from .hashid_utils import encode_id, decode_id


class HashidConverter:
    """URL path converter that uses hashids instead of raw integer IDs."""
    regex = r'[a-zA-Z0-9]{8,32}'

    def to_python(self, value):
        result = decode_id(value)
        if result is None:
            raise ValueError("Invalid hashid")
        return result

    def to_url(self, value):
        if isinstance(value, int):
            return encode_id(value)
        return value


register_converter(HashidConverter, 'hashid')

urlpatterns = [
    path("", views.dashboard_view, name="dashboard"),
    path("sign/<hashid:doc_id>/", views.sign_document_view, name="sign_document"),
    path("sign/<hashid:doc_id>/page/<int:page_num>/", views.sign_page_view, name="sign_page"),
    path("sign/<hashid:doc_id>/place/", views.place_item_view, name="place_item"),
    path("sign/<hashid:doc_id>/remove/<int:placement_id>/", views.remove_placement_view, name="remove_placement"),
    path("confirm-otp/<hashid:doc_id>/", views.confirm_otp_view, name="confirm_otp"),
    path("preview/<hashid:doc_id>/", views.preview_signed_view, name="preview_signed"),
    path("download/<hashid:doc_id>/", views.download_signed_view, name="download_signed"),
    path("delete/<hashid:doc_id>/", views.delete_document_view, name="delete_document"),
    path("send/<hashid:doc_id>/", views.send_signed_view, name="send_signed"),
    # Public download - no login required, uses secret access token
    path("public/download/<str:token>/", views.public_download_view, name="public_download"),
]
