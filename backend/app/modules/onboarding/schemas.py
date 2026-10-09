"""Response shape for onboarding progress."""
from pydantic import BaseModel


# class for how much of the app a user has used so far
class OnboardingProgress(BaseModel):
    """Plain counts the web app turns into the getting-started checklist.

    Counted from real data (not remembered flags) so the checklist can never disagree with
    what is actually in the account. Deleted documents do not count.
    """

    documents: int
    vehicles: int
    renewals: int
    renewals_with_cost: int
