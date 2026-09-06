from pydantic import BaseModel


class RouteStop(BaseModel):
    """A single route-stop pair: one stop served by one KMB lane (route+bound+service_type)."""
    co: str = "KMB"
    route: str
    bound: str  # normalized: "O" (outbound) or "I" (inbound)
    service_type: str
    seq: int
    stop: str
    data_timestamp: str | None = None


class RouteStopListResponse(BaseModel):
    type: str
    version: str
    generated_timestamp: str
    data: list[RouteStop]
