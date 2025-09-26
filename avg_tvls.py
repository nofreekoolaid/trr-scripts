import requests
import datetime
import statistics
import argparse

def get_average_tvl(protocol: str, start_date: str, end_date: str):
    """
    Fetch and average the daily TVL for a given protocol between start_date and end_date.
    Days without TVL data (e.g., before launch) are treated as TVL = 0.
    Dates are interpreted as UTC calendar days, and API timestamps are converted in UTC.

    Parameters:
    - protocol (str): The protocol name (as listed on DeFiLlama).
    - start_date (str): Start date in YYYY-MM-DD format (UTC).
    - end_date (str): End date in YYYY-MM-DD format (UTC).

    Returns:
    - The average TVL over the given period.
    """
    # Convert input dates to date objects
    start_dt = datetime.datetime.strptime(start_date, "%Y-%m-%d").date()
    end_dt = datetime.datetime.strptime(end_date, "%Y-%m-%d").date()

    # Fetch historical TVL data from DeFiLlama
    url = f"https://api.llama.fi/protocol/{protocol}"
    response = requests.get(url)

    if response.status_code != 200:
        raise ValueError(f"Error fetching data: {response.status_code}")

    data = response.json()
    tvl_data = data.get("tvl", [])

    if not tvl_data:
        raise ValueError(f"No TVL data found for protocol {protocol}")

    # Build a map of date -> TVL (convert UNIX seconds to a UTC date to avoid local-TZ skew)
    tvl_map = {
        datetime.datetime.fromtimestamp(entry["date"], tz=datetime.timezone.utc).date(): entry["totalLiquidityUSD"]
        for entry in tvl_data
    }

    # Iterate over all dates in range and collect TVL values (default to 0 if missing)
    current_date = start_dt
    tvls = []
    while current_date <= end_dt:
        tvls.append(tvl_map.get(current_date, 0.0))
        current_date += datetime.timedelta(days=1)

    # Handle case where no data exists in the whole range
    if not tvls:
        raise ValueError(f"No TVL data available between {start_date} and {end_date}")

    return statistics.mean(tvls)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Calculate average TVL for a DeFi protocol.")
    parser.add_argument("protocol", type=str, help="The DeFi protocol name (as listed on DeFiLlama).")
    parser.add_argument("start_date", type=str, help="Start date in YYYY-MM-DD format (UTC).")
    parser.add_argument("end_date", type=str, help="End date in YYYY-MM-DD format (UTC).")
    args = parser.parse_args()

    try:
        avg_tvl = get_average_tvl(args.protocol, args.start_date, args.end_date)
        print(f"Average TVL for {args.protocol} from {args.start_date} to {args.end_date}: ${avg_tvl:,.2f}")
    except ValueError as e:
        print(f"Error: {e}")
