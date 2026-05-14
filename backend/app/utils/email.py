# ================================================================
# NexusCare — utils/email.py
# Email normalization. Apply at every entry point (schema validators
# AND service lookups) so a stray code path can never compare against
# an un-normalized string.
# ================================================================


def normalize_email(value: str) -> str:
    """Trim surrounding whitespace and lowercase. Storage canonical form."""
    return value.strip().lower()
