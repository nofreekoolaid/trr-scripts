import requests
import datetime
import statistics
import argparse

def get_average_tvl(protocol: str, start_date: str, end_date: str):
    """
    Fetches and averages the daily TVL for a given protocol between start_date and end_date.

    Parameters:
    - protocol (str): The protocol name (as listed on DeFiLlama).
    - start_date (str): Start date in YYYY-MM-DD format.
    - end_date (str): End date in YYYY-MM-DD format.

    Returns:
    - The average TVL over the given period.
    """
    # Convert input dates to timestamps
    start_timestamp = int(datetime.datetime.strptime(start_date, "%Y-%m-%d").timestamp())
    end_timestamp = int(datetime.datetime.strptime(end_date, "%Y-%m-%d").timestamp())

    # Fetch historical TVL data from DeFiLlama
    url = f"https://api.llama.fi/protocol/{protocol}"
    response = requests.get(url)

    if response.status_code != 200:
        raise ValueError(f"Error fetching data: {response.status_code}")

    data = response.json()

    # Extract TVL data (sorted by timestamp)
    tvl_data = data.get("tvl", [])

    if not tvl_data:
        raise ValueError(f"No TVL data found for protocol {protocol}")

    # Filter TVL data for the date range
    filtered_tvl = [
        entry["totalLiquidityUSD"]
        for entry in tvl_data
        if start_timestamp <= entry["date"] <= end_timestamp
    ]

    if not filtered_tvl:
        raise ValueError(f"No TVL data available between {start_date} and {end_date}")

    # Compute and return the average TVL
    avg_tvl = statistics.mean(filtered_tvl)
    return avg_tvl

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Calculate average TVL for a DeFi protocol.")
    parser.add_argument("protocol", type=str, help="The DeFi protocol name (as listed on DeFiLlama).")
    parser.add_argument("start_date", type=str, help="Start date in YYYY-MM-DD format.")
    parser.add_argument("end_date", type=str, help="End date in YYYY-MM-DD format.")
    args = parser.parse_args()

    try:
        avg_tvl = get_average_tvl(args.protocol, args.start_date, args.end_date)
        print(f"Average TVL for {args.protocol} from {args.start_date} to {args.end_date}: ${avg_tvl:,.2f}")
    except ValueError as e:
        print(f"Error: {e}")
