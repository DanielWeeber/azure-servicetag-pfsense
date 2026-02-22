import json
import unittest
from unittest.mock import patch

from scripts.azure_service_tags_sync import AliasDefinition, sync_pfsense_aliases


class FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


def build_alias(name: str, addresses: list[str]) -> AliasDefinition:
    return AliasDefinition(
        name=name,
        alias_type="network",
        addresses=addresses,
        description=f"Azure Service Tag {name}",
        source_tag=name,
        service="AzureCloud",
        region="westeurope",
    )


class PfrestSyncTests(unittest.TestCase):
    def test_update_only_skips_create(self) -> None:
        existing_aliases = {
            "data": [
                {
                    "id": 10,
                    "name": "azure_service_tag_Existing",
                    "type": "network",
                    "descr": "Azure Service Tag azure_service_tag_Existing",
                    "address": ["1.1.1.0/24"],
                }
            ]
        }
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.side_effect = [
                FakeResponse(existing_aliases),
                FakeResponse({"data": {"id": 10}}),
            ]
            results = sync_pfsense_aliases(
                aliases=[
                    build_alias("azure_service_tag_Existing", ["1.1.2.0/24"]),
                    build_alias("azure_service_tag_Missing", ["2.2.2.0/24"]),
                ],
                base_url="https://pfsense:441",
                api_key="token",
                tls_insecure=True,
                update_only=True,
                apply_changes=False,
            )

        self.assertEqual(results["updated"], 1)
        self.assertEqual(results["created"], 0)
        self.assertEqual(results["skipped"], 1)

        self.assertEqual(mock_urlopen.call_count, 2)
        patch_request = mock_urlopen.call_args_list[1][0][0]
        self.assertEqual(patch_request.get_method(), "PATCH")

    def test_allow_create_posts_missing_alias(self) -> None:
        existing_aliases = {"data": []}
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.side_effect = [
                FakeResponse(existing_aliases),
                FakeResponse({"data": {"id": 20}}),
            ]
            results = sync_pfsense_aliases(
                aliases=[build_alias("azure_service_tag_New", ["3.3.3.0/24"])],
                base_url="https://pfsense:441",
                api_key="token",
                tls_insecure=False,
                update_only=False,
                apply_changes=False,
            )

        self.assertEqual(results["created"], 1)
        self.assertEqual(results["updated"], 0)
        self.assertEqual(results["skipped"], 0)
        self.assertEqual(mock_urlopen.call_count, 2)
        post_request = mock_urlopen.call_args_list[1][0][0]
        self.assertEqual(post_request.get_method(), "POST")


if __name__ == "__main__":
    unittest.main()