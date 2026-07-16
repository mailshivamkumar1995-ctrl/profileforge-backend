import re
import logging
from typing import Any

logger = logging.getLogger(__name__)

# -- Compiled regex patterns --------------------------------------------------

_RE_EMAIL = re.compile(
    r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"
)
_RE_PHONE = re.compile(
    r"(?:\+?1[\s.-]?)?(?:\(\d{3}\)|\d{3})[\s.-]?\d{3}[\s.-]?\d{4}"
)
_RE_LINKEDIN = re.compile(
    r"(?:https?://)?(?:www\.)?linkedin\.com/in/([\w-]+)", re.IGNORECASE
)
_RE_GITHUB = re.compile(
    r"(?:https?://)?(?:www\.)?github\.com/([\w-]+)", re.IGNORECASE
)
_RE_WEBSITE = re.compile(
    r"https?://(?!linkedin|github)[^\s<>\"',]+"
)
_RE_DATE_RANGE = re.compile(
    r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|"
    r"Dec(?:ember)?)\s+\d{4}"
    r"|(?:\d{4})\s*[-–—to]+\s*(?:\d{4}|[Pp]resent|[Cc]urrent|[Nn]ow)",
    re.IGNORECASE,
)
_RE_YEAR_ONLY = re.compile(r"\b(19|20)\d{2}\b")
_RE_DATE_ARTIFACT = re.compile(
    r"^(\d{4}|[Pp]resent|[Cc]urrent|[Nn]ow)$"
)

_SECTION_HEADERS = {
    "summary": re.compile(
        r"^(?:professional\s+)?(?:summary|profile|about\s+me|objective|overview|"
        r"career\s+objective|professional\s+statement)\s*$",
        re.IGNORECASE | re.MULTILINE,
    ),
    "experience": re.compile(
        r"^(?:work\s+)?(?:experience|history|employment|career\s+history|"
        r"work\s+history|professional\s+experience)\s*$",
        re.IGNORECASE | re.MULTILINE,
    ),
    "education": re.compile(
        r"^(?:education(?:al\s+background)?|academic\s+(?:background|history)|"
        r"qualifications)\s*$",
        re.IGNORECASE | re.MULTILINE,
    ),
    "skills": re.compile(
        r"^(?:technical\s+)?(?:skills?|competenc(?:ies|y)|technologies|"
        r"core\s+(?:skills?|competenc(?:ies|y))|expertise|proficiencies)\s*$",
        re.IGNORECASE | re.MULTILINE,
    ),
    "projects": re.compile(
        r"^(?:projects?|personal\s+projects?|portfolio|work\s+samples?|"
        r"side\s+projects?|open\s+source)\s*$",
        re.IGNORECASE | re.MULTILINE,
    ),
    "certifications": re.compile(
        r"^(?:certifications?|certificates?|licenses?\s+and\s+certifications?|"
        r"professional\s+certifications?|credentials?)\s*$",
        re.IGNORECASE | re.MULTILINE,
    ),
    "achievements": re.compile(
        r"^(?:achievements?|awards?|honors?|accomplishments?|recognition)\s*$",
        re.IGNORECASE | re.MULTILINE,
    ),
}


# -- Section splitter ---------------------------------------------------------

def _split_sections(text: str) -> dict[str, str]:
    lines = text.split("\n")
    sections: dict[str, list[str]] = {"_header": []}
    current = "_header"

    for line in lines:
        matched = False
        stripped = line.strip()
        if stripped:
            for section_name, pattern in _SECTION_HEADERS.items():
                if pattern.match(stripped):
                    current = section_name
                    sections.setdefault(current, [])
                    matched = True
                    break
        if not matched:
            sections.setdefault(current, [])
            sections[current].append(line)

    return {k: "\n".join(v).strip() for k, v in sections.items()}


# -- Personal info extraction -------------------------------------------------

def _extract_personal(text: str) -> tuple[dict, dict]:
    data: dict[str, Any] = {}
    confidence: dict[str, float] = {}

    email_match = _RE_EMAIL.search(text)
    if email_match:
        data["email"] = email_match.group(0)
        confidence["email"] = 0.99

    phone_match = _RE_PHONE.search(text)
    if phone_match:
        data["phone"] = phone_match.group(0).strip()
        confidence["phone"] = 0.95

    linkedin_match = _RE_LINKEDIN.search(text)
    if linkedin_match:
        data["linkedin_url"] = f"https://linkedin.com/in/{linkedin_match.group(1)}"
        confidence["linkedin_url"] = 0.97

    github_match = _RE_GITHUB.search(text)
    if github_match:
        data["github_url"] = f"https://github.com/{github_match.group(1)}"
        confidence["github_url"] = 0.97

    website_match = _RE_WEBSITE.search(text)
    if website_match:
        data["website_url"] = website_match.group(0).rstrip(".,;)")
        confidence["website_url"] = 0.85

    # Name: first non-contact, non-header line in the first 10 lines
    for line in text.split("\n")[:10]:
        line = line.strip()
        if not line:
            continue
        if _RE_EMAIL.search(line) or _RE_PHONE.search(line):
            continue
        if _RE_LINKEDIN.search(line) or _RE_GITHUB.search(line):
            continue
        if re.match(r"^https?://", line):
            continue
        if re.match(r"^(resume|curriculum vitae|cv)\s*$", line, re.IGNORECASE):
            continue
        words = line.split()
        if 1 <= len(words) <= 5 and all(
            w.replace(".", "").isalpha() or (w[0].isupper() if w else False)
            for w in words
        ):
            data["full_name"] = line
            confidence["full_name"] = 0.8
            break

    loc_match = re.search(
        r"\b([A-Z][a-z]+(?: [A-Z][a-z]+)*),\s*([A-Z]{2}|[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b",
        text,
    )
    if loc_match:
        city, region = loc_match.group(1), loc_match.group(2)
        if not re.match(r"^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)$", city):
            data["location"] = {"city": city, "country": region}
            confidence["location"] = 0.7

    return data, confidence


# -- Summary extraction -------------------------------------------------------

def _extract_summary(sections: dict[str, str]) -> tuple[str, float]:
    text = sections.get("summary", "")
    if text and len(text) >= 30:
        return text[:2000], 0.85

    header = sections.get("_header", "")
    paragraphs = [p.strip() for p in header.split("\n\n") if len(p.strip()) >= 80]
    if paragraphs:
        return paragraphs[0][:2000], 0.6

    return "", 0.0


# -- Work experience extraction -----------------------------------------------

def _parse_date_str(s: str) -> str:
    s = s.strip()
    if re.match(r"^(present|current|now)$", s, re.IGNORECASE):
        return ""

    m = re.match(
        r"(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
        r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|"
        r"Dec(?:ember)?)\s+(\d{4})",
        s, re.IGNORECASE,
    )
    if m:
        month_map = {
            "jan": "01", "feb": "02", "mar": "03", "apr": "04",
            "may": "05", "jun": "06", "jul": "07", "aug": "08",
            "sep": "09", "oct": "10", "nov": "11", "dec": "12",
        }
        month = month_map[m.group(1)[:3].lower()]
        return f"{m.group(2)}-{month}-01"

    year_match = re.match(r"(\d{4})", s)
    if year_match:
        return f"{year_match.group(1)}-01-01"

    return ""


def _clean_part(s: str) -> str:
    """Strip trailing backslashes, dashes, and whitespace from an extracted text part."""
    return s.strip().rstrip("\\-–— ").strip()


def _extract_experiences(sections: dict[str, str]) -> tuple[list[dict], dict]:
    text = sections.get("experience", "")
    if not text:
        return [], {}

    confidence: dict[str, float] = {}
    entries: list[dict] = []
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    current: dict | None = None
    # Track the last short non-date, non-bullet line as a potential company heading
    pending_company: str = ""

    for i, line in enumerate(lines):
        date_match = _RE_DATE_RANGE.search(line)
        year_match = _RE_YEAR_ONLY.search(line)
        is_bullet = line.startswith(("*", "-", "+", "•", "·", "◦"))

        if date_match or (year_match and len(line) < 50):
            if current:
                entries.append(current)

            date_str = date_match.group(0) if date_match else line
            separators = re.split(r"[\|]|[—–\-]{1,3}|\s{2,}", re.sub(_RE_DATE_RANGE, "", line))
            parts = [_clean_part(p) for p in separators if _clean_part(p)]

            company_from_line = parts[1] if len(parts) > 1 else ""
            # Reject date artifacts ("Present", "2023", etc.) as company names
            if _RE_DATE_ARTIFACT.match(company_from_line):
                company_from_line = ""

            current = {
                "job_title": parts[0] if parts else "",
                "company_name": company_from_line or pending_company,
                "is_current": bool(re.search(r"present|current|now", line, re.IGNORECASE)),
                "start_date": "",
                "end_date": "",
                "description": "",
                "achievements": [],
                "technologies": [],
                "employment_type": "full_time",
                "location": {},
            }
            date_parts = re.split(r"\s*[\-–—to]+\s*", date_str, maxsplit=1)
            if date_parts:
                current["start_date"] = _parse_date_str(date_parts[0])
                current["end_date"] = (
                    "" if current["is_current"]
                    else (_parse_date_str(date_parts[1]) if len(date_parts) > 1 else "")
                )
            pending_company = ""

        elif is_bullet:
            if current is not None:
                bullet = line.lstrip("*-+•·◦ ").strip()
                if bullet:
                    current["achievements"].append(bullet)
            pending_company = ""

        elif current is not None:
            # Non-bullet, non-date line after an entry starts — could be a heading for the NEXT entry
            if current["description"]:
                current["description"] += " " + line
            else:
                current["description"] = line
            # Short lines with no sentence punctuation may be the next company heading
            if len(line) < 80 and not line.endswith((".", "!", "?")):
                pending_company = line
            else:
                pending_company = ""

        else:
            # Before any entry — short heading-like lines are potential company names
            if not is_bullet and len(line) < 80 and not _RE_DATE_RANGE.search(line):
                pending_company = line
            else:
                pending_company = ""

    if current:
        entries.append(current)

    for idx, entry in enumerate(entries):
        confidence[f"work_experiences[{idx}].company_name"] = 0.75
        confidence[f"work_experiences[{idx}].job_title"] = 0.75
        confidence[f"work_experiences[{idx}].start_date"] = 0.8 if entry["start_date"] else 0.3

    return entries, confidence


# -- Education extraction -----------------------------------------------------

_DEGREE_KEYWORDS = re.compile(
    r"\b(Bachelor|Master|Ph\.?D|M\.?S\.?|B\.?S\.?|M\.?B\.?A\.?|"
    r"Associate|Diploma|Doctorate|B\.?Eng?\.?|M\.?Eng?\.?|LL\.?[BM]|"
    r"B\.?A\.?|M\.?A\.?)\b",
    re.IGNORECASE,
)


def _extract_educations(sections: dict[str, str]) -> tuple[list[dict], dict]:
    text = sections.get("education", "")
    if not text:
        return [], {}

    confidence: dict[str, float] = {}
    entries: list[dict] = []
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    current: dict | None = None

    for line in lines:
        degree_match = _DEGREE_KEYWORDS.search(line)
        year_match = _RE_YEAR_ONLY.search(line)

        if degree_match or (year_match and len(line) < 80):
            if current:
                entries.append(current)

            year_str = year_match.group(0) if year_match else ""
            remaining = re.sub(_RE_YEAR_ONLY, "", line).strip()
            remaining = re.sub(r"\(\s*\)", "", remaining).strip()  # remove empty ()
            remaining = re.sub(r"[-–—,]+$", "", remaining).strip()

            current = {
                "institution": "",
                "degree": degree_match.group(0) if degree_match else "",
                "field_of_study": "",
                "start_date": "",
                "end_date": f"{year_str}-05-01" if year_str else "",
                "gpa": None,
                "description": "",
                "achievements": [],
            }

            parts = re.split(r"[\|,—–]", remaining, maxsplit=2)
            parts = [p.strip() for p in parts if p.strip()]
            if parts:
                if degree_match and degree_match.group(0).lower() in parts[0].lower():
                    current["degree"] = parts[0]
                    current["institution"] = parts[1] if len(parts) > 1 else ""
                    current["field_of_study"] = parts[2] if len(parts) > 2 else ""
                else:
                    current["institution"] = parts[0]
                    current["field_of_study"] = parts[1] if len(parts) > 1 else ""

        elif current is not None:
            gpa_match = re.search(r"GPA[:\s]+(\d+\.\d+)", line, re.IGNORECASE)
            if gpa_match:
                current["gpa"] = float(gpa_match.group(1))
            elif not current["institution"] and len(line) < 100:
                current["institution"] = line
            else:
                if current["description"]:
                    current["description"] += " " + line
                else:
                    current["description"] = line

    if current:
        entries.append(current)

    for idx, entry in enumerate(entries):
        confidence[f"educations[{idx}].institution"] = 0.8
        confidence[f"educations[{idx}].degree"] = 0.85 if entry["degree"] else 0.4

    return entries, confidence


# -- Skills extraction --------------------------------------------------------

def _extract_skills(sections: dict[str, str]) -> tuple[list[dict], dict]:
    text = sections.get("skills", "")
    if not text:
        return [], {}

    confidence: dict[str, float] = {}
    skills: list[dict] = []
    seen: set[str] = set()

    raw_items = re.split(r"[,•|\n]+", text)
    for item in raw_items:
        item = item.strip().lstrip("•◦·*-· ")
        if not item or len(item) > 60 or item.isdigit():
            continue
        if re.match(r"^(technical|soft|hard|programming|framework|tool)s?\s*:?\s*$", item, re.IGNORECASE):
            continue
        key = item.lower()
        if key not in seen:
            seen.add(key)
            skills.append({
                "name": item,
                "category": "other",
                "proficiency_level": "intermediate",
            })

    confidence["skills"] = 0.85 if skills else 0.0
    return skills, confidence


# -- Projects extraction ------------------------------------------------------

def _extract_projects(sections: dict[str, str]) -> tuple[list[dict], dict]:
    text = sections.get("projects", "")
    if not text:
        return [], {}

    confidence: dict[str, float] = {}
    entries: list[dict] = []
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    current: dict | None = None

    for line in lines:
        is_bullet = line.startswith(("*", "-", "+", "•", "·", "◦"))
        if not is_bullet and len(line) < 60 and not _RE_DATE_RANGE.search(line):
            if current:
                entries.append(current)
            current = {
                "title": line,
                "description": "",
                "role": "",
                "technologies": [],
                "live_url": "",
                "repo_url": "",
                "highlights": [],
            }
            url_match = _RE_WEBSITE.search(line)
            if url_match:
                url = url_match.group(0)
                if "github.com" in url:
                    current["repo_url"] = url
                else:
                    current["live_url"] = url
        elif current is not None:
            bullet = line.lstrip("*-+•·◦ ").strip()
            if is_bullet and bullet:
                current["highlights"].append(bullet)
            else:
                tech_match = re.search(r"(?:tech(?:nologies)?|stack|built with)[:\s]+(.+)", line, re.IGNORECASE)
                if tech_match:
                    current["technologies"] = [t.strip() for t in tech_match.group(1).split(",")]
                elif current["description"]:
                    current["description"] += " " + line
                else:
                    current["description"] = line

    if current:
        entries.append(current)

    for idx in range(len(entries)):
        confidence[f"projects[{idx}].title"] = 0.8

    return entries, confidence


# -- Certifications extraction ------------------------------------------------

def _extract_certifications(sections: dict[str, str]) -> tuple[list[dict], dict]:
    text = sections.get("certifications", "")
    if not text:
        return [], {}

    confidence: dict[str, float] = {}
    entries: list[dict] = []
    lines = [l.strip() for l in text.split("\n") if l.strip()]

    for line in lines:
        line = line.lstrip("*-+•·◦ ").strip()
        if not line:
            continue
        parts = re.split(r"[—–,\|]", line, maxsplit=1)
        name = parts[0].strip()
        issuer = parts[1].strip() if len(parts) > 1 else ""
        date_match = re.search(
            r"((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\s+\d{4}|\d{4})",
            line, re.IGNORECASE,
        )
        issue_date = _parse_date_str(date_match.group(0)) if date_match else "2020-01-01"
        entries.append({
            "name": name,
            "issuing_organization": issuer,
            "issue_date": issue_date,
            "credential_id": "",
            "credential_url": "",
        })

    for idx in range(len(entries)):
        confidence[f"certifications[{idx}].name"] = 0.8

    return entries, confidence


# -- Achievements extraction --------------------------------------------------

def _extract_achievements(sections: dict[str, str]) -> tuple[list[dict], dict]:
    text = sections.get("achievements", "")
    if not text:
        return [], {}

    confidence: dict[str, float] = {}
    entries: list[dict] = []
    lines = [l.strip() for l in text.split("\n") if l.strip()]

    for line in lines:
        line = line.lstrip("*-+•·◦ ").strip()
        if not line:
            continue
        date_match = re.search(
            r"((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\s+\d{4}|\d{4})",
            line, re.IGNORECASE,
        )
        entries.append({
            "title": line[:200],
            "description": "",
            "date": _parse_date_str(date_match.group(0)) if date_match else None,
            "issuer": "",
        })

    for idx in range(len(entries)):
        confidence[f"achievements[{idx}].title"] = 0.75

    return entries, confidence


# -- Top-level extractor ------------------------------------------------------

class ProfileExtractor:
    """
    Extracts structured profile data from raw document text.
    Returns (extracted_data, confidence_scores) where scores are 0.0-1.0.
    """

    @classmethod
    def extract(cls, text: str) -> tuple[dict, dict]:
        sections = _split_sections(text)

        personal, personal_conf = _extract_personal(text)
        summary, summary_conf = _extract_summary(sections)
        experiences, exp_conf = _extract_experiences(sections)
        educations, edu_conf = _extract_educations(sections)
        skills, skill_conf = _extract_skills(sections)
        projects, proj_conf = _extract_projects(sections)
        certifications, cert_conf = _extract_certifications(sections)
        achievements, ach_conf = _extract_achievements(sections)

        extracted = {
            "personal": personal,
            "summary": summary,
            "work_experiences": experiences,
            "educations": educations,
            "skills": skills,
            "projects": projects,
            "certifications": certifications,
            "achievements": achievements,
        }

        confidence: dict[str, float] = {}
        for key, val in personal_conf.items():
            confidence[f"personal.{key}"] = val
        if summary_conf > 0:
            confidence["summary"] = summary_conf
        confidence.update(exp_conf)
        confidence.update(edu_conf)
        if skill_conf.get("skills", 0) > 0:
            confidence["skills"] = skill_conf["skills"]
        confidence.update(proj_conf)
        confidence.update(cert_conf)
        confidence.update(ach_conf)

        return extracted, confidence

    @classmethod
    def build_mapping_review(cls, extracted: dict, confidence: dict) -> dict:
        """Convert extracted data into a mapping_review dict for user review."""
        review: dict = {}

        review["personal"] = {
            field: {
                "value": val,
                "confidence": confidence.get(f"personal.{field}", 0.5),
                "approved": confidence.get(f"personal.{field}", 0.5) >= 0.9,
            }
            for field, val in (extracted.get("personal") or {}).items()
        }

        if extracted.get("summary"):
            review["summary"] = {
                "value": extracted["summary"],
                "confidence": confidence.get("summary", 0.6),
                "approved": False,
            }

        for section in ("work_experiences", "educations", "skills", "projects", "certifications", "achievements"):
            items = extracted.get(section) or []
            review[section] = [
                {
                    "value": item,
                    "confidence": max(
                        (v for k, v in confidence.items() if k.startswith(f"{section}[{i}]")),
                        default=0.6,
                    ),
                    "approved": False,
                }
                for i, item in enumerate(items)
            ]

        return review
