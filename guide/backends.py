"""
Login mit Benutzername ODER E-Mail.

Django prüft beim Login normalerweise nur den Benutzernamen. Dieses "Backend" schaut zuerst,
ob im Feld ein @ steht. Wenn ja, sucht es die Person über die E-Mail-Adresse.
Danach prüft Django das Passwort ganz normal (als Hash, nie im Klartext).
"""
from django.contrib.auth.backends import ModelBackend
from django.contrib.auth.models import User


class EmailOrUsernameBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        if username and "@" in username:
            user = User.objects.filter(email__iexact=username.strip()).order_by("id").first()
            if user is None:
                User().set_password(password)  # gleich lange rechnen wie bei echtem Konto (Schutz vor Ausprobieren)
                return None
            if user.check_password(password) and self.user_can_authenticate(user):
                return user
            return None
        # kein @: normaler Login mit Benutzername
        return super().authenticate(request, username=username, password=password, **kwargs)
