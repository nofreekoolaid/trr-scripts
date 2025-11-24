import logging
from abc import ABC, abstractmethod

import requests
from web3 import Web3


class TraceProvider(ABC):
    @abstractmethod
    def get_transaction_trace(self, tx_hash: str) -> dict:
        """Get execution trace for transaction"""
        pass

    @abstractmethod
    def extract_direct_calls(
        self, trace: dict, source_addr: str, allowed_call_types: set[str] = None
    ) -> set[str]:
        """Extract addresses where source made direct calls"""
        pass


class TenderlyTraceProvider(TraceProvider):
    def __init__(self, rpc_url: str):
        self.rpc_url = rpc_url

    def get_transaction_trace(self, tx_hash: str) -> dict:
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "debug_traceTransaction",
            "params": [tx_hash, {"tracer": "callTracer", "timeout": "30s"}],
        }

        try:
            response = requests.post(
                self.rpc_url, headers={"Content-Type": "application/json"}, json=payload, timeout=60
            )
            response.raise_for_status()
            result = response.json()

            if "error" in result:
                logging.warning(f"Tenderly trace error: {result['error']}")
                return {}

            return result.get("result", {})
        except Exception as e:
            logging.warning(f"Tenderly trace failed: {str(e)}")
            return {}

    def extract_direct_calls(
        self, trace: dict, source_addr: str, allowed_call_types: set[str] = None
    ) -> set[str]:
        # Default for now
        if allowed_call_types is None:
            allowed_call_types = {"CALL", "DELEGATECALL", "STATICCALL"}

        calls = set()
        source_checksum = Web3.to_checksum_address(source_addr)

        def _extract_from_node(node, caller=None):
            if not isinstance(node, dict):
                return

            call_type = node.get("type", "CALL")  # Default to CALL if missing

            # Check if this call was made by source contract
            current_caller = (
                Web3.to_checksum_address(node.get("from", "")) if node.get("from") else None
            )
            current_to = Web3.to_checksum_address(node.get("to", "")) if node.get("to") else None

            # If so add the target
            if current_caller == source_checksum and current_to and call_type in allowed_call_types:
                calls.add(current_to)

            # Recursively process nested calls
            if "calls" in node and isinstance(node["calls"], list):
                for call in node["calls"]:
                    _extract_from_node(call, current_caller or caller)

        if trace:
            _extract_from_node(trace)

        return calls


class GethTraceProvider(TraceProvider):
    def __init__(self, rpc_url: str):
        self.rpc_url = rpc_url

    def get_transaction_trace(self, tx_hash: str) -> dict:
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "debug_traceTransaction",
            "params": [tx_hash, {"tracer": "callTracer", "timeout": "30s"}],
        }

        try:
            response = requests.post(
                self.rpc_url, headers={"Content-Type": "application/json"}, json=payload, timeout=60
            )
            response.raise_for_status()
            result = response.json()
            return result.get("result", {})
        except Exception as e:
            logging.warning(f"Geth trace failed: {str(e)}")
            return {}

    def extract_direct_calls(
        self, trace: dict, source_addr: str, allowed_call_types: set[str] = None
    ) -> set[str]:
        # Same implementation as Tenderly
        return TenderlyTraceProvider.extract_direct_calls(
            self, trace, source_addr, allowed_call_types
        )


class ErigonTraceProvider(TraceProvider):
    def __init__(self, rpc_url: str):
        self.rpc_url = rpc_url

    def get_transaction_trace(self, tx_hash: str) -> dict:
        # trace_replayTransaction instead of debug_traceTransaction
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "trace_replayTransaction",
            "params": [tx_hash, ["trace"]],
        }

        try:
            response = requests.post(
                self.rpc_url, headers={"Content-Type": "application/json"}, json=payload, timeout=60
            )
            response.raise_for_status()
            result = response.json()

            # DEBUG LOGGING
            logging.debug(f"Erigon trace result keys: {list(result.keys()) if result else 'None'}")
            if result and "result" in result and "trace" in result["result"]:
                sample_entry = result["result"]["trace"][0] if result["result"]["trace"] else {}
                logging.debug(f"First trace entry keys: {list(sample_entry.keys())}")
                if "action" in sample_entry:
                    logging.debug(f"Action keys: {list(sample_entry['action'].keys())}")

            return result.get("result", {})
        except Exception as e:
            logging.warning(f"Erigon trace failed: {str(e)}")
            return {}

    def extract_direct_calls(
        self, trace: dict, source_addr: str, allowed_call_types: set[str] = None
    ) -> set[str]:
        calls = set()
        source_checksum = Web3.to_checksum_address(source_addr)

        if allowed_call_types is None:
            allowed_call_types = {"CALL", "DELEGATECALL", "STATICCALL"}

        if trace and "trace" in trace:
            for trace_entry in trace["trace"]:
                action = trace_entry.get("action", {})
                trace_address = trace_entry.get("traceAddress", [])

                if len(trace_address) > 0:
                    continue

                call_type = action.get("callType", "call").lower()
                from_address = action.get("from", "")
                to_address = action.get("to", "")

                try:
                    from_checksum = Web3.to_checksum_address(from_address)
                    to_checksum = Web3.to_checksum_address(to_address) if to_address else None
                except Exception:
                    continue

                if (
                    from_checksum == source_checksum
                    and to_checksum
                    and call_type in allowed_call_types
                ):
                    calls.add(to_checksum)

        return calls


def get_trace_provider(provider_name: str, rpc_url: str) -> TraceProvider:
    """Factory function to get trace provider by name"""
    providers = {
        "tenderly": TenderlyTraceProvider,
        "geth": GethTraceProvider,
        "erigon": ErigonTraceProvider,
    }

    provider_class = providers.get(provider_name.lower())
    if provider_class:
        return provider_class(rpc_url)

    raise ValueError(f"Unknown trace provider: {provider_name}")
