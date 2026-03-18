"""
Broker factory – instantiates the right broker based on BROKER_TYPE env var.

BROKER_TYPE values:
  "sim"  (default) – simulated paper trading
  "ibkr"           – Interactive Brokers (requires IB Gateway/TWS)

Add new brokers by:
  1. Create broker_xxx.py implementing Broker + DataProvider
  2. Add a case here
"""

import os

from broker import Broker, DataProvider

BROKER_TYPE = os.getenv("BROKER_TYPE", "sim")


def create_data_provider() -> DataProvider:
    if BROKER_TYPE == "ibkr":
        from broker_ibkr import IBKRDataProvider

        return IBKRDataProvider()
    else:
        from broker_sim import SimulatedDataProvider

        return SimulatedDataProvider()


def create_broker(data_provider: DataProvider = None) -> Broker:
    if BROKER_TYPE == "ibkr":
        from broker_ibkr import IBKRBroker, IBKRDataProvider

        if data_provider is None:
            data_provider = IBKRDataProvider()
        return IBKRBroker(data_provider)
    else:
        from broker_sim import AsyncSimulatedBroker

        return AsyncSimulatedBroker(data_provider=data_provider)
