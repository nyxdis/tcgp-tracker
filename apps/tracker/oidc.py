"""OIDC authentication backend for logging in via Authentik."""

from mozilla_django_oidc.auth import OIDCAuthenticationBackend


class AuthentikOIDCBackend(OIDCAuthenticationBackend):
    """Match existing users by email; use Authentik's username for new ones.

    The base backend generates a random UUID username for accounts it
    creates. Using the `preferred_username` claim instead keeps OIDC-created
    accounts consistent with ones made through the regular registration
    form, since usernames are user-facing here (friend search, profiles).
    """

    def get_username(self, claims):
        return claims.get("preferred_username") or super().get_username(claims)
