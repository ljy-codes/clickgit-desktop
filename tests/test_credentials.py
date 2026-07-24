from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from clickgit.credentials import (
    CredentialRequest,
    SshKeyService,
    build_credential_payload,
    parse_credential_output,
)
from clickgit.git_runner import GitRunner


class CredentialTests(unittest.TestCase):
    def test_build_and_parse_credential_payload(self) -> None:
        request = CredentialRequest(
            protocol="https",
            host="example.com",
            path="team/repo.git",
            username="user",
            password="secret",
        )

        payload = build_credential_payload(request)
        parsed = parse_credential_output(payload)

        self.assertEqual(parsed, request)
        self.assertTrue(payload.endswith(b"\n\n"))

    def test_credential_fields_reject_newline_injection(self) -> None:
        request = CredentialRequest(
            protocol="https",
            host="example.com\npassword=stolen",
        )

        with self.assertRaises(ValueError):
            build_credential_payload(request)

    def test_generate_and_read_ed25519_public_key(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            service = SshKeyService.from_git(GitRunner().git_executable)
            private_key = Path(temp_dir) / "id_clickgit"

            generated = service.generate(
                private_key,
                comment="clickgit@example.com",
                passphrase="",
            )

            self.assertEqual(generated, private_key)
            self.assertTrue(private_key.exists())
            self.assertTrue(private_key.with_suffix(".pub").exists())
            self.assertTrue(
                service.public_key(private_key).startswith("ssh-ed25519 ")
            )


if __name__ == "__main__":
    unittest.main()

