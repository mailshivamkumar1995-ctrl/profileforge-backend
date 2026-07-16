"""
Unit tests for match_resources.py — skill resource descriptor catalog.

All functions are pure: no database, no network, no Django ORM.
"""
from __future__ import annotations

import pytest

from apps.career_hub.services.match_resources import (
    SKILL_RESOURCES,
    VALID_CATEGORIES,
    VALID_RESOURCE_TYPES,
    SkillResourceDescriptor,
    get_resource_for_skill,
    get_resources_for_gaps,
)
from apps.career_hub.services.match_scoring import _SOFT_SKILL_VOCAB, _TECH_VOCAB


# ─── SkillResourceDescriptor ─────────────────────────────────────────────────

class TestSkillResourceDescriptor:
    def test_instantiation_with_all_fields(self):
        d = SkillResourceDescriptor(
            display_name="Docker",
            category="devops",
            description="Container runtime.",
            resource_type="docs",
            url="https://docs.docker.com/",
        )
        assert d.display_name == "Docker"
        assert d.category == "devops"
        assert d.description == "Container runtime."
        assert d.resource_type == "docs"
        assert d.url == "https://docs.docker.com/"
        assert d.prerequisites == ()

    def test_prerequisites_defaults_to_empty_tuple(self):
        d = SkillResourceDescriptor(
            display_name="Go",
            category="programming",
            description="Systems language.",
            resource_type="docs",
            url="https://go.dev/doc/",
        )
        assert d.prerequisites == ()
        assert isinstance(d.prerequisites, tuple)

    def test_prerequisites_stored_as_tuple(self):
        d = SkillResourceDescriptor(
            display_name="Next.js",
            category="framework",
            description="React meta-framework.",
            resource_type="docs",
            url="https://nextjs.org/docs",
            prerequisites=("react", "javascript"),
        )
        assert d.prerequisites == ("react", "javascript")

    def test_is_frozen_cannot_mutate_display_name(self):
        d = SkillResourceDescriptor(
            display_name="Python",
            category="programming",
            description="General-purpose language.",
            resource_type="docs",
            url="https://docs.python.org/",
        )
        with pytest.raises((AttributeError, TypeError)):
            d.display_name = "Changed"  # type: ignore[misc]

    def test_is_hashable_due_to_frozen(self):
        d = SkillResourceDescriptor(
            display_name="Redis",
            category="database",
            description="In-memory store.",
            resource_type="docs",
            url="https://redis.io/docs/",
        )
        assert hash(d) is not None
        s = {d}
        assert len(s) == 1

    def test_equality_on_same_values(self):
        a = SkillResourceDescriptor("A", "tool", "desc", "docs", "https://x.com/")
        b = SkillResourceDescriptor("A", "tool", "desc", "docs", "https://x.com/")
        assert a == b

    def test_inequality_on_different_display_name(self):
        a = SkillResourceDescriptor("A", "tool", "desc", "docs", "https://x.com/")
        b = SkillResourceDescriptor("B", "tool", "desc", "docs", "https://x.com/")
        assert a != b


# ─── get_resource_for_skill ───────────────────────────────────────────────────

class TestGetResourceForSkill:
    def test_known_tech_token_returns_descriptor(self):
        result = get_resource_for_skill("docker")
        assert result is not None
        assert isinstance(result, SkillResourceDescriptor)

    def test_known_soft_token_returns_descriptor(self):
        result = get_resource_for_skill("leadership")
        assert result is not None
        assert isinstance(result, SkillResourceDescriptor)

    def test_unknown_token_returns_none(self):
        assert get_resource_for_skill("xyzunknown999") is None

    def test_empty_string_returns_none(self):
        assert get_resource_for_skill("") is None

    def test_case_insensitive_uppercase(self):
        assert get_resource_for_skill("DOCKER") is not None

    def test_case_insensitive_mixed(self):
        assert get_resource_for_skill("Python") is not None

    def test_python_display_name(self):
        result = get_resource_for_skill("python")
        assert result is not None
        assert result.display_name == "Python"

    def test_docker_category_is_devops(self):
        result = get_resource_for_skill("docker")
        assert result is not None
        assert result.category == "devops"

    def test_python_category_is_programming(self):
        result = get_resource_for_skill("python")
        assert result is not None
        assert result.category == "programming"

    def test_postgresql_category_is_database(self):
        result = get_resource_for_skill("postgresql")
        assert result is not None
        assert result.category == "database"

    def test_aws_category_is_cloud(self):
        result = get_resource_for_skill("aws")
        assert result is not None
        assert result.category == "cloud"

    def test_git_category_is_tool(self):
        result = get_resource_for_skill("git")
        assert result is not None
        assert result.category == "tool"

    def test_leadership_category_is_soft_skill(self):
        result = get_resource_for_skill("leadership")
        assert result is not None
        assert result.category == "soft_skill"

    def test_agile_category_is_soft_skill(self):
        result = get_resource_for_skill("agile")
        assert result is not None
        assert result.category == "soft_skill"

    def test_aws_resource_type_is_certification(self):
        result = get_resource_for_skill("aws")
        assert result is not None
        assert result.resource_type == "certification"

    def test_docker_resource_type_is_docs(self):
        result = get_resource_for_skill("docker")
        assert result is not None
        assert result.resource_type == "docs"

    def test_kubernetes_has_docker_prerequisite(self):
        result = get_resource_for_skill("kubernetes")
        assert result is not None
        assert "docker" in result.prerequisites

    def test_typescript_has_javascript_prerequisite(self):
        result = get_resource_for_skill("typescript")
        assert result is not None
        assert "javascript" in result.prerequisites

    def test_postgresql_has_sql_prerequisite(self):
        result = get_resource_for_skill("postgresql")
        assert result is not None
        assert "sql" in result.prerequisites

    def test_nextjs_has_react_prerequisite(self):
        result = get_resource_for_skill("nextjs")
        assert result is not None
        assert "react" in result.prerequisites

    def test_python_has_no_prerequisites(self):
        result = get_resource_for_skill("python")
        assert result is not None
        assert result.prerequisites == ()

    def test_url_is_nonempty_string(self):
        result = get_resource_for_skill("react")
        assert result is not None
        assert isinstance(result.url, str)
        assert len(result.url) > 0

    def test_description_is_nonempty_string(self):
        result = get_resource_for_skill("kafka")
        assert result is not None
        assert isinstance(result.description, str)
        assert len(result.description) > 0

    def test_scrum_has_agile_prerequisite(self):
        result = get_resource_for_skill("scrum")
        assert result is not None
        assert "agile" in result.prerequisites

    def test_bash_has_linux_prerequisite(self):
        result = get_resource_for_skill("bash")
        assert result is not None
        assert "linux" in result.prerequisites


# ─── get_resources_for_gaps ──────────────────────────────────────────────────

class TestGetResourcesForGaps:
    def _make_four_tier_gaps(self) -> dict[str, list[str]]:
        return {
            "critical": ["docker", "react"],
            "moderate": ["microservices"],
            "soft": ["leadership", "agile"],
            "low": ["xyz"],
        }

    def _make_three_tier_gaps(self) -> dict[str, list[str]]:
        return {
            "critical": ["docker"],
            "moderate": ["microservices"],
            "low": ["xyz"],
        }

    def test_empty_gaps_returns_empty_dict(self):
        result = get_resources_for_gaps({})
        assert result == {}

    def test_all_tiers_present_in_output(self):
        result = get_resources_for_gaps(self._make_four_tier_gaps())
        assert set(result.keys()) == {"critical", "moderate", "soft", "low"}

    def test_known_tech_token_is_enriched(self):
        result = get_resources_for_gaps({"critical": ["docker"]})
        items = result["critical"]
        assert len(items) == 1
        assert items[0]["token"] == "docker"
        assert items[0]["display_name"] == "Docker"

    def test_unknown_token_returns_bare_token_dict(self):
        result = get_resources_for_gaps({"low": ["xyz"]})
        items = result["low"]
        assert len(items) == 1
        assert items[0] == {"token": "xyz"}

    def test_enriched_item_has_token_key(self):
        result = get_resources_for_gaps({"critical": ["python"]})
        assert result["critical"][0]["token"] == "python"

    def test_enriched_item_has_display_name(self):
        result = get_resources_for_gaps({"critical": ["python"]})
        assert "display_name" in result["critical"][0]

    def test_enriched_item_has_category(self):
        result = get_resources_for_gaps({"critical": ["python"]})
        assert "category" in result["critical"][0]

    def test_enriched_item_has_description(self):
        result = get_resources_for_gaps({"critical": ["python"]})
        assert "description" in result["critical"][0]

    def test_enriched_item_has_resource_type(self):
        result = get_resources_for_gaps({"critical": ["python"]})
        assert "resource_type" in result["critical"][0]

    def test_enriched_item_has_url(self):
        result = get_resources_for_gaps({"critical": ["python"]})
        assert "url" in result["critical"][0]

    def test_enriched_item_has_prerequisites_as_list(self):
        result = get_resources_for_gaps({"critical": ["kubernetes"]})
        item = result["critical"][0]
        assert "prerequisites" in item
        assert isinstance(item["prerequisites"], list)
        assert "docker" in item["prerequisites"]

    def test_soft_tier_items_enriched(self):
        result = get_resources_for_gaps({"soft": ["leadership", "agile"]})
        items = result["soft"]
        assert all("display_name" in it for it in items)
        assert all(it["category"] == "soft_skill" for it in items)

    def test_critical_tier_items_enriched(self):
        result = get_resources_for_gaps({"critical": ["docker", "react"]})
        items = result["critical"]
        assert len(items) == 2
        assert all("display_name" in it for it in items)

    def test_order_preserved_in_output(self):
        result = get_resources_for_gaps({"critical": ["python", "docker", "react"]})
        tokens = [it["token"] for it in result["critical"]]
        assert tokens == ["python", "docker", "react"]

    def test_backward_compat_three_key_gaps(self):
        result = get_resources_for_gaps(self._make_three_tier_gaps())
        assert set(result.keys()) == {"critical", "moderate", "low"}

    def test_bare_item_has_only_token_key(self):
        result = get_resources_for_gaps({"critical": ["notarealskill"]})
        item = result["critical"][0]
        assert list(item.keys()) == ["token"]

    def test_empty_tier_produces_empty_list(self):
        result = get_resources_for_gaps({"critical": [], "moderate": ["microservices"]})
        assert result["critical"] == []

    def test_mixed_known_and_unknown_in_same_tier(self):
        result = get_resources_for_gaps({"critical": ["docker", "unknownskill999"]})
        items = result["critical"]
        assert len(items) == 2
        assert "display_name" in items[0]
        assert list(items[1].keys()) == ["token"]

    def test_prerequisites_are_plain_list_not_tuple(self):
        result = get_resources_for_gaps({"critical": ["kubernetes"]})
        prereqs = result["critical"][0]["prerequisites"]
        assert isinstance(prereqs, list)


# ─── SKILL_RESOURCES catalog integrity ───────────────────────────────────────

class TestSkillResourcesCatalog:
    def test_catalog_is_nonempty(self):
        assert len(SKILL_RESOURCES) > 0

    def test_resource_count_in_target_range(self):
        assert 90 <= len(SKILL_RESOURCES) <= 115

    def test_all_keys_are_lowercase_strings(self):
        for key in SKILL_RESOURCES:
            assert isinstance(key, str)
            assert key == key.lower(), f"Key {key!r} is not lowercase"

    def test_all_values_are_descriptors(self):
        for key, val in SKILL_RESOURCES.items():
            assert isinstance(val, SkillResourceDescriptor), f"Bad value for key {key!r}"

    def test_all_display_names_nonempty(self):
        for key, val in SKILL_RESOURCES.items():
            assert val.display_name, f"Empty display_name for {key!r}"

    def test_all_descriptions_nonempty(self):
        for key, val in SKILL_RESOURCES.items():
            assert val.description, f"Empty description for {key!r}"

    def test_all_urls_nonempty(self):
        for key, val in SKILL_RESOURCES.items():
            assert val.url, f"Empty url for {key!r}"

    def test_all_categories_are_valid(self):
        for key, val in SKILL_RESOURCES.items():
            assert val.category in VALID_CATEGORIES, (
                f"Invalid category {val.category!r} for {key!r}"
            )

    def test_all_resource_types_are_valid(self):
        for key, val in SKILL_RESOURCES.items():
            assert val.resource_type in VALID_RESOURCE_TYPES, (
                f"Invalid resource_type {val.resource_type!r} for {key!r}"
            )

    def test_all_prerequisites_are_known_tokens(self):
        catalog_keys = set(SKILL_RESOURCES.keys())
        for key, val in SKILL_RESOURCES.items():
            for prereq in val.prerequisites:
                assert prereq in catalog_keys, (
                    f"Prerequisite {prereq!r} for {key!r} not in catalog"
                )

    def test_all_tech_vocab_tokens_have_resource(self):
        missing = _TECH_VOCAB - set(SKILL_RESOURCES.keys())
        assert missing == frozenset(), f"Missing _TECH_VOCAB entries: {missing}"

    def test_soft_skill_entries_have_soft_skill_category(self):
        soft_keys = _SOFT_SKILL_VOCAB & set(SKILL_RESOURCES.keys())
        for key in soft_keys:
            assert SKILL_RESOURCES[key].category == "soft_skill", (
                f"{key!r} is in _SOFT_SKILL_VOCAB but has category "
                f"{SKILL_RESOURCES[key].category!r}"
            )

    def test_docker_in_catalog(self):
        assert "docker" in SKILL_RESOURCES

    def test_kubernetes_in_catalog(self):
        assert "kubernetes" in SKILL_RESOURCES

    def test_python_in_catalog(self):
        assert "python" in SKILL_RESOURCES

    def test_react_in_catalog(self):
        assert "react" in SKILL_RESOURCES

    def test_leadership_in_catalog(self):
        assert "leadership" in SKILL_RESOURCES

    def test_agile_in_catalog(self):
        assert "agile" in SKILL_RESOURCES

    def test_communication_in_catalog(self):
        assert "communication" in SKILL_RESOURCES

    def test_collaboration_in_catalog(self):
        assert "collaboration" in SKILL_RESOURCES

    def test_aws_resource_type_certification(self):
        assert SKILL_RESOURCES["aws"].resource_type == "certification"

    def test_azure_resource_type_certification(self):
        assert SKILL_RESOURCES["azure"].resource_type == "certification"

    def test_gcp_resource_type_certification(self):
        assert SKILL_RESOURCES["gcp"].resource_type == "certification"

    def test_cloud_providers_all_present(self):
        for provider in ("aws", "azure", "gcp"):
            assert provider in SKILL_RESOURCES

    def test_vcs_tools_all_present(self):
        for tool in ("git", "jenkins", "gitlab", "github"):
            assert tool in SKILL_RESOURCES

    def test_primary_databases_all_present(self):
        for db in ("sql", "postgresql", "mysql", "mongodb", "redis", "elasticsearch"):
            assert db in SKILL_RESOURCES

    def test_ml_libraries_all_present(self):
        for lib in ("tensorflow", "pytorch", "scikit", "pandas", "spark", "hadoop"):
            assert lib in SKILL_RESOURCES

    def test_os_shell_entries_present(self):
        for entry in ("linux", "bash", "powershell"):
            assert entry in SKILL_RESOURCES

    def test_no_duplicate_display_names_for_core_techs(self):
        tech_display_names = [
            SKILL_RESOURCES[k].display_name
            for k in _TECH_VOCAB
            if k in SKILL_RESOURCES
        ]
        assert len(tech_display_names) == len(set(tech_display_names)), (
            "Duplicate display names found in tech entries"
        )


# ─── VALID_CATEGORIES and VALID_RESOURCE_TYPES ───────────────────────────────

class TestValidConstants:
    def test_valid_categories_is_frozenset(self):
        assert isinstance(VALID_CATEGORIES, frozenset)

    def test_soft_skill_in_valid_categories(self):
        assert "soft_skill" in VALID_CATEGORIES

    def test_programming_in_valid_categories(self):
        assert "programming" in VALID_CATEGORIES

    def test_valid_resource_types_is_frozenset(self):
        assert isinstance(VALID_RESOURCE_TYPES, frozenset)

    def test_docs_in_valid_resource_types(self):
        assert "docs" in VALID_RESOURCE_TYPES

    def test_certification_in_valid_resource_types(self):
        assert "certification" in VALID_RESOURCE_TYPES

    def test_course_in_valid_resource_types(self):
        assert "course" in VALID_RESOURCE_TYPES

    def test_practice_in_valid_resource_types(self):
        assert "practice" in VALID_RESOURCE_TYPES


# ─── Backward compatibility ───────────────────────────────────────────────────

class TestBackwardCompatibility:
    def test_get_resources_for_gaps_handles_three_key_dict(self):
        old_gaps = {"critical": ["docker"], "moderate": [], "low": []}
        result = get_resources_for_gaps(old_gaps)
        assert set(result.keys()) == {"critical", "moderate", "low"}
        assert result["critical"][0]["display_name"] == "Docker"

    def test_get_resources_for_gaps_handles_four_key_dict(self):
        new_gaps = {"critical": ["react"], "moderate": [], "soft": ["agile"], "low": []}
        result = get_resources_for_gaps(new_gaps)
        assert set(result.keys()) == {"critical", "moderate", "soft", "low"}

    def test_missing_soft_key_does_not_raise(self):
        old_gaps = {"critical": [], "moderate": [], "low": []}
        result = get_resources_for_gaps(old_gaps)
        assert "soft" not in result

    def test_empty_lists_in_old_format_produce_empty_lists(self):
        old_gaps = {"critical": [], "moderate": [], "low": []}
        result = get_resources_for_gaps(old_gaps)
        assert result == {"critical": [], "moderate": [], "low": []}
