import logging

from web3 import Web3


class InteractionFilter:
    def __init__(self, config: dict):
        self.config = config
        self.protocol_factories = set()
        self.allowed_event_signatures = set()
        self.allowed_call_types = set(
            config.get("allowed_call_types", ["CALL", "DELEGATECALL", "STATICCALL"])
        )

        # Initialize config
        self._load_config()

    def get_allowed_call_types(self) -> set[str]:
        return self.allowed_call_types

    def get_max_call_depth(self) -> int:
        return self.max_call_depth

    def _load_config(self):
        """Load filtering configuration from config"""
        # Protocol factory addresses
        factory_addresses = self.config.get("protocol_factory_addresses", [])
        for addr in factory_addresses:
            try:
                self.protocol_factories.add(Web3.to_checksum_address(addr))
            except Exception:
                logging.warning(f"Invalid factory address in config: {addr}")

        # Allowed event signatures
        event_signatures = self.config.get("allowed_event_signatures", [])
        self.allowed_event_signatures = set(event_signatures)

    def is_protocol_factory(self, address: str) -> bool:
        """Check if address is a known protocol factory"""
        try:
            checksum_addr = Web3.to_checksum_address(address)
            return checksum_addr in self.protocol_factories
        except Exception:
            return False

    def has_allowed_event_signature(self, event_data: dict) -> bool:
        """Check if event matches allowed signatures"""
        if not event_data or not self.allowed_event_signatures:
            return False

        topics = event_data.get("topics", [])
        if topics and len(topics) > 0:
            event_signature = topics[0]
            return event_signature in self.allowed_event_signatures

        return False

    def filter_interactions(
        self, interactions: list[str], source_addr: str, tx_data: dict = None
    ) -> list[str]:
        """Apply filtering to interactions"""
        if not self.config.get("strict_interaction_mode", False):
            return interactions

        filtered = []
        source_checksum = Web3.to_checksum_address(source_addr)
        zero_address = Web3.to_checksum_address("0x0000000000000000000000000000000000000000")

        # Get blacklist from config
        blacklist = {
            Web3.to_checksum_address(addr) for addr in self.config.get("blacklist_contracts", [])
        }

        for addr in interactions:
            try:
                checksum_addr = Web3.to_checksum_address(addr)

                # Skip zero address
                if checksum_addr == zero_address:
                    continue

                # Skip blacklisted addresses
                if checksum_addr in blacklist:
                    continue

                # Allow interactions with known protocol factories
                if self.is_protocol_factory(checksum_addr):
                    filtered.append(checksum_addr)
                    continue

                # Non-factory interactions
                if self._should_keep_interaction(checksum_addr, source_checksum, tx_data):
                    filtered.append(checksum_addr)

            except Exception as e:
                logging.debug(f"Error filtering address {addr}: {e}")
                continue

        return filtered

    def _should_keep_interaction(self, target_addr: str, source_addr: str, tx_data: dict) -> bool:
        """Determine if an interaction should be kept"""

        # Rule 1: Keep if source is a known factory
        if self.is_protocol_factory(source_addr):
            return True

        # Rule 2: Keep if target is a known factory
        if self.is_protocol_factory(target_addr):
            return True

        # Rule 3: Check for allowed events (from config, if tx_data contains receipt info)
        if tx_data and "logs" in tx_data:
            for log in tx_data["logs"]:
                if Web3.to_checksum_address(
                    log.get("address", "")
                ) == target_addr and self.has_allowed_event_signature(log):
                    return True

        # Default: filter out
        return False
