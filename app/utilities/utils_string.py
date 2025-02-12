import hashlib


def consistent_hash(input_string: str):
    # Convert string to a consistent format
    normalized_string = input_string.lower()  # Convert to lowercase

    # Generate SHA-256 hash
    hash_object = hashlib.sha256(normalized_string.encode())
    hash_hex = hash_object.hexdigest()

    return hash_hex
