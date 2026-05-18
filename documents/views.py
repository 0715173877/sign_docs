import os
import io
import json
import random
import string
from datetime import datetime

from django.utils import timezone

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.conf import settings
from django.core.mail import send_mail, EmailMessage
from django.http import HttpResponse, JsonResponse, FileResponse
from django.views.decorators.http import require_POST
from django.template.loader import render_to_string
import mimetypes

import fitz  # PyMuPDF
from PIL import Image, ImageDraw, ImageFont

from .models import Document, Placement, OTP
from .forms import DocumentUploadForm, OTPForm
from .hashid_utils import encode_id
from accounts.models import UserProfile


def generate_preview(pdf_path, output_path, page_num=0):
    """Generate a PNG preview of a specific page of a PDF."""
    doc = fitz.open(pdf_path)
    page = doc[page_num]
    # Render at 150 DPI for good quality
    mat = fitz.Matrix(150 / 72, 150 / 72)
    pix = page.get_pixmap(matrix=mat)
    pix.save(output_path)
    doc.close()


def generate_all_previews(document):
    """Generate preview images for all pages of a document."""
    pdf_path = document.pdf_file.path
    doc = fitz.open(pdf_path)
    document.total_pages = len(doc)
    doc.close()

    preview_dir = os.path.join(settings.MEDIA_ROOT, "previews", str(document.id))
    os.makedirs(preview_dir, exist_ok=True)

    for page_num in range(document.total_pages):
        preview_filename = f"page_{page_num}.png"
        preview_path = os.path.join(preview_dir, preview_filename)
        generate_preview(document.pdf_file.path, preview_path, page_num)

    document.save()
    return document.total_pages


def add_date_to_stamp(stamp_path, output_path):
    """Overlay the current date centered on the stamp image using Pillow."""
    img = Image.open(stamp_path)
    # Ensure image is in RGBA mode for transparency support
    if img.mode != "RGBA":
        img = img.convert("RGBA")

    # Make white/near-white background transparent
    # This ensures the stamp blends nicely onto the PDF page
    pixels = img.load()
    for y in range(img.height):
        for x in range(img.width):
            r, g, b, a = pixels[x, y]
            if r > 200 and g > 200 and b > 200:
                pixels[x, y] = (r, g, b, 0)

    draw = ImageDraw.Draw(img)

    # Get today's date
    today = datetime.now().strftime("%d %b %Y")

    # Use a smaller font size for a subtle centered look
    font_size = max(int(img.height * 0.08), 12)
    try:
        font = ImageFont.truetype(
            os.path.join(settings.BASE_DIR, "static", "fonts", "Helvetica.ttc"),
            font_size,
        )
    except (IOError, OSError):
        try:
            font = ImageFont.truetype(
                os.path.join(settings.BASE_DIR, "static", "fonts", "DejaVuSans-Bold.ttf"),
                font_size,
            )
        except (IOError, OSError):
            font = ImageFont.load_default()

    # Get text bounding box
    bbox = draw.textbbox((0, 0), today, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]

    # Position at center of stamp (both horizontally and vertically)
    x = (img.width - text_w) // 2
    y = (img.height - text_h) // 2

    # Draw a semi-transparent white background for readability
    padding = 4
    draw.rectangle(
        [x - padding, y - padding, x + text_w + padding, y + text_h + padding],
        fill=(255, 255, 255, 220),
    )

    # Draw the date text in dark red to match stamp color
    draw.text((x, y), today, fill=(180, 0, 0, 255), font=font)

    img.save(output_path, "PNG")


def generate_signed_pdf(document):
    """
    Image-based approach: render each PDF page to an image, composite
    signature/stamp onto the image at exact pixel coordinates, then
    replace the PDF page with the composited image.

    This eliminates coordinate system conversion issues between
    preview pixels and PDF points.
    """
    pdf_path = document.pdf_file.path
    profile = UserProfile.objects.filter(user=document.user).first()
    if not profile:
        raise ValueError("User profile not found. Please upload a signature and stamp first.")

    # Validate that image files exist on disk
    if profile.signature and not os.path.exists(profile.signature.path):
        raise FileNotFoundError(f"Signature file not found: {profile.signature.path}")
    if profile.stamp and not os.path.exists(profile.stamp.path):
        raise FileNotFoundError(f"Stamp file not found: {profile.stamp.path}")

    # Open the PDF
    doc = fitz.open(pdf_path)

    # Group placements by page
    placements_by_page = {}
    for placement in document.placements.all():
        page_num = placement.page_number
        if page_num not in placements_by_page:
            placements_by_page[page_num] = []
        placements_by_page[page_num].append(placement)

    # Track temp files for cleanup
    temp_files = []

    # Resolution for rendering (must match the preview generation resolution)
    RENDER_DPI = 150
    render_zoom = RENDER_DPI / 72.0

    try:
        for page_num, placements in placements_by_page.items():
            # page_num is 1-indexed from the database, but fitz uses 0-indexed pages
            page_index = page_num - 1
            if page_index < 0 or page_index >= len(doc):
                continue
            page = doc[page_index]
            page_rect = page.rect

            # Render the page to an image at the same resolution as the preview
            mat = fitz.Matrix(render_zoom, render_zoom)
            pix = page.get_pixmap(matrix=mat)
            rendered_img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

            # The rendered image dimensions define our pixel coordinate space.
            # Placement x,y are in this same pixel space (since the preview
            # used for clicking is rendered at the same DPI).
            img_width, img_height = rendered_img.size

            # Composite all placements for this page onto the rendered image
            for placement in placements:
                # placement.x and placement.y are in preview pixel coordinates
                # (top-left origin). The rendered image is at the same resolution,
                # so we use them directly.
                cx = placement.x  # center x in pixels
                cy = placement.y  # center y in pixels

                if placement.placement_type == 'signature' and profile.signature:
                    sig_path = profile.signature.path
                    sig_img = Image.open(sig_path).convert("RGBA")

                    # Calculate signature size relative to page width
                    sig_width_px = int(img_width * 0.2)
                    sig_height_px = int(sig_width_px * (sig_img.height / sig_img.width))
                    sig_img_resized = sig_img.resize((sig_width_px, sig_height_px), Image.LANCZOS)

                    # Calculate top-left corner (centered on click point)
                    paste_x = int(cx - sig_width_px / 2)
                    paste_y = int(cy - sig_height_px / 2)

                    # Paste onto rendered image (use alpha channel for transparency)
                    rendered_img.paste(sig_img_resized, (paste_x, paste_y), sig_img_resized)

                elif placement.placement_type == 'stamp' and profile.stamp:
                    # Create temp file for dated stamp
                    dated_stamp_path = os.path.join(
                        settings.MEDIA_ROOT,
                        "temp",
                        f"dated_stamp_{document.id}_p{page_num}.png",
                    )
                    os.makedirs(os.path.dirname(dated_stamp_path), exist_ok=True)
                    add_date_to_stamp(profile.stamp.path, dated_stamp_path)
                    temp_files.append(dated_stamp_path)

                    stamp_img = Image.open(dated_stamp_path).convert("RGBA")

                    # Calculate stamp size relative to page width
                    stamp_width_px = int(img_width * 0.15)
                    stamp_height_px = int(stamp_width_px * (stamp_img.height / stamp_img.width))
                    stamp_img_resized = stamp_img.resize((stamp_width_px, stamp_height_px), Image.LANCZOS)

                    # Calculate top-left corner (centered on click point)
                    paste_x = int(cx - stamp_width_px / 2)
                    paste_y = int(cy - stamp_height_px / 2)

                    # Paste onto rendered image (use alpha channel for transparency)
                    rendered_img.paste(stamp_img_resized, (paste_x, paste_y), stamp_img_resized)

            # Save the composited image to a temp file
            composited_path = os.path.join(
                settings.MEDIA_ROOT,
                "temp",
                f"composited_page_{document.id}_p{page_index}.png",
            )
            os.makedirs(os.path.dirname(composited_path), exist_ok=True)
            rendered_img.save(composited_path, "PNG")
            temp_files.append(composited_path)

            # Clear the page content and insert the composited image as a full-page image
            # This replaces the original PDF page content with our composited version
            page.clean_contents()

            # Insert the composited image to cover the entire page
            page.insert_image(
                page_rect,
                filename=composited_path,
            )

        # Save the signed PDF
        signed_dir = os.path.join(settings.MEDIA_ROOT, "signed")
        os.makedirs(signed_dir, exist_ok=True)
        signed_filename = f"signed_{document.id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        signed_path = os.path.join(signed_dir, signed_filename)
        doc.save(signed_path)
        doc.close()

        # Update document record
        document.is_signed = True
        document.signed_pdf.name = f"signed/{signed_filename}"
        document.save()

        return signed_path

    except Exception as e:
        doc.close()
        raise e
    finally:
        # Clean up temp files
        for temp_file in temp_files:
            if os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                except OSError:
                    pass


def generate_otp():
    """Generate a random 6-digit OTP."""
    return "".join(random.choices(string.digits, k=6))


@login_required
def dashboard_view(request):
    """Show user's documents and upload form."""
    documents = Document.objects.filter(user=request.user).order_by("-created_at")
    form = DocumentUploadForm()

    if request.method == "POST":
        form = DocumentUploadForm(request.POST, request.FILES)
        if form.is_valid():
            document = form.save(commit=False)
            document.user = request.user
            document.save()

            # Generate previews for all pages
            generate_all_previews(document)

            messages.success(request, "Document uploaded successfully!")
            return redirect("sign_document", doc_id=document.id)

    documents_signed_count = documents.filter(is_signed=True).count()
    documents_pending_count = documents.filter(is_signed=False).count()

    return render(request, "documents/dashboard.html", {
        "documents": documents,
        "form": form,
        "documents_signed_count": documents_signed_count,
        "documents_pending_count": documents_pending_count,
    })



@login_required
def sign_document_view(request, doc_id):
    """Show the first page of the document for signing."""
    document = get_object_or_404(Document, id=doc_id, user=request.user)
    profile, _ = UserProfile.objects.get_or_create(user=request.user)

    if not profile.has_signature() or not profile.has_stamp():
        messages.warning(
            request,
            "You need to upload both a signature and a stamp before signing documents."
        )
        return redirect("profile")

    return redirect("sign_page", doc_id=document.id, page_num=1)


@login_required
def sign_page_view(request, doc_id, page_num):
    """Show a specific page for signing with HTMX."""
    document = get_object_or_404(Document, id=doc_id, user=request.user)
    profile, _ = UserProfile.objects.get_or_create(user=request.user)

    if not profile.has_signature() or not profile.has_stamp():
        messages.warning(
            request,
            "You need to upload both a signature and a stamp before signing documents."
        )
        return redirect("profile")

    if page_num < 1 or page_num > document.total_pages:
        messages.error(request, "Invalid page number.")
        return redirect("sign_page", doc_id=document.id, page_num=1)

    # Get placements for this page
    placements = document.placements.filter(page_number=page_num)

    # Check if this is an HTMX request
    is_htmx = request.headers.get('HX-Request') == 'true'

    # page_num is 1-indexed from URL, but preview files are 0-indexed
    preview_url = f"{settings.MEDIA_URL}previews/{document.id}/page_{page_num - 1}.png"

    # Check if signature and stamp have been placed on ANY page (not just current page)
    all_placements = document.placements.all()
    has_signature_anywhere = all_placements.filter(placement_type='signature').exists()
    has_stamp_anywhere = all_placements.filter(placement_type='stamp').exists()

    context = {
        "document": document,
        "profile": profile,
        "page_num": page_num,
        "total_pages": document.total_pages,
        "preview_url": preview_url,
        "placements": placements,
        "has_signature": placements.filter(placement_type='signature').exists(),
        "has_stamp": placements.filter(placement_type='stamp').exists(),
        "has_signature_anywhere": has_signature_anywhere,
        "has_stamp_anywhere": has_stamp_anywhere,
    }

    if is_htmx:
        return render(request, "documents/partials/sign_page_content.html", context)
    return render(request, "documents/sign.html", context)


@login_required
@require_POST
def place_item_view(request, doc_id):
    """HTMX endpoint to place a signature or stamp on a page."""
    document = get_object_or_404(Document, id=doc_id, user=request.user)
    profile, _ = UserProfile.objects.get_or_create(user=request.user)

    try:
        data = json.loads(request.body)
        placement_type = data.get('type')  # 'signature' or 'stamp'
        page_number = int(data.get('page', 1))
        x = float(data.get('x', 0))
        y = float(data.get('y', 0))
    except (json.JSONDecodeError, ValueError, TypeError):
        return JsonResponse({"error": "Invalid data"}, status=400)

    if placement_type not in ['signature', 'stamp']:
        return JsonResponse({"error": "Invalid type"}, status=400)

    # Remove existing placement of same type on this page
    document.placements.filter(
        placement_type=placement_type,
        page_number=page_number,
    ).delete()

    # Create new placement
    placement = Placement.objects.create(
        document=document,
        placement_type=placement_type,
        page_number=page_number,
        x=x,
        y=y,
    )

    # Get the image URL for the overlay
    if placement_type == 'signature' and profile.signature:
        img_url = profile.signature.url
    elif placement_type == 'stamp' and profile.stamp:
        img_url = profile.stamp.url
    else:
        img_url = ""

    # Render the overlay HTML
    overlay_html = render_to_string("documents/partials/placement_overlay.html", {
        "placement": placement,
        "img_url": img_url,
        "document": document,
    })

    return JsonResponse({
        "success": True,
        "placement_id": placement.id,
        "overlay_html": overlay_html,
        "type": placement_type,
    })


@login_required
@require_POST
def remove_placement_view(request, doc_id, placement_id):
    """HTMX endpoint to remove a placement."""
    document = get_object_or_404(Document, id=doc_id, user=request.user)
    placement = get_object_or_404(Placement, id=placement_id, document=document)
    placement.delete()
    # Return empty response for HTMX to swap out the element
    return HttpResponse("")


def send_otp_email(user, document, otp_code):
    """Send OTP via email."""
    if document:
        subject = "Your OTP for Document Signing"
        message = render_to_string("emails/otp_email.txt", {
            "user": user,
            "document": document,
            "otp_code": otp_code,
        })
    else:
        subject = "Your SignDocs Login Verification Code"
        message = (
            f"Hello {user.username},\n\n"
            f"Your SignDocs login verification code is: {otp_code}\n\n"
            f"This code is valid for 10 minutes. Do not share this code.\n\n"
            f"If you did not attempt to login, please ignore this email.\n\n"
            f"Best regards,\nSignDocs Team"
        )
    send_mail(
        subject,
        message,
        settings.DEFAULT_FROM_EMAIL,
        [user.email],
        fail_silently=False,
    )


def send_otp_sms(user, document, otp_code):
    """
    Send OTP via SMS.
    
    For production, integrate with an SMS provider like:
    - Africa's Talking (https://africastalking.com)
    - Twilio (https://twilio.com)
    - Vonage (https://vonage.com)
    
    For now, this logs the OTP to the console (like the email backend does in dev).
    In production, replace the print statement with an actual SMS API call.
    """
    profile = UserProfile.objects.filter(user=user).first()
    if not profile or not profile.phone_number:
        raise ValueError("No phone number configured for SMS delivery.")

    phone = profile.phone_number
    
    if document:
        doc_info = f" to sign the document \"{document.title or 'Untitled'}\""
    else:
        doc_info = " for your SignDocs login"
    
    message = (
        f"Your SignDocs OTP is: {otp_code}\n\n"
        f"Use this code{doc_info}.\n"
        f"Valid for 10 minutes. Do not share this code."
    )

    # 🔧 DEV: Log to console (like the email console backend)
    print(f"\n{'='*60}")
    print(f"SMS OTP to {phone}: {otp_code}")
    print(f"Message:\n{message}")
    print(f"{'='*60}\n")

    # TODO: In production, replace with actual SMS API call:
    # Example with Africa's Talking:
    # import africastalking
    # africastalking.initialize(username, api_key)
    # sms = africastalking.SMS
    # sms.send(message, [phone])
    #
    # Example with Twilio:
    # from twilio.rest import Client
    # client = Client(account_sid, auth_token)
    # client.messages.create(body=message, from_=twilio_phone, to=phone)


@login_required
def confirm_otp_view(request, doc_id):
    """Verify OTP and generate the final signed PDF."""
    document = get_object_or_404(Document, id=doc_id, user=request.user)

    if document.is_signed:
        messages.info(request, "This document has already been signed.")
        return redirect("dashboard")

    # Check that at least one placement exists
    if not document.placements.exists():
        messages.warning(request, "Please place your signature and stamp before confirming.")
        return redirect("sign_document", doc_id=document.id)

    # 🔧 DEV BYPASS: Add ?skip_otp=1 to the URL to skip OTP verification
    skip_otp = request.GET.get("skip_otp") == "1"

    # Initialize otp_code for template context (may be set below on GET requests)
    otp_code = None

    # Get user profile for OTP delivery
    profile = UserProfile.objects.filter(user=request.user).first()

    # Determine OTP delivery method
    # Default to email. If user has a phone number and requests SMS, use SMS.
    otp_method = request.GET.get("resend", "email")  # 'email' or 'sms'
    if otp_method not in ("email", "sms"):
        otp_method = "email"
    if otp_method == "sms" and (not profile or not profile.phone_number):
        otp_method = "email"

    # Clean up expired OTPs
    OTP.objects.filter(
        user=request.user,
        document=document,
        is_used=False,
        expires_at__lt=timezone.now(),
    ).delete()

    if request.method == "POST":
        # Clean up only expired OTPs, not the current valid one
        OTP.objects.filter(
            user=request.user,
            document=document,
            is_used=False,
            expires_at__lt=timezone.now(),
        ).delete()

        form = OTPForm(request.POST)
        if form.is_valid():
            otp_code = form.cleaned_data["otp_code"]
            # Find a valid, unused, non-expired OTP for this user and document
            otp_entry = OTP.objects.filter(
                user=request.user,
                document=document,
                code=otp_code,
                is_used=False,
                expires_at__gt=timezone.now(),
            ).last()

            if otp_entry or skip_otp:
                if otp_entry:
                    otp_entry.is_used = True
                    otp_entry.save()

                # Generate the signed PDF
                try:
                    signed_path = generate_signed_pdf(document)
                    messages.success(
                        request,
                        "Document signed successfully! You can now preview and download it."
                    )
                    return redirect("preview_signed", doc_id=document.id)
                except Exception as e:
                    messages.error(
                        request,
                        f"Error generating signed PDF: {str(e)}"
                    )
                    return redirect("dashboard")
            else:
                messages.error(request, "Invalid or expired OTP. Please try again.")
    else:
        form = OTPForm()
        # Clean up only expired unused OTPs before creating a new one
        OTP.objects.filter(
            user=request.user,
            document=document,
            is_used=False,
            expires_at__lt=timezone.now(),
        ).delete()

        # Generate and send OTP on GET request
        otp_code = generate_otp()
        OTP.objects.create(
            user=request.user,
            document=document,
            code=otp_code,
        )

        # Send OTP via the chosen method
        try:
            if otp_method == "sms" and profile and profile.phone_number:
                send_otp_sms(request.user, document, otp_code)
            else:
                send_otp_email(request.user, document, otp_code)
        except Exception as e:
            # If sending fails, still show the OTP page
            print(f"OTP sending failed: {e}")

    # Determine display info for the template
    if otp_method == "sms" and profile and profile.phone_number:
        otp_destination = profile.phone_number
        # Mask the middle digits for privacy
        if len(otp_destination) > 6:
            otp_destination = otp_destination[:3] + "****" + otp_destination[-3:]
    else:
        otp_destination = request.user.email

    return render(request, "documents/confirm_otp.html", {
        "document": document,
        "form": form,
        "skip_otp": skip_otp,
        "otp_method": otp_method,
        "otp_destination": otp_destination,
    })


@login_required
def preview_signed_view(request, doc_id):
    """Preview the signed PDF before downloading."""
    document = get_object_or_404(Document, id=doc_id, user=request.user)

    if not document.is_signed or not document.signed_pdf:
        messages.error(request, "Signed PDF not found.")
        return redirect("dashboard")

    signed_path = document.signed_pdf.path
    if not os.path.exists(signed_path):
        messages.error(request, "Signed PDF file not found on disk.")
        return redirect("dashboard")

    # Generate preview images of the signed PDF
    preview_dir = os.path.join(settings.MEDIA_ROOT, "signed_previews", str(document.id))
    os.makedirs(preview_dir, exist_ok=True)

    preview_urls = []
    doc = fitz.open(signed_path)
    for page_num in range(len(doc)):
        preview_filename = f"signed_page_{page_num}.png"
        preview_path = os.path.join(preview_dir, preview_filename)
        if not os.path.exists(preview_path):
            mat = fitz.Matrix(150 / 72, 150 / 72)
            pix = doc[page_num].get_pixmap(matrix=mat)
            pix.save(preview_path)
        preview_urls.append(f"{settings.MEDIA_URL}signed_previews/{document.id}/{preview_filename}")
    doc.close()

    return render(request, "documents/preview_signed.html", {
        "document": document,
        "preview_urls": preview_urls,
    })


@login_required
def download_signed_view(request, doc_id):
    """Download the signed PDF (requires login)."""
    document = get_object_or_404(Document, id=doc_id, user=request.user)

    if not document.is_signed or not document.signed_pdf:
        messages.error(request, "Signed PDF not found.")
        return redirect("dashboard")

    signed_path = document.signed_pdf.path
    if not os.path.exists(signed_path):
        messages.error(request, "Signed PDF file not found on disk.")
        return redirect("dashboard")

    response = FileResponse(
        open(signed_path, "rb"),
        content_type="application/pdf",
        filename=f"signed_{document.title or 'document'}.pdf",
        as_attachment=True,
    )
    return response


def public_download_view(request, token):
    """
    Public download view - no login required.
    Clients can download the signed PDF using a secret access token.
    The token is a long, random URL-safe string that is hard to guess.
    """
    document = get_object_or_404(Document, public_access_token=token, is_signed=True)

    if not document.signed_pdf:
        return HttpResponse("Signed PDF not found.", status=404)

    signed_path = document.signed_pdf.path
    if not os.path.exists(signed_path):
        return HttpResponse("Signed PDF file not found on disk.", status=404)

    response = FileResponse(
        open(signed_path, "rb"),
        content_type="application/pdf",
        filename=f"signed_{document.title or 'document'}.pdf",
        as_attachment=True,
    )
    return response


@login_required
def delete_document_view(request, doc_id):
    """Delete a document and all associated files."""
    document = get_object_or_404(Document, id=doc_id, user=request.user)
    if request.method == "POST":
        # Clean up files
        if document.pdf_file and os.path.exists(document.pdf_file.path):
            os.remove(document.pdf_file.path)
        if document.signed_pdf and os.path.exists(document.signed_pdf.path):
            os.remove(document.signed_pdf.path)

        # Clean up preview directories
        for dir_name in ["previews", "signed_previews"]:
            dir_path = os.path.join(settings.MEDIA_ROOT, dir_name, str(document.id))
            if os.path.exists(dir_path):
                import shutil
                shutil.rmtree(dir_path)

        document.delete()
        messages.success(request, "Document deleted successfully.")
    return redirect("dashboard")


@login_required
def send_signed_view(request, doc_id):
    """Send the signed document via email and/or WhatsApp."""
    document = get_object_or_404(Document, id=doc_id, user=request.user)

    if not document.is_signed or not document.signed_pdf:
        messages.error(request, "Signed PDF not found.")
        return redirect("dashboard")

    signed_path = document.signed_pdf.path
    if not os.path.exists(signed_path):
        messages.error(request, "Signed PDF file not found on disk.")
        return redirect("dashboard")

    if request.method == "POST":
        send_email = request.POST.get("send_email") == "on"
        send_whatsapp = request.POST.get("send_whatsapp") == "on"
        recipient_email = request.POST.get("recipient_email", "").strip()
        recipient_phone = request.POST.get("recipient_phone", "").strip()
        sender_name = request.user.get_full_name() or request.user.username

        if not send_email and not send_whatsapp:
            messages.warning(request, "Please select at least one method (Email or WhatsApp).")
            return redirect("send_signed", doc_id=document.id)

        success_count = 0
        wa_url = None

        # --- Send via Email ---
        if send_email:
            if not recipient_email:
                messages.error(request, "Please provide a recipient email address.")
                return redirect("send_signed", doc_id=document.id)

            try:
                # Build the public download URL for the email body
                download_url = request.build_absolute_uri(
                    f"/public/download/{document.public_access_token}/"
                )
                subject = f"Signed Document: {document.title or 'Document'}"
                body = render_to_string("emails/send_document_email.txt", {
                    "sender_name": sender_name,
                    "document": document,
                    "message": request.POST.get("email_message", ""),
                    "download_url": download_url,
                })
                email = EmailMessage(
                    subject=subject,
                    body=body,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    to=[recipient_email],
                )
                # Attach the signed PDF
                with open(signed_path, "rb") as f:
                    pdf_content = f.read()
                email.attach(
                    f"signed_{document.title or 'document'}.pdf",
                    pdf_content,
                    "application/pdf",
                )
                email.send(fail_silently=False)
                success_count += 1
                messages.success(request, f"✅ Document sent via email to {recipient_email}")
            except Exception as e:
                messages.error(request, f"Failed to send email: {str(e)}")

        # --- Send via WhatsApp ---
        if send_whatsapp:
            if not recipient_phone:
                messages.error(request, "Please provide a recipient phone number.")
                return redirect("send_signed", doc_id=document.id)

            try:
                # Build the public download URL using the secret access token
                # This URL does NOT require login - clients can download directly
                download_url = request.build_absolute_uri(
                    f"/public/download/{document.public_access_token}/"
                )
                # WhatsApp uses wa.me links with pre-filled message
                wa_message = (
                    f"Hi! Please find the signed document "
                    f"\"{document.title or 'Document'}\" attached.\n\n"
                    f"You can download it here: {download_url}\n\n"
                    f"Regards,\n{sender_name}"
                )
                from urllib.parse import quote
                wa_url = f"https://wa.me/{recipient_phone}?text={quote(wa_message)}"
                success_count += 1
                # Store WhatsApp link in session for display on the result page
                request.session["wa_url"] = wa_url
                request.session["wa_phone"] = recipient_phone
                messages.success(
                    request,
                    f"📱 WhatsApp link generated for {recipient_phone}!",
                )
            except Exception as e:
                messages.error(request, f"Failed to generate WhatsApp link: {str(e)}")

        if success_count > 0:
            return render(request, "documents/send_signed.html", {
                "document": document,
                "wa_url": wa_url,
                "sent": True,
            })

    # Check session for WhatsApp link from a previous POST
    wa_url = request.session.pop("wa_url", None)
    wa_phone = request.session.pop("wa_phone", None)

    return render(request, "documents/send_signed.html", {
        "document": document,
        "wa_url": wa_url,
        "wa_phone": wa_phone,
    })
