from app.utilities.utils_string import consistent_hash


class TestUtilities:
    """
    Unit tests for string utilities functions
    """

    def test_hashing_consistency(self):
        """
        GIVEN a string
        WHEN it is hashed
        THEN check the if the hash is consistent
        """

        string: str = "/coverage/companies?jurisdiction=Denmark&sics_sector=Transportation"
        string_hashed: str = consistent_hash(string)
        string_hashed_second: str = consistent_hash(string)
        assert string_hashed == string_hashed_second
