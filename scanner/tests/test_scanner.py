import sys
import os
import unittest
from unittest import TestCase, mock
from web3 import Web3
from scanner import processed_deployers
import networkx as nx



from scanner import (
    short_addr,
    display_label,
    is_eoa,
    fetch_contract_name,
    fetch_recent_transactions,
    get_contract_creator,
    get_contracts_deployed_by,
    annotate_and_add_contract,
    deployer_discovery_pass,
    simulate_and_extract,
    contract_name_cache,
    APIRateLimiter
)


class TestScannerUtils(TestCase):
    def setUp(self):
        self.test_addr = "0x14Bdc3A3AE09f5518b923b69489CBcAfB238e617"
        self.checksum_addr = Web3.to_checksum_address(self.test_addr)
        self.blacklist = {"0x1F98431c8aD98523631AE4a59f267346ea31F984"}

class TestEOACheck(TestScannerUtils):
    @mock.patch('scanner.w3.eth.get_code')
    def test_is_eoa(self, mock_get_code):
        # empty code
        mock_get_code.return_value = b''
        self.assertTrue(is_eoa(self.test_addr))
        
        # non empty code
        mock_get_code.return_value = b'0x123'
        self.assertFalse(is_eoa(self.test_addr))
        
        # blacklisted
        self.assertFalse(is_eoa("0x1F98431c8aD98523631AE4a59f267346ea31F984"))

class TestEtherscanAPI(TestScannerUtils):
    def setUp(self):
        super().setUp()
        contract_name_cache.clear()

        self.mock_get_patcher = mock.patch('requests.get')
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
            "result": ""
        }
        name = fetch_contract_name(self.test_addr)
        expected = short_addr(Web3.to_checksum_address(self.test_addr))
        self.assertEqual(name, expected)

    def test_fetch_contract_name_empty_response(self):
        self.mock_get.return_value.json.return_value = {
            "status": "1",
            "message": "OK",
            "result": []
        }
        name = fetch_contract_name(self.test_addr)
        expected = short_addr(Web3.to_checksum_address(self.test_addr))
        self.assertEqual(name, expected)
    
    def test_get_contract_creator(self):
        CONTRACT_CREATION = {
            'status': '1',
            'message': 'OK',
            'result': [{
                'contractAddress': '0x14bdc3a3ae09f5518b923b69489cbcafb238e617',
                'contractCreator': '0xeba675f1d0fe4c00e179c1f224b8b18dd476e76a',
                'txHash': '0xeb41d87f9f1c5c871f9eecd2676387e661bc984bbbb5153230f714e5943d9fc6',
                'blockNumber': '22472324',
                'timestamp': '1747115327',
                'contractFactory': '0x35a338522a435d46f77be32c70e215b813d0e3ac',
                'creationBytecode': '0x61010060...'
            }]
        }
        self.mock_get.return_value.json.return_value = CONTRACT_CREATION

        creator = get_contract_creator(self.test_addr)
        
        expected = Web3.to_checksum_address('0xeba675f1d0fe4c00e179c1f224b8b18dd476e76a')
        self.assertEqual(creator, expected)

        self.mock_get.assert_called_once_with(
            "https://api.etherscan.io/api",
            params={
                "module": "contract",
                "action": "getcontractcreation",
                "contractaddresses": self.checksum_addr,
                "apikey": mock.ANY
            }
        )

    def test_fetch_recent_transactions(self):
        mock_tx_hashes = [
            '0x7e1184333dcf5eaf94ada8ef085ed14eefaa4ac17210ae0f2f7f60f2440800e8',
            '0xac8b350293361c8e04876670ca6bf92a32fd8867e2b59d02eb27dbc6bb660b85',
            '0x60a4f8d1130cc4f9868ce486d1c06cc2d80441bedb4fe56b264f791976ef021b'
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
                    "value": "0"
                } for tx_hash in mock_tx_hashes
            ]
        }
        
        txs = fetch_recent_transactions(self.test_addr, limit=3)
        
        self.mock_get.assert_called_once()
        self.assertEqual(len(txs), 3)
        self.assertEqual(txs, mock_tx_hashes)
        
        self.assertEqual(txs[0], '0x7e1184333dcf5eaf94ada8ef085ed14eefaa4ac17210ae0f2f7f60f2440800e8')
        self.assertEqual(txs[-1], '0x60a4f8d1130cc4f9868ce486d1c06cc2d80441bedb4fe56b264f791976ef021b')

class TestSimulateAndExtract(TestScannerUtils):
    def setUp(self):
        super().setUp()
        self.tx_hash = "0x1234567890abcdef"

        self.mock_w3 = mock.MagicMock()
        self.w3_patch = mock.patch('scanner.w3', new=self.mock_w3)
        self.w3_patch.start()

        self.mock_w3.eth.get_code.return_value = b'0x123'
        
        self.requests_patch = mock.patch('scanner.requests.post')
        self.mock_post = self.requests_patch.start()
        self.limiter_patch = mock.patch('scanner.limiter.wait')
        self.mock_limiter = self.limiter_patch.start()
        self.etherscan_patch = mock.patch('scanner.fetch_interactions_etherscan')
        self.mock_etherscan = self.etherscan_patch.start()

    def tearDown(self):
        self.w3_patch.stop()
        self.requests_patch.stop()
        self.limiter_patch.stop()
        self.etherscan_patch.stop()
        super().tearDown()

    def test_tenderly_success(self):
        self.mock_post.return_value.json.return_value = {
            "result": {
                "trace": [{"to": "0x1111111111111111111111111111111111111111"}],
                "logs": [{"address": "0x2222222222222222222222222222222222222222"}],
                "stateChanges": [{"address": "0x3333333333333333333333333333333333333333"}]
            }
        }
        
        def get_code_side_effect(addr):
            addr = addr.lower() if addr else addr
            if addr == "0x1111111111111111111111111111111111111111":
                return b'0x123'
            elif addr == "0x2222222222222222222222222222222222222222":
                return b'0x123'
            elif addr == "0x3333333333333333333333333333333333333333":
                return b'0x123'
            return b''
            
        self.mock_w3.eth.get_code.side_effect = get_code_side_effect
        
        result = simulate_and_extract(self.tx_hash)
        
        self.assertEqual(len(result), 3)
        self.assertIn("0x1111111111111111111111111111111111111111", result)
        self.assertIn("0x2222222222222222222222222222222222222222", result)
        self.assertIn("0x3333333333333333333333333333333333333333", result)

class TestDeployerDiscovery(TestScannerUtils):
    def setUp(self):
        super().setUp()
        self.deployer_addr = Web3.to_checksum_address("0xdedd000000000000000000000000000000000001")
        self.sibling1 = Web3.to_checksum_address("0xabcd000000000000000000000000000000000001")
        self.sibling2 = Web3.to_checksum_address("0xabcd000000000000000000000000000000000002")
        
        self.mock_get_patcher = mock.patch('scanner.requests.get')
        self.mock_get = self.mock_get_patcher.start()
        
        self.mock_w3 = mock.MagicMock()
        self.w3_patch = mock.patch('scanner.w3', new=self.mock_w3)
        self.w3_patch.start()
        
        self.mock_w3.eth.get_code.return_value = b'0x123'

    def tearDown(self):
        self.mock_get_patcher.stop()
        self.w3_patch.stop()
        super().tearDown()

    def test_get_contracts_deployed_by(self):
        blacklist_addr = Web3.to_checksum_address(list(self.blacklist)[0])
        self.mock_get.return_value.json.return_value = {
            "status": "1",
            "result": [
                {"to": "", "contractAddress": self.sibling1},
                {"to": "", "contractAddress": self.sibling2}, 
                {"to": "0x0000000000000000000000000000000000000000", "contractAddress": ""}, 
                {"to": "", "contractAddress": blacklist_addr} 
            ]
        }

        with mock.patch('scanner.is_eoa') as mock_is_eoa:
            blacklist_lower = blacklist_addr.lower()
            mock_is_eoa.side_effect = lambda addr: addr == "" or addr.lower() == blacklist_lower
            contracts = get_contracts_deployed_by(self.deployer_addr)
        
        for contract in contracts:
            print(f"Contract Address: {contract}")

        self.assertEqual(len(contracts), 2)
        self.assertIn(self.sibling1, contracts)
        self.assertIn(self.sibling2, contracts)
        self.assertNotIn(blacklist_addr, contracts)

    def test_deployer_discovery_pass(self):
        self.mock_get.return_value.json.side_effect = [
            {  # get_contract_creator response
                "result": [{
                    "contractCreator": self.deployer_addr,
                    "contractAddress": self.test_addr
                }]
            },
            {  # get_contracts_deployed_by response
                "result": [
                    {"to": "", "contractAddress": self.sibling1},
                    {"to": "", "contractAddress": self.sibling2}
                ]
            }
        ]

        test_graph = nx.DiGraph()
        discovered = set()
        untraced = set()
        
        new_contracts = deployer_discovery_pass(
            contracts_to_check=[self.test_addr],
            blacklist=self.blacklist,
            contract_graph=test_graph,
            discovered_contracts=discovered,
            untraced_contracts=untraced,
            label="test"
        )

        self.assertEqual(len(new_contracts), 2)
        self.assertEqual(len(discovered), 2)
        self.assertIn(self.sibling1, discovered)
        self.assertIn(self.sibling2, discovered)

        self.assertEqual(test_graph.number_of_nodes(), 3) 
        self.assertEqual(test_graph.number_of_edges(), 2) 
        self.assertEqual(
            test_graph.nodes[self.sibling1]["discovery_method"],
            "test"
        )


if __name__ == '__main__':
    unittest.main()