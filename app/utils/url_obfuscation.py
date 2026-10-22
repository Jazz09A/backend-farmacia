import base64


class URLObfuscator:
    """Utility class for obfuscating and deobfuscating product URLs."""

    @staticmethod
    def encode_url(product_id: str, product_name: str = "") -> str:
        """
        Encode product ID and name into an obfuscated URL.

        Args:
            product_id: The product ID
            product_name: Optional product name for SEO-friendly URLs

        Returns:
            Obfuscated URL string
        """
        try:
            # Create a simple encoding scheme
            combined = f"{product_id}"
            encoded_bytes = base64.urlsafe_b64encode(combined.encode("utf-8"))
            encoded_str = encoded_bytes.decode("utf-8").rstrip("=")

            # Add product name if provided for SEO
            if product_name:
                # Clean product name for URL
                clean_name = URLObfuscator._clean_name_for_url(product_name)
                return f"{clean_name}-{encoded_str}"

            return encoded_str
        except Exception:
            return product_id  # Fallback to original ID

    @staticmethod
    def decode_url(obfuscated_url: str) -> str | None:
        """
        Decode obfuscated URL back to product ID.

        Args:
            obfuscated_url: The obfuscated URL string

        Returns:
            Product ID if successful, None if failed
        """
        try:
            # Remove product name if present (everything before last dash)
            if "-" in obfuscated_url:
                encoded_part = obfuscated_url.split("-")[-1]
            else:
                encoded_part = obfuscated_url

            # Add padding if needed
            missing_padding = len(encoded_part) % 4
            if missing_padding:
                encoded_part += "=" * (4 - missing_padding)

            # Decode
            decoded_bytes = base64.urlsafe_b64decode(encoded_part.encode("utf-8"))
            decoded_str = decoded_bytes.decode("utf-8")

            return decoded_str
        except Exception:
            return None

    @staticmethod
    def _clean_name_for_url(name: str) -> str:
        """
        Clean product name for URL usage.

        Args:
            name: Product name

        Returns:
            Cleaned name suitable for URLs
        """
        # Convert to lowercase
        clean_name = name.lower()

        # Replace spaces and special characters with hyphens
        import re

        clean_name = re.sub(r"[^a-z0-9\s-]", "", clean_name)
        clean_name = re.sub(r"\s+", "-", clean_name)
        clean_name = re.sub(r"-+", "-", clean_name)

        # Remove leading/trailing hyphens
        clean_name = clean_name.strip("-")

        # Limit length
        if len(clean_name) > 50:
            clean_name = clean_name[:50].rstrip("-")

        return clean_name

    @staticmethod
    def create_product_url(product_id: str, product_name: str) -> str:
        """
        Create a SEO-friendly product URL.

        Args:
            product_id: Product ID
            product_name: Product name

        Returns:
            SEO-friendly URL
        """
        return URLObfuscator.encode_url(product_id, product_name)

    @staticmethod
    def generate_slug(text: str) -> str:
        """
        Generate a URL slug from text.

        Args:
            text: Input text

        Returns:
            URL-safe slug
        """
        return URLObfuscator._clean_name_for_url(text)
