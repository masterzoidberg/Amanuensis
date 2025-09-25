import json
import os
import base64
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import getpass

class SecureConfigManager:
    def __init__(self, config_file="config.json", auto_setup=True):
        self.config_file = config_file
        self.key = None
        self.config = {}

        # Auto-setup encryption for testing and ease of use
        if auto_setup:
            self._auto_setup_encryption()

    def _auto_setup_encryption(self):
        """Automatically setup encryption for testing and first-run scenarios"""
        try:
            # Check if salt file exists (indicating previous setup)
            salt_file = f"{self.config_file}.salt"
            if os.path.exists(salt_file):
                # Try to load existing configuration with default password
                try:
                    with open(salt_file, "rb") as f:
                        salt = f.read()

                    # Use a default password for testing
                    default_password = "amanuensis_test_key_2024"
                    self.key, _ = self._derive_key(default_password, salt)

                    # Try to load existing config
                    if os.path.exists(self.config_file):
                        fernet = Fernet(self.key)
                        with open(self.config_file, "rb") as f:
                            encrypted_data = f.read()
                            decrypted_data = fernet.decrypt(encrypted_data)
                            self.config = json.loads(decrypted_data.decode())

                    return True
                except:
                    # If decryption fails, setup new encryption
                    pass

            # Setup new encryption with default password
            default_password = "amanuensis_test_key_2024"
            self.key, salt = self._derive_key(default_password)

            # Save salt for future use
            with open(salt_file, "wb") as f:
                f.write(salt)

            return True

        except Exception as e:
            # If auto-setup fails, continue without encryption (for testing)
            print(f"Warning: Auto-setup encryption failed: {e}")
            return False

    def _derive_key(self, password: str, salt: bytes = None) -> bytes:
        if salt is None:
            salt = os.urandom(16)

        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
        return key, salt

    def setup_encryption(self, password: str = None):
        if password is None:
            password = getpass.getpass("Enter master password for API key encryption: ")

        self.key, salt = self._derive_key(password)

        # Save salt for future decryption
        with open(f"{self.config_file}.salt", "wb") as f:
            f.write(salt)

        return True

    def load_config(self, password: str = None):
        if not os.path.exists(self.config_file):
            return {}

        if password is None:
            password = getpass.getpass("Enter master password: ")

        try:
            # Load salt
            with open(f"{self.config_file}.salt", "rb") as f:
                salt = f.read()

            self.key, _ = self._derive_key(password, salt)
            fernet = Fernet(self.key)

            with open(self.config_file, "rb") as f:
                encrypted_data = f.read()
                decrypted_data = fernet.decrypt(encrypted_data)
                self.config = json.loads(decrypted_data.decode())

            return self.config

        except Exception as e:
            print(f"Failed to decrypt config: {e}")
            return {}

    def save_config(self):
        if self.key is None:
            raise ValueError("Encryption not set up. Call setup_encryption() first.")

        fernet = Fernet(self.key)
        config_json = json.dumps(self.config, indent=2)
        encrypted_data = fernet.encrypt(config_json.encode())

        with open(self.config_file, "wb") as f:
            f.write(encrypted_data)

    def set_api_key(self, service: str, api_key: str):
        if 'api_keys' not in self.config:
            self.config['api_keys'] = {}
        self.config['api_keys'][service] = api_key
        self.save_config()

    def get_api_key(self, service: str) -> str:
        return self.config.get('api_keys', {}).get(service, '')

    def set_setting(self, key: str, value):
        if 'settings' not in self.config:
            self.config['settings'] = {}
        self.config['settings'][key] = value
        self.save_config()

    def get_setting(self, key: str, default=None):
        return self.config.get('settings', {}).get(key, default)

    def clear_memory(self):
        # Clear sensitive data from memory
        if hasattr(self, 'key'):
            self.key = None
        if hasattr(self, 'config'):
            self.config.clear()

    def validate_api_keys(self) -> dict:
        """Validate that required API keys are present"""
        required_keys = ['openai', 'anthropic']
        api_keys = self.config.get('api_keys', {})

        validation_result = {}
        for key in required_keys:
            validation_result[key] = bool(api_keys.get(key, '').strip())

        return validation_result