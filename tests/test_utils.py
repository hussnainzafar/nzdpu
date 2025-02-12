"""Test utility functions"""

from app.utils import check_password, encrypt_password


class TestUtils:
    """
    Unit tests for utility functions
    """

    def test_encrypt_decrypt(self):
        """
        GIVEN a string
        WHEN it is encrypted
        THEN check the un-encrypted version matches the original string
        """

        pwd: str = "testpassword"
        encrypted_pwd: str = encrypt_password(pwd)
        assert check_password(pwd, encrypted_pwd)
