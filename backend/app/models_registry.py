"""Import every model so Base.metadata is complete (used by Alembic and the app)."""
from app.modules.auth.models import PasswordResetToken, RefreshToken, User  # noqa: F401
from app.modules.documents.models import Document, RenewalHistory  # noqa: F401
from app.modules.notifications.models import EmailDispatch  # noqa: F401
from app.modules.reminders.models import ReminderLog  # noqa: F401
from app.modules.vehicles.models import Vehicle  # noqa: F401
