"""Import every model so Base.metadata is complete (used by Alembic and the app)."""
from app.modules.auth.models import PasswordResetToken, User  # noqa: F401
from app.modules.documents.models import Document, RenewalHistory  # noqa: F401
from app.modules.reminders.models import ReminderLog  # noqa: F401
from app.modules.vehicles.models import Vehicle  # noqa: F401
