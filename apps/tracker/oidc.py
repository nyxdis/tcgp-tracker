"""OIDC authentication backend for logging in via Authentik."""

from mozilla_django_oidc.auth import OIDCAuthenticationBackend


class AuthentikOIDCBackend(OIDCAuthenticationBackend):
    """Match existing users by username first, falling back to email.

    The base backend only matches by email, so accounts registered here
    before OIDC was added (username set, email unset/mismatched) fail to
    link and hit a duplicate-username IntegrityError on create_user instead.
    Username is also the more reliable identifier for this app specifically,
    since it's user-facing (friend search, profiles) and set to match the
    authentik username by convention.

    The base backend also generates a random UUID username for accounts it
    creates. Using the `preferred_username` claim instead keeps OIDC-created
    accounts consistent with ones made through the regular registration form.
    """

    def get_username(self, claims):
        return claims.get("preferred_username") or super().get_username(claims)

    def filter_users_by_claims(self, claims):
        username = claims.get("preferred_username")
        if username:
            users = self.UserModel.objects.filter(username__iexact=username)
            if users.exists():
                return users
        return super().filter_users_by_claims(claims)
