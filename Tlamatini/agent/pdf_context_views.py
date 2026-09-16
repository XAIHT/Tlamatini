# Tlamatini Author Banner — Angela López Mendoza
"""Authenticated multipart preparation of a PDF selected in the browser canvas."""

import logging

from django.http import JsonResponse

from .pdf_context_jobs import cancel_request, job_status, start_job


def prepare_pdf_context_view(request):
    upload = request.FILES.get("pdf")
    if upload is None:
        return JsonResponse({"error": "Select a PDF before using it as context."}, status=400)
    image_option = request.POST.get('process_images', 'false')
    if image_option not in {'true', 'false'}:
        return JsonResponse({'error': 'Invalid image-processing option.'}, status=400)
    try:
        job = start_job(upload, request.user.pk, request.POST.get("password", ""), request.POST.get('request_id'),
                        process_images=image_option == 'true')
        return JsonResponse({"job": job}, status=202)
    except Exception:
        logging.exception("PDF canvas context preparation failed")
        return JsonResponse({"error": "Could not prepare PDF context. Check the PDF and available disk space, then try again."}, status=422)


def pdf_context_status_view(request):
    try:
        return JsonResponse(job_status(request.GET.get('job'), request.user.pk))
    except ValueError as error:
        return JsonResponse({'error': str(error)}, status=404)


def cancel_pdf_context_view(request):
    try:
        if request.POST.get('request_id'):
            return JsonResponse(cancel_request(request.POST['request_id'], request.user.pk))
        return JsonResponse(job_status(request.POST.get('job'), request.user.pk, cancel=True))
    except ValueError as error:
        return JsonResponse({'error': str(error)}, status=404)
