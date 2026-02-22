import json
import unittest
from pathlib import Path

from scripts.azure_service_tags_sync import extract_aliases

FIXTURE = Path(__file__).parent / "fixtures" / "service_tags_sample.json"


class ServiceTagsSyncTests(unittest.TestCase):
    def test_extract_aliases_filters_and_ipv6(self) -> None:
        data = json.loads(FIXTURE.read_text())
        aliases = extract_aliases(
            data,
            service_filters=["AzureCloud"],
            region_filters=["westeurope"],
            include_ipv6=False,
            name_prefix="azure_service_tag_",
            max_name_length=31,
        )
        self.assertEqual(len(aliases), 1)
        alias = aliases[0]
        self.assertEqual(alias.service, "AzureCloud")
        self.assertEqual(alias.region, "westeurope")
        self.assertEqual(alias.addresses, ["1.2.3.0/24"])
        self.assertTrue(alias.name.startswith("azure_service_tag_"))

    def test_global_alias_included_with_region_filter(self) -> None:
        data = {
            "values": [
                {
                    "name": "AzureActiveDirectory",
                    "properties": {
                        "systemService": "AzureActiveDirectory",
                        "region": "",
                        "addressPrefixes": ["4.3.2.0/24"],
                    },
                }
            ]
        }
        aliases = extract_aliases(
            data,
            service_filters=["AzureActiveDirectory"],
            region_filters=["West Europe"],
            include_ipv6=False,
            name_prefix="azure_service_tag_",
            max_name_length=31,
        )
        self.assertEqual(len(aliases), 1)
        self.assertEqual(aliases[0].region, "")

    def test_service_filter_matches_tag_name(self) -> None:
        data = {
            "values": [
                {
                    "name": "ServiceBus.WestEurope",
                    "properties": {
                        "systemService": "AzureServiceBus",
                        "region": "westeurope",
                        "addressPrefixes": ["5.6.7.0/24"],
                    },
                }
            ]
        }
        aliases = extract_aliases(
            data,
            service_filters=["ServiceBus"],
            region_filters=["West Europe"],
            include_ipv6=False,
            name_prefix="azure_service_tag_",
            max_name_length=31,
        )
        self.assertEqual(len(aliases), 1)
        self.assertEqual(aliases[0].service, "AzureServiceBus")


if __name__ == "__main__":
    unittest.main()
