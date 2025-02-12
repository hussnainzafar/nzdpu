"Metric response schemas"

from pydantic import BaseModel


class ActiveUsersMetricResponse(BaseModel):
    """
    Response for /metrics endpoint
    """

    active_users: int
    days: int
    total: int
