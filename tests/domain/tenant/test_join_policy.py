import pytest

from app.domain.tenant.join_policy import (
    MAX_ALLOWED_DOMAINS,
    JoinPolicyError,
    TenantJoinPolicy,
)
from app.domain.tenant.value_objects import MembershipRole, TenantId


def policy(domains=("futa.edu.ng",), enabled=True):
    p = TenantJoinPolicy(tenant_id=TenantId("t1"))
    p.configure(enabled=enabled, allowed_domains=list(domains), updated_by_user_id="owner-1")
    return p


def test_off_by_default():
    p = TenantJoinPolicy(tenant_id=TenantId("t1"))

    assert p.enabled is False
    assert p.auto_join_role_for("ada@futa.edu.ng", email_verified=True) is None


def test_a_verified_address_on_an_allowed_domain_is_eligible_as_a_student():
    assert policy().auto_join_role_for("Ada@FUTA.edu.ng", email_verified=True) is MembershipRole.STUDENT


def test_an_unverified_address_is_never_eligible():
    assert policy().auto_join_role_for("ada@futa.edu.ng", email_verified=False) is None


@pytest.mark.parametrize(
    "email",
    [
        "ada@student.futa.edu.ng",  # subdomains must be listed explicitly
        "ada@evilfuta.edu.ng",
        "ada@futa.edu.ng.evil.com",
        "ada@gmail.com",
    ],
)
def test_only_exact_domains_match(email):
    assert policy().auto_join_role_for(email, email_verified=True) is None


def test_a_disabled_policy_keeps_its_domains_but_grants_nothing():
    p = policy(enabled=False)

    assert p.allowed_domains == ("futa.edu.ng",)
    assert p.auto_join_role_for("ada@futa.edu.ng", email_verified=True) is None


def test_domains_are_normalised_and_deduplicated():
    p = policy(domains=[" FUTA.edu.ng ", "futa.edu.ng", "student.futa.edu.ng"])

    assert p.allowed_domains == ("futa.edu.ng", "student.futa.edu.ng")


@pytest.mark.parametrize("bad", ["@futa.edu.ng", "*.futa.edu.ng", "futa", "futa..edu.ng", "-futa.edu.ng", "futa.edu.ng/x", ""])
def test_invalid_domains_are_rejected(bad):
    with pytest.raises(JoinPolicyError):
        policy(domains=[bad])


@pytest.mark.parametrize("role", [MembershipRole.LECTURER, MembershipRole.ADMIN, MembershipRole.OWNER])
def test_email_domain_join_cannot_grant_staff_roles(role):
    p = TenantJoinPolicy(tenant_id=TenantId("t1"))

    with pytest.raises(JoinPolicyError):
        p.configure(enabled=True, allowed_domains=["futa.edu.ng"], default_role=role, updated_by_user_id=None)
    with pytest.raises(JoinPolicyError):
        TenantJoinPolicy(tenant_id=TenantId("t1"), default_role=role)


def test_an_enabled_policy_needs_a_domain_and_has_a_limit():
    with pytest.raises(JoinPolicyError):
        policy(domains=[])
    with pytest.raises(JoinPolicyError):
        policy(domains=[f"d{i}.edu.ng" for i in range(MAX_ALLOWED_DOMAINS + 1)])


def test_a_failed_reconfiguration_leaves_the_policy_unchanged():
    p = policy()

    with pytest.raises(JoinPolicyError):
        p.configure(enabled=True, allowed_domains=["not a domain"], updated_by_user_id=None)

    assert (p.enabled, p.allowed_domains) == (True, ("futa.edu.ng",))
