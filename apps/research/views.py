"""
Views for deep research functionality.
"""
import logging

from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render, redirect
from django.utils import timezone
from django.views import View

from core.mixins import OrganizationViewMixin
from apps.companies.models import Company
from .models import ResearchProfile, ResearchJob
from .prompt_builder import build_research_prompt, build_config_snapshot

logger = logging.getLogger(__name__)


class ResearchModalView(OrganizationViewMixin, View):
    """
    HTMX view: Returns the Deep Research configuration modal.
    GET: Renders the modal with current ResearchProfile (creates one if needed).
    """

    def get(self, request, slug):
        company = get_object_or_404(
            Company.objects.filter(organization=request.organization),
            slug=slug,
        )

        profile, created = ResearchProfile.objects.get_or_create(
            company=company,
            defaults={'created_by': request.user},
        )

        if created or (not profile.ceo_name and not profile.ir_url):
            _auto_populate_profile(company, profile)

        past_jobs = ResearchJob.objects.filter(
            company=company,
            organization=request.organization,
        ).order_by('-created_at')[:5]

        context = {
            'company': company,
            'profile': profile,
            'past_jobs': past_jobs,
        }
        return render(request, 'research/partials/research_modal.html', context)


class GeneratePromptView(OrganizationViewMixin, View):
    """
    POST: Save profile updates and generate the Claude Code prompt.
    Returns the prompt display partial (with copy-to-clipboard button).
    """

    def post(self, request, slug):
        company = get_object_or_404(
            Company.objects.filter(organization=request.organization),
            slug=slug,
        )

        profile, _ = ResearchProfile.objects.get_or_create(
            company=company,
            defaults={'created_by': request.user},
        )

        profile.ir_url = request.POST.get('ir_url', '').strip()
        profile.ceo_name = request.POST.get('ceo_name', '').strip()
        profile.cfo_name = request.POST.get('cfo_name', '').strip()
        profile.other_executives = request.POST.get('other_executives', '').strip()
        profile.extra_search_terms = request.POST.get('extra_search_terms', '').strip()
        profile.updated_by = request.user
        profile.save()

        options = {
            'years': int(request.POST.get('years', 5)),
            'skip_youtube': request.POST.get('skip_youtube') == 'on',
            'skip_podcasts': request.POST.get('skip_podcasts') == 'on',
            'skip_notebooklm': request.POST.get('skip_notebooklm') == 'on',
        }

        prompt_text = build_research_prompt(company, profile, options)

        job = ResearchJob.objects.create(
            company=company,
            organization=request.organization,
            created_by=request.user,
            prompt_text=prompt_text,
            config_snapshot=build_config_snapshot(profile),
            status=ResearchJob.Status.GENERATED,
        )

        context = {
            'company': company,
            'prompt_text': prompt_text,
            'job': job,
        }
        return render(request, 'research/partials/prompt_display.html', context)


class ResearchJobListView(OrganizationViewMixin, View):
    """GET: List past research jobs for a company."""

    def get(self, request, slug):
        company = get_object_or_404(
            Company.objects.filter(organization=request.organization),
            slug=slug,
        )
        jobs = ResearchJob.objects.filter(
            company=company,
            organization=request.organization,
        ).order_by('-created_at')

        return render(request, 'research/partials/job_history.html', {
            'company': company,
            'jobs': jobs,
        })


class UpdateJobStatusView(OrganizationViewMixin, View):
    """POST: Update a research job's status and results after Claude Code run."""

    def post(self, request, slug, job_id):
        company = get_object_or_404(
            Company.objects.filter(organization=request.organization),
            slug=slug,
        )
        job = get_object_or_404(
            ResearchJob.objects.filter(company=company, organization=request.organization),
            pk=job_id,
        )

        new_status = request.POST.get('status', '')
        if new_status in dict(ResearchJob.Status.choices):
            job.status = new_status

        if new_status == ResearchJob.Status.IN_PROGRESS and not job.started_at:
            job.started_at = timezone.now()
        elif new_status == ResearchJob.Status.COMPLETED:
            job.completed_at = timezone.now()

        job.notebook_url = request.POST.get('notebook_url', job.notebook_url)
        job.files_found = int(request.POST.get('files_found', job.files_found) or 0)
        job.videos_found = int(request.POST.get('videos_found', job.videos_found) or 0)
        job.notes_text = request.POST.get('notes_text', job.notes_text)
        job.updated_by = request.user
        job.save()

        if request.htmx:
            return HttpResponse(status=204, headers={'HX-Refresh': 'true'})
        return redirect('companies:detail', slug=slug)


def _auto_populate_profile(company, profile):
    """Try to auto-populate the research profile from Yahoo Finance data."""
    try:
        ticker = company.get_primary_ticker()
        if not ticker:
            return

        import yfinance as yf
        info = yf.Ticker(ticker.symbol).info

        officers = info.get('companyOfficers', [])
        for officer in officers:
            title = officer.get('title', '').lower()
            name = officer.get('name', '')
            if 'chief executive' in title or 'ceo' in title:
                if not profile.ceo_name:
                    profile.ceo_name = name
            elif 'chief financial' in title or 'cfo' in title:
                if not profile.cfo_name:
                    profile.cfo_name = name

        website = info.get('website', company.website or '')
        if website and not profile.ir_url:
            from urllib.parse import urlparse
            parsed = urlparse(website)
            domain = parsed.netloc.replace('www.', '')
            profile.ir_url = f'https://ir.{domain}' if domain else ''

        profile.save(update_fields=['ceo_name', 'cfo_name', 'ir_url'])

    except Exception as e:
        logger.debug(f'Auto-populate failed for {company.name}: {e}')
