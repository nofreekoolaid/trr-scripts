import os
import sys
import unittest
from unittest import TestCase, mock

import networkx as nx
from web3 import Web3

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from scanner.interaction_filters import InteractionFilter
from scanner.scanner import (
    APIRateLimiter,
    _is_eoa_cached,
    contract_name_cache,
    deployer_discovery_pass,
    fetch_contract_name,
    fetch_recent_transactions,
    get_contract_creator,
    get_contracts_deployed_by,
    get_receipt_interactions_strict,
    get_strict_interactions,
    is_eoa,
    processed_deployers,
    short_addr,
    simulate_and_extract,
)


class TestScannerUtils(TestCase):
    def setUp(self):
        self.test_addr = "0x14Bdc3A3AE09f5518b923b69489CBcAfB238e617"
        self.checksum_addr = Web3.to_checksum_address(self.test_addr)
        self.blacklist = {"0x1F98431c8aD98523631AE4a59f267346ea31F984"}


class TestEOACheck(TestScannerUtils):
    @mock.patch("scanner.scanner.w3.eth.get_code")
    def test_is_eoa(self, mock_get_code):
        # Test empty code (should be EOA)
        mock_get_code.return_value = b""
        result = is_eoa(self.test_addr)
        self.assertTrue(result)
        _is_eoa_cached.cache_clear()

        # non empty code
        mock_get_code.return_value = b"0x123456"
        result = is_eoa(self.test_addr)
        self.assertFalse(result)
        _is_eoa_cached.cache_clear()

        # blacklisted
        self.assertFalse(is_eoa("0x1F98431c8aD98523631AE4a59f267346ea31F984"))


class TestEtherscanAPI(TestScannerUtils):
    def setUp(self):
        super().setUp()
        contract_name_cache.clear()

        self.mock_get_patcher = mock.patch("scanner.scanner.session.get")
        self.mock_get = self.mock_get_patcher.start()

        self.original_limiter_wait = APIRateLimiter.wait
        APIRateLimiter.wait = lambda *args: None

    def tearDown(self):
        self.mock_get_patcher.stop()
        APIRateLimiter.wait = self.original_limiter_wait
        super().tearDown()

    def test_fetch_contract_name(self):
        self.mock_get.return_value.json.return_value = {
            "result": [{"ContractName": "PendlePrincipalToken", "Proxy": "0"}]
        }

        result = fetch_contract_name(self.test_addr)

        self.mock_get.assert_called_once()
        self.assertEqual(result, "PendlePrincipalToken")

    def test_fetch_contract_name_error_response(self):
        self.mock_get.return_value.json.return_value = {
            "status": "0",
            "message": "Invalid API Key",
            "result": "",
        }
        name = fetch_contract_name(self.test_addr)
        expected = short_addr(Web3.to_checksum_address(self.test_addr))
        self.assertEqual(name, expected)

    def test_fetch_contract_name_empty_response(self):
        self.mock_get.return_value.json.return_value = {
            "status": "1",
            "message": "OK",
            "result": [],
        }
        name = fetch_contract_name(self.test_addr)
        expected = short_addr(Web3.to_checksum_address(self.test_addr))
        self.assertEqual(name, expected)

    def test_get_contract_creator(self):
        CONTRACT_CREATION = {
            "status": "1",
            "message": "OK",
            "result": [
                {
                    "contractAddress": "0x14bdc3a3ae09f5518b923b69489cbcafb238e617",
                    "contractCreator": "0xeba675f1d0fe4c00e179c1f224b8b18dd476e76a",
                    "txHash": "0xeb41d87f9f1c5c871f9eecd2676387e661bc984bbbb5153230f714e5943d9fc6",
                    "blockNumber": "22472324",
                    "timestamp": "1747115327",
                    "contractFactory": "0x35a338522a435d46f77be32c70e215b813d0e3ac",
                    "creationBytecode": "0x61010060...",
                }
            ],
        }

        mock_response = mock.MagicMock()
        mock_response.json.return_value = CONTRACT_CREATION
        mock_response.raise_for_status.return_value = None

        self.mock_get.return_value = mock_response

        creator = get_contract_creator(self.test_addr)

        expected = Web3.to_checksum_address("0xeba675f1d0fe4c00e179c1f224b8b18dd476e76a")
        self.assertEqual(creator, expected)

        self.mock_get.assert_called_once_with(
            "https://api.etherscan.io/api",
            params={
                "module": "contract",
                "action": "getcontractcreation",
                "contractaddresses": self.checksum_addr,
                "apikey": mock.ANY,
            },
            timeout=30,
        )

    def test_fetch_recent_transactions(self):
        mock_tx_hashes = [
            "0x7e1184333dcf5eaf94ada8ef085ed14eefaa4ac17210ae0f2f7f60f2440800e8",
            "0xac8b350293361c8e04876670ca6bf92a32fd8867e2b59d02eb27dbc6bb660b85",
            "0x60a4f8d1130cc4f9868ce486d1c06cc2d80441bedb4fe56b264f791976ef021b",
        ]

        self.mock_get.return_value.json.return_value = {
            "status": "1",
            "message": "OK",
            "result": [
                {
                    "hash": tx_hash,
                    "to": self.test_addr.lower(),
                    "from": "0x0000000000000000000000000000000000000000",
                    "blockNumber": "12345678",
                    "timeStamp": 160000,
                    "value": "0",
                }
                for tx_hash in mock_tx_hashes
            ],
        }

        txs = fetch_recent_transactions(self.test_addr, limit=3)

        self.mock_get.assert_called_once()
        self.assertEqual(len(txs), 3)
        self.assertEqual(txs, mock_tx_hashes)

        self.assertEqual(
            txs[0], "0x7e1184333dcf5eaf94ada8ef085ed14eefaa4ac17210ae0f2f7f60f2440800e8"
        )
        self.assertEqual(
            txs[-1], "0x60a4f8d1130cc4f9868ce486d1c06cc2d80441bedb4fe56b264f791976ef021b"
        )


class TestSimulateAndExtract(TestScannerUtils):
    def setUp(self):
        super().setUp()
        self.tx_hash = "0x1234567890abcdef"

        self.mock_w3 = mock.MagicMock()
        self.w3_patch = mock.patch("scanner.scanner.w3", new=self.mock_w3)
        self.w3_patch.start()

        self.mock_w3.eth.get_code.return_value = b"0x123"

        self.requests_patch = mock.patch("scanner.scanner.session.post")
        self.mock_post = self.requests_patch.start()
        self.limiter_patch = mock.patch("scanner.scanner.limiter.wait")
        self.mock_limiter = self.limiter_patch.start()
        self.etherscan_patch = mock.patch("scanner.scanner.fetch_interactions_etherscan")
        self.mock_etherscan = self.etherscan_patch.start()

    def tearDown(self):
        self.w3_patch.stop()
        self.requests_patch.stop()
        self.limiter_patch.stop()
        self.etherscan_patch.stop()
        super().tearDown()

    # This function has been changed
    # def test_tenderly_success(self):
    #     self.mock_post.return_value.json.return_value = {
    #         "result": {
    #             "trace": [{"to": "0x1111111111111111111111111111111111111111"}],
    #             "logs": [{"address": "0x2222222222222222222222222222222222222222"}],
    #             "stateChanges": [{"address": "0x3333333333333333333333333333333333333333"}]
    #         }
    #     }

    #     def get_code_side_effect(addr):
    #         addr = addr.lower() if addr else addr
    #         if addr == "0x1111111111111111111111111111111111111111":
    #             return b'0x123'
    #         elif addr == "0x2222222222222222222222222222222222222222":
    #             return b'0x123'
    #         elif addr == "0x3333333333333333333333333333333333333333":
    #             return b'0x123'
    #         return b''

    #     self.mock_w3.eth.get_code.side_effect = get_code_side_effect

    #     result = simulate_and_extract(self.tx_hash)

    #     self.assertEqual(len(result), 3)
    #     self.assertIn("0x1111111111111111111111111111111111111111", result)
    #     self.assertIn("0x2222222222222222222222222222222222222222", result)
    #     self.assertIn("0x3333333333333333333333333333333333333333", result)


class TestDeployerDiscovery(TestScannerUtils):
    def setUp(self):
        super().setUp()
        self.deployer_addr = Web3.to_checksum_address("0xdedd000000000000000000000000000000000001")
        self.sibling1 = Web3.to_checksum_address("0xabcd000000000000000000000000000000000001")
        self.sibling2 = Web3.to_checksum_address("0xabcd000000000000000000000000000000000002")

        self.mock_get_patcher = mock.patch("scanner.scanner.session.get")
        self.mock_get = self.mock_get_patcher.start()

        self.mock_w3 = mock.MagicMock()
        self.w3_patch = mock.patch("scanner.scanner.w3", new=self.mock_w3)
        self.w3_patch.start()

        self.mock_w3.eth.get_code.return_value = b"0x123"

    def tearDown(self):
        self.mock_get_patcher.stop()
        self.w3_patch.stop()
        super().tearDown()

    def test_get_contracts_deployed_by(self):
        blacklist_addr = Web3.to_checksum_address(list(self.blacklist)[0])
        mock_response = mock.MagicMock()
        mock_json_response = {
            "status": "1",
            "message": "OK",
            "result": [
                {"to": "", "contractAddress": self.sibling1},
                {"to": "", "contractAddress": self.sibling2},
                {"to": "0x0000000000000000000000000000000000000000", "contractAddress": ""},
                {"to": "", "contractAddress": blacklist_addr},
            ],
        }
        mock_response.json.return_value = mock_json_response
        mock_response.raise_for_status.return_value = None

        self.mock_get.return_value = mock_response

        # Patch BLACKLIST to match test blacklist
        with mock.patch("scanner.scanner.BLACKLIST", self.blacklist):
            contracts = get_contracts_deployed_by(self.deployer_addr)

        # Verify API call was made correctly
        self.mock_get.assert_called_once_with(
            "https://api.etherscan.io/api",
            params={
                "module": "account",
                "action": "txlist",
                "address": self.deployer_addr,
                "startblock": 0,
                "endblock": 99999999,
                "sort": "asc",
                "apikey": mock.ANY,
            },
            timeout=30,
        )

        # Verify results
        self.assertEqual(len(contracts), 2)
        self.assertIn(self.sibling1, contracts)
        self.assertIn(self.sibling2, contracts)
        self.assertNotIn(blacklist_addr, contracts)

    def test_deployer_discovery_pass(self):
        # Create mock responses for ALL API calls
        # 1. fetch_contract_name for test_addr (getsourcecode) - may make 2 calls if proxy
        mock_response1 = mock.MagicMock()
        mock_response1.json.return_value = {
            "status": "1",
            "message": "OK",
            "result": [{"ContractName": "TestContract", "Proxy": "0"}],
        }
        mock_response1.raise_for_status.return_value = None

        # 2. get_contract_creator for test_addr (getcontractcreation)
        mock_response2 = mock.MagicMock()
        mock_response2.json.return_value = {
            "status": "1",
            "message": "OK",
            "result": [{"contractCreator": self.deployer_addr, "contractAddress": self.test_addr}],
        }
        mock_response2.raise_for_status.return_value = None

        # 3. get_contracts_deployed_by for deployer_addr (txlist)
        mock_response3 = mock.MagicMock()
        mock_response3.json.return_value = {
            "status": "1",
            "message": "OK",
            "result": [
                {"to": "", "contractAddress": self.sibling1},
                {"to": "", "contractAddress": self.sibling2},
            ],
        }
        mock_response3.raise_for_status.return_value = None

        # 4-5. fetch_contract_name for sibling1 and sibling2 (getsourcecode)
        mock_response4 = mock.MagicMock()
        mock_response4.json.return_value = {
            "status": "1",
            "message": "OK",
            "result": [{"ContractName": "Sibling1", "Proxy": "0"}],
        }
        mock_response4.raise_for_status.return_value = None

        mock_response5 = mock.MagicMock()
        mock_response5.json.return_value = {
            "status": "1",
            "message": "OK",
            "result": [{"ContractName": "Sibling2", "Proxy": "0"}],
        }
        mock_response5.raise_for_status.return_value = None

        # Set up the side effect for all 5 calls
        self.mock_get.side_effect = [
            mock_response1,
            mock_response2,
            mock_response3,
            mock_response4,
            mock_response5,
        ]

        test_graph = nx.DiGraph()
        discovered = set()
        untraced = set()

        # Clear processed deployers and cache before test
        global processed_deployers
        processed_deployers.clear()
        contract_name_cache.clear()

        # Mock is_eoa to return False for sibling contracts
        with mock.patch("scanner.scanner.is_eoa", return_value=False):
            new_contracts = deployer_discovery_pass(
                contracts_to_check=[self.test_addr],
                blacklist=self.blacklist,
                contract_graph=test_graph,
                discovered_contracts=discovered,
                untraced_contracts=untraced,
                label="test",
            )

        # Should make 5 calls: 1 (fetch name) + 1 (get creator) + 1 (get deployed) + 2 (fetch names for siblings)
        self.assertEqual(self.mock_get.call_count, 5)

        # Verify results
        self.assertEqual(len(new_contracts), 2)
        self.assertEqual(len(discovered), 2)
        self.assertIn(self.sibling1, discovered)
        self.assertIn(self.sibling2, discovered)
        self.assertEqual(test_graph.number_of_nodes(), 3)
        self.assertEqual(test_graph.number_of_edges(), 2)

        # Verify graph properties
        discovery_methods = test_graph.nodes[self.sibling1].get("discovery_methods", [])
        self.assertIn("test", discovery_methods)

        # Verify deployer edge was created
        self.assertTrue(test_graph.has_edge(self.deployer_addr, self.sibling1))
        self.assertTrue(test_graph.has_edge(self.deployer_addr, self.sibling2))


class TestTraceBasedDiscovery(TestScannerUtils):
    def setUp(self):
        super().setUp()
        self.tx_hash = "0x1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef"

        # Mock the trace provider
        self.trace_provider_patch = mock.patch("scanner.scanner.get_trace_provider")
        self.mock_get_provider = self.trace_provider_patch.start()

        # Mock interaction filter
        self.filter_patch = mock.patch("scanner.scanner.InteractionFilter")
        self.mock_filter_class = self.filter_patch.start()
        self.mock_filter = mock.MagicMock()
        self.mock_filter_class.return_value = self.mock_filter

        # Mock config
        self.config_patch = mock.patch(
            "scanner.scanner.config",
            {"strict_interaction_mode": True, "trace_provider_preference": ["tenderly"]},
        )
        self.config_patch.start()

    def tearDown(self):
        self.trace_provider_patch.stop()
        self.filter_patch.stop()
        self.config_patch.stop()
        super().tearDown()

    def test_get_strict_interactions_trace_success(self):
        """Test successful trace-based interaction discovery"""
        # Mock trace provider
        mock_provider = mock.MagicMock()
        mock_provider.get_transaction_trace.return_value = {
            "from": self.test_addr,
            "to": "0xTarget",
            "calls": [{"from": self.test_addr, "to": "0xDirectCall"}],
        }
        mock_provider.extract_direct_calls.return_value = {"0xDirectCall"}
        self.mock_get_provider.return_value = mock_provider

        # Mock filter
        self.mock_filter.filter_interactions.return_value = ["0xDirectCall"]

        result = get_strict_interactions(
            self.tx_hash, self.test_addr, interaction_filter=self.mock_filter
        )

        self.assertEqual(result, ["0xDirectCall"])
        mock_provider.get_transaction_trace.assert_called_once_with(self.tx_hash)
        self.mock_filter.filter_interactions.assert_called_once()

    def test_get_strict_interactions_provider_fallback(self):
        """Test provider fallback mechanism"""
        # First provider fails
        mock_provider1 = mock.MagicMock()
        mock_provider1.get_transaction_trace.side_effect = Exception("Provider failed")

        # Second provider succeeds
        mock_provider2 = mock.MagicMock()
        mock_provider2.get_transaction_trace.return_value = {
            "from": self.test_addr,
            "calls": [{"from": self.test_addr, "to": "0xDirectCall"}],
        }
        mock_provider2.extract_direct_calls.return_value = {"0xDirectCall"}

        self.mock_get_provider.side_effect = [mock_provider1, mock_provider2]

        # Mock filter
        self.mock_filter.filter_interactions.return_value = ["0xDirectCall"]

        # Mock config with multiple providers
        with mock.patch(
            "scanner.scanner.config",
            {
                "strict_interaction_mode": True,
                "trace_provider_preference": ["failed_provider", "working_provider"],
            },
        ):
            result = get_strict_interactions(
                self.tx_hash, self.test_addr, interaction_filter=self.mock_filter
            )

            # Should have tried both providers
            self.assertEqual(self.mock_get_provider.call_count, 2)
            # Should return the result from the second provider
            self.assertEqual(result, ["0xDirectCall"])
            # Should have called filter interactions
            self.mock_filter.filter_interactions.assert_called_once()

    def test_get_strict_interactions_strict_mode_disabled(self):
        """Test behavior when strict mode is disabled"""
        with mock.patch("scanner.scanner.config", {"strict_interaction_mode": False}):
            # Mock receipt interactions
            with mock.patch("scanner.scanner.get_receipt_interactions_strict") as mock_receipt:
                mock_receipt.return_value = ["0xReceiptTarget"]
                self.mock_filter.filter_interactions.return_value = ["0xFilteredTarget"]

                result = get_strict_interactions(
                    self.tx_hash, self.test_addr, interaction_filter=self.mock_filter
                )

                # Should use receipt-based approach
                mock_receipt.assert_called_once_with(self.tx_hash, self.test_addr, self.mock_filter)
                self.mock_filter.filter_interactions.assert_called_once_with(
                    ["0xReceiptTarget"], self.test_addr, None
                )
                # Should return filtered result
                self.assertEqual(result, ["0xFilteredTarget"])


class TestInteractionFilter(TestScannerUtils):
    def setUp(self):
        super().setUp()
        self.config = {
            "strict_interaction_mode": True,
            "protocol_factory_addresses": ["0x5C69bEe701ef814a2B6a3EDD4B1652CB9cc5aA6f"],
            "allowed_event_signatures": [
                "0x0d3648bd0f6ba80134a33ba9275ac585d9d315f0ad8355cddefde31afa28d0e9"
            ],
            "blacklist_contracts": ["0x1F98431c8aD98523631AE4a59f267346ea31F984"],
        }

        self.filter = InteractionFilter(self.config)

    def test_is_protocol_factory(self):
        """Test factory address detection"""
        self.assertTrue(
            self.filter.is_protocol_factory("0x5C69bEe701ef814a2B6a3EDD4B1652CB9cc5aA6f")
        )
        self.assertFalse(self.filter.is_protocol_factory("0xNonFactoryAddress"))

    def test_filter_interactions_basic(self):
        """Test basic interaction filtering"""
        interactions = [
            "0x5C69bEe701ef814a2B6a3EDD4B1652CB9cc5aA6f",  # Should keep (factory)
            "0x1F98431c8aD98523631AE4a59f267346ea31F984",  # Should remove (blacklisted)
            "0x6B175474E89094C44Da98b954EedeAC495271d0F",  # Should remove (non-factory, no event data)
            "0x0000000000000000000000000000000000000000",  # Should remove (EOA)
        ]

        # Mock EOA check
        with mock.patch("scanner.scanner.is_eoa") as mock_is_eoa:
            mock_is_eoa.side_effect = (
                lambda addr: addr == "0x0000000000000000000000000000000000000000"
            )

            result = self.filter.filter_interactions(interactions, self.test_addr, None)

        # Only factory addresses should be kept when strict mode is on and no event data
        self.assertIn("0x5C69bEe701ef814a2B6a3EDD4B1652CB9cc5aA6f", result)
        self.assertNotIn("0x6B175474E89094C44Da98b954EedeAC495271d0F", result)
        self.assertNotIn("0x1F98431c8aD98523631AE4a59f267346ea31F984", result)
        self.assertNotIn("0x0000000000000000000000000000000000000000", result)

    def test_filter_interactions_with_event_data(self):
        """Test filtering with event data"""
        interactions = ["0x6B175474E89094C44Da98b954EedeAC495271d0F"]

        tx_data = {
            "logs": [
                {
                    "address": "0x6B175474E89094C44Da98b954EedeAC495271d0F",
                    "topics": [
                        "0x0d3648bd0f6ba80134a33ba9275ac585d9d315f0ad8355cddefde31afa28d0e9",
                        "0xOtherData",
                    ],
                }
            ]
        }

        result = self.filter.filter_interactions(interactions, self.test_addr, tx_data)

        # Should keep contract with allowed event
        self.assertIn("0x6B175474E89094C44Da98b954EedeAC495271d0F", result)


class TestReceiptInteractionsStrict(TestScannerUtils):
    def setUp(self):
        super().setUp()
        self.tx_hash = "0x1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef"

        # Mock dependencies
        self.receipt_patch = mock.patch("scanner.scanner.get_transaction_receipt")
        self.mock_get_receipt = self.receipt_patch.start()

        self.etherscan_patch = mock.patch("scanner.scanner.fetch_interactions_etherscan")
        self.mock_etherscan = self.etherscan_patch.start()

        self.filter_patch = mock.patch("scanner.scanner.InteractionFilter")
        self.mock_filter = mock.MagicMock()
        self.filter_patch.return_value = self.mock_filter

        # Mock config
        self.config_patch = mock.patch("scanner.scanner.config", {"strict_interaction_mode": True})
        self.config_patch.start()

    def tearDown(self):
        self.receipt_patch.stop()
        self.etherscan_patch.stop()
        self.filter_patch.stop()
        self.config_patch.stop()
        super().tearDown()

    def test_get_receipt_interactions_strict(self):
        """Test strict receipt-based interactions"""
        # Use checksum addresses for the mock
        target1 = Web3.to_checksum_address("0x1234567890123456789012345678901234567890")
        blacklisted = Web3.to_checksum_address("0x1F98431c8aD98523631AE4a59f267346ea31F984")
        zero_addr = Web3.to_checksum_address("0x0000000000000000000000000000000000000000")

        # Mock responses
        self.mock_etherscan.return_value = [
            target1,
            blacklisted,  # Blacklisted
            zero_addr,  # EOA
        ]

        self.mock_get_receipt.return_value = {"logs": []}
        self.mock_filter.filter_interactions.return_value = [target1]

        # Mock is_eoa and temporarily replace BLACKLIST
        with (
            mock.patch("scanner.scanner.is_eoa") as mock_is_eoa,
            mock.patch("scanner.scanner.BLACKLIST", new={blacklisted}),
        ):
            # Set up is_eoa mock
            mock_is_eoa.side_effect = lambda addr: addr == zero_addr

            result = get_receipt_interactions_strict(
                self.tx_hash, self.test_addr, interaction_filter=self.mock_filter
            )

        self.mock_etherscan.assert_called_once_with(self.tx_hash)
        self.mock_get_receipt.assert_called_once_with(self.tx_hash)
        self.mock_filter.filter_interactions.assert_called_once_with(
            [target1], self.test_addr, {"logs": []}
        )
        # Verify output correctness
        self.assertEqual(result, [target1])


class TestSimulateAndExtractIntegration(TestScannerUtils):
    def setUp(self):
        super().setUp()
        self.tx_hash = "0x1234567890abcdef"

        # Mock strict interactions function
        self.strict_patch = mock.patch("scanner.scanner.get_strict_interactions")
        self.mock_strict = self.strict_patch.start()

        # Mock config
        self.config_patch = mock.patch("scanner.scanner.config", {"strict_interaction_mode": True})
        self.config_patch.start()

    def tearDown(self):
        self.strict_patch.stop()
        self.config_patch.stop()
        super().tearDown()

    def test_simulate_and_extract_strict_mode(self):
        """Test simulate_and_extract in strict mode"""
        mock_filter = mock.MagicMock()
        self.mock_strict.return_value = ["0xStrictTarget"]

        result = simulate_and_extract(
            self.tx_hash, source_addr=self.test_addr, interaction_filter=mock_filter
        )

        self.mock_strict.assert_called_once_with(self.tx_hash, self.test_addr, None, mock_filter)
        self.assertEqual(result, ["0xStrictTarget"])

    def test_simulate_and_extract_legacy_mode(self):
        """Test simulate_and_extract in legacy mode"""
        with mock.patch("scanner.scanner.config", {"strict_interaction_mode": False}):
            with mock.patch("scanner.scanner.fetch_interactions_etherscan") as mock_etherscan:
                mock_etherscan.return_value = ["0xLegacyTarget"]

                result = simulate_and_extract(self.tx_hash)

                mock_etherscan.assert_called_once_with(self.tx_hash)
                self.assertEqual(result, ["0xLegacyTarget"])


if __name__ == "__main__":
    unittest.main()
