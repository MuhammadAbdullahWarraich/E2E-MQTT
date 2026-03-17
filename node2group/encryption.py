# the purpose of this file is to allow changing the encryption implementation without changing much code(kind of like a mini platform layer)
from .mock_encryption_lib import mock_decryption_algo as decrypt_data
from .mock_encryption_lib import mock_encryption_algo as encrypt_data