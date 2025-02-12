def mock_org(nz_id, score, source=None, latest_reported_year=None):
    return {
        "nz_id": nz_id,
        "score": score,
        "source": source,
        "latest_reported_year": latest_reported_year,
        "id": nz_id,
        "lei": "LEI001",
        "legal_name": "Legal Name",
        "created_on": "2024-01-01T00:00:00Z",
        "last_updated_on": "2024-01-02T00:00:00Z",
    }


class TestOrganizationService:
    pass
