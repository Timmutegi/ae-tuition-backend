import secrets
import string


def generate_secure_password(length: int = 10) -> str:
    """Generate cryptographically secure password with mixed case, numbers, and symbols."""

    if length < 8:
        length = 8  # Minimum password length
    elif length > 20:
        length = 20  # Maximum password length

    # Define character sets
    lowercase = string.ascii_lowercase
    uppercase = string.ascii_uppercase
    digits = string.digits
    symbols = "!@#$%^&*"

    # Ensure at least one character from each required set
    password = [
        secrets.choice(lowercase),
        secrets.choice(uppercase),
        secrets.choice(digits),
        secrets.choice(symbols)
    ]

    # Fill the rest with random characters from all sets
    all_chars = lowercase + uppercase + digits + symbols
    password.extend(secrets.choice(all_chars) for _ in range(length - 4))

    # Shuffle to avoid predictable patterns
    secrets.SystemRandom().shuffle(password)

    return ''.join(password)