"""
Profile serialization utilities.

ACA-003 fix: ProfileSerializer previously lived in apps/resumes/services.py,
making the resumes app the implicit owner of a profiles-domain object. It is
moved here so that cover_letters, portfolios, templates_engine, and resumes
all import from its canonical location.
"""
from apps.profiles.models import UserProfile


class ProfileSerializer:
    """
    Converts a UserProfile ORM object (and all related sections) into a plain
    Python dictionary suitable for template rendering and AI prompt construction.

    Callers must prefetch all related managers before calling to_dict() to
    avoid N+1 queries:

        profile = UserProfile.objects.prefetch_related(
            "work_experiences", "educations", "skills",
            "projects", "certifications", "achievements", "publications",
        ).select_related("user").get(user=user)
        data = ProfileSerializer.to_dict(profile)
    """

    @staticmethod
    def to_dict(profile: UserProfile) -> dict:
        user = profile.user
        return {
            "full_name": user.full_name,
            "email": user.email,
            "headline": profile.headline,
            "professional_summary": profile.professional_summary,
            "phone": profile.phone,
            "location": profile.location,
            "website_url": profile.website_url,
            "linkedin_url": profile.linkedin_url,
            "github_url": profile.github_url,
            "twitter_url": profile.twitter_url,
            "work_experiences": [
                {
                    "company_name": w.company_name,
                    "job_title": w.job_title,
                    "employment_type": w.employment_type,
                    "location": w.location,
                    "start_date": w.start_date.strftime("%b %Y") if w.start_date else "",
                    "end_date": w.end_date.strftime("%b %Y") if w.end_date else "",
                    "is_current": w.is_current,
                    "description": w.description,
                    "achievements": w.achievements,
                    "technologies": w.technologies,
                }
                for w in profile.work_experiences.all()
            ],
            "educations": [
                {
                    "institution": e.institution,
                    "degree": e.degree,
                    "field_of_study": e.field_of_study,
                    "start_date": e.start_date.strftime("%Y") if e.start_date else "",
                    "end_date": e.end_date.strftime("%Y") if e.end_date else "",
                    "gpa": str(e.gpa) if e.gpa else None,
                    "description": e.description,
                    "achievements": e.achievements,
                }
                for e in profile.educations.all()
            ],
            "skills": [
                {
                    "name": s.name,
                    "category": s.category,
                    "proficiency_level": s.proficiency_level,
                }
                for s in profile.skills.all()
            ],
            "projects": [
                {
                    "title": p.title,
                    "description": p.description,
                    "role": p.role,
                    "technologies": p.technologies,
                    "live_url": p.live_url,
                    "repo_url": p.repo_url,
                    "highlights": p.highlights,
                }
                for p in profile.projects.all()
            ],
            "certifications": [
                {
                    "name": c.name,
                    "issuing_organization": c.issuing_organization,
                    "issue_date": c.issue_date.strftime("%b %Y") if c.issue_date else "",
                    "credential_id": c.credential_id,
                    "credential_url": c.credential_url,
                }
                for c in profile.certifications.all()
            ],
            "achievements": [
                {
                    "title": a.title,
                    "description": a.description,
                    "date": a.date.strftime("%b %Y") if a.date else "",
                    "issuer": a.issuer,
                }
                for a in profile.achievements.all()
            ],
            "publications": [
                {
                    "title": pub.title,
                    "publisher": pub.publisher,
                    "publication_date": pub.publication_date.strftime("%b %Y") if pub.publication_date else "",
                    "url": pub.url,
                    "description": pub.description,
                }
                for pub in profile.publications.all()
            ],
        }
