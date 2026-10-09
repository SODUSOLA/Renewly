import enum


# class: kinds of document a user can track. `CUSTOM` requires a custom label
class DocumentType(str, enum.Enum):
    """Kinds of document a user can track. `CUSTOM` requires a custom label."""

    DRIVER_LICENSE = "driver_license"
    INSURANCE = "insurance"
    VEHICLE_REGISTRATION = "vehicle_registration"
    PERMIT = "permit"
    CUSTOM = "custom"


# class: delivery channels for reminders. Only email in v1
class ReminderChannel(str, enum.Enum):
    """Delivery channels for reminders. Only email in v1."""

    EMAIL = "email"
    # SMS = "sms"            # v2
    # WHATSAPP = "whatsapp"  # v2


# class: outcome of a reminder attempt, recorded in the reminder log
class ReminderStatus(str, enum.Enum):
    """State of a reminder attempt: claimed (pending), then sent or failed."""

    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"


# func: store the enum's value (e.g. 'driver_license'), not its name
def enum_values(enum_cls: type[enum.Enum]) -> list[str]:
    """Store the enum's value (e.g. 'driver_license'), not its name."""
    return [member.value for member in enum_cls]


# class: derived state of a document relative to today (never stored)
class DocumentStatus(str, enum.Enum):
    """Derived state of a document, computed from its expiry date and never stored."""

    VALID = "valid"
    EXPIRING_SOON = "expiring_soon"
    EXPIRED = "expired"


# class for how a user wants their reminders delivered
class ReminderStyle(str, enum.Enum):
    """`EACH`: one email per document reminder. `DIGEST`: one email a day with everything due."""

    EACH = "each"
    DIGEST = "digest"
