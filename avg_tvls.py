import argparse
import datetime
import json
import statistics
import sys
from typing import Any, Optional

import requests


def get_tvl_dataset(protocol: str, start_date: str, end_date: str, extrapolate: bool = True) -> list[dict[str, Any]]:
    """
    Fetch the complete daily TVL dataset for a given protocol between start_date and end_date.
    Missing values are linearly interpolated between available data points.
    Dates are interpreted as UTC calendar days, and API timestamps are converted in UTC.
    
    For dates at the beginning or end of the range where data exists only on one side:
    - If extrapolate=True (default): Uses linear extrapolation based on the two nearest 
      data points on that side to estimate the TVL value.
    - If extrapolate=False: Skips these dates, returning only dates that can be 
      interpolated between two surrounding data points.

    Parameters:
    - protocol (str): The protocol name (as listed on DeFiLlama).
    - start_date (str): Start date in YYYY-MM-DD format (UTC).
    - end_date (str): End date in YYYY-MM-DD format (UTC).
    - extrapolate (bool): Whether to extrapolate values at start/end. Default: True.

    Returns:
    - List of dictionaries with keys: 'date' (str), 'tvl' (float), 'is_interpolated' (bool)
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
        datetime.datetime.fromtimestamp(entry["date"], tz=datetime.timezone.utc).date(): entry[
            "totalLiquidityUSD"
        ]
        for entry in tvl_data
    }

    # Get sorted list of all available dates (for interpolation, we need dates outside range too)
    all_available_dates = sorted(tvl_map.keys())

    # Get dates within the range to check if we have any data
    available_dates_in_range = [d for d in all_available_dates if start_dt <= d <= end_dt]

    if not available_dates_in_range:
        raise ValueError(f"No TVL data available between {start_date} and {end_date}")

    # Build the result dataset with interpolation
    result = []
    current_date = start_dt

    while current_date <= end_dt:
        if current_date in tvl_map:
            # Raw data exists
            result.append(
                {
                    "date": current_date.isoformat(),
                    "tvl": tvl_map[current_date],
                    "is_interpolated": False,
                }
            )
        else:
            # Need to interpolate, extrapolate, or skip
            prev_date, next_date = _find_nearest_dates(current_date, all_available_dates)

            if prev_date is not None and next_date is not None:
                # Linear interpolation between two points
                prev_tvl = tvl_map[prev_date]
                next_tvl = tvl_map[next_date]

                # Calculate days between points
                days_between = (next_date - prev_date).days
                days_from_prev = (current_date - prev_date).days

                # Linear interpolation
                interpolated_tvl = prev_tvl + (next_tvl - prev_tvl) * (
                    days_from_prev / days_between
                )

                result.append(
                    {
                        "date": current_date.isoformat(),
                        "tvl": interpolated_tvl,
                        "is_interpolated": True,
                    }
                )
            elif not extrapolate:
                # No extrapolation: skip dates that can't be interpolated between two points
                pass
            elif prev_date is not None:
                # Only previous data exists - extrapolate forward using trend from two most recent points
                # Find the two most recent data points before or at current_date
                dates_before = [d for d in all_available_dates if d <= current_date or d == prev_date]
                if len(dates_before) >= 2:
                    # Use the two most recent points to calculate slope
                    date1 = dates_before[-2]
                    date2 = dates_before[-1]
                    tvl1 = tvl_map[date1]
                    tvl2 = tvl_map[date2]
                    slope = _get_extrapolation_slope(date1, tvl1, date2, tvl2)
                    
                    # Extrapolate from the most recent point
                    days_diff = (current_date - date2).days
                    extrapolated_tvl = tvl2 + slope * days_diff
                    
                    result.append(
                        {
                            "date": current_date.isoformat(),
                            "tvl": extrapolated_tvl,
                            "is_interpolated": True,
                        }
                    )
                else:
                    # Only one data point available, use it directly (fallback)
                    result.append(
                        {
                            "date": current_date.isoformat(),
                            "tvl": tvl_map[prev_date],
                            "is_interpolated": True,
                        }
                    )
            elif next_date is not None:
                # Only future data exists - extrapolate backward using trend from two earliest points
                # Find the two earliest data points after or at current_date
                dates_after = [d for d in all_available_dates if d >= current_date or d == next_date]
                if len(dates_after) >= 2:
                    # Use the two earliest points to calculate slope
                    date1 = dates_after[0]
                    date2 = dates_after[1]
                    tvl1 = tvl_map[date1]
                    tvl2 = tvl_map[date2]
                    slope = _get_extrapolation_slope(date1, tvl1, date2, tvl2)
                    
                    # Extrapolate backward from the earliest point
                    days_diff = (current_date - date1).days  # This will be negative
                    extrapolated_tvl = tvl1 + slope * days_diff
                    
                    result.append(
                        {
                            "date": current_date.isoformat(),
                            "tvl": extrapolated_tvl,
                            "is_interpolated": True,
                        }
                    )
                else:
                    # Only one data point available, use it directly (fallback)
                    result.append(
                        {
                            "date": current_date.isoformat(),
                            "tvl": tvl_map[next_date],
                            "is_interpolated": True,
                        }
                    )
            else:
                # No data available at all (shouldn't happen if we have data in range)
                if extrapolate:
                    result.append(
                        {"date": current_date.isoformat(), "tvl": 0.0, "is_interpolated": True}
                    )

        current_date += datetime.timedelta(days=1)

    return result


def _find_nearest_dates(
    target_date: datetime.date, available_dates: list[datetime.date]
) -> tuple[Optional[datetime.date], Optional[datetime.date]]:
    """
    Find the nearest previous and next available dates for interpolation.
    Returns (prev_date, next_date) tuple. Either can be None if not found.
    """
    prev_date = None
    next_date = None

    # Find previous date (before or equal to target)
    for date in reversed(available_dates):
        if date <= target_date:
            prev_date = date
            break

    # Find next date (after target)
    for date in available_dates:
        if date > target_date:
            next_date = date
            break

    return (prev_date, next_date)


def _get_extrapolation_slope(
    date1: datetime.date, tvl1: float, date2: datetime.date, tvl2: float
) -> float:
    """
    Calculate the slope (TVL change per day) between two data points.
    
    Parameters:
    - date1, date2: Two dates with known TVL values
    - tvl1, tvl2: The TVL values at those dates
    
    Returns:
    - Slope as TVL change per day
    """
    days_between = (date2 - date1).days
    if days_between == 0:
        return 0.0
    return (tvl2 - tvl1) / days_between


def get_average_tvl(protocol: str, start_date: str, end_date: str, extrapolate: bool = True) -> float:
    """
    Fetch and average the daily TVL for a given protocol between start_date and end_date.

    Parameters:
    - protocol (str): The protocol name (as listed on DeFiLlama).
    - start_date (str): Start date in YYYY-MM-DD format (UTC).
    - end_date (str): End date in YYYY-MM-DD format (UTC).
    - extrapolate (bool): Whether to extrapolate values at start/end. Default: True.

    Returns:
    - The average TVL over the given period.
    """
    dataset = get_tvl_dataset(protocol, start_date, end_date, extrapolate)
    tvls = [row["tvl"] for row in dataset]
    return statistics.mean(tvls)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Calculate TVL data for a DeFi protocol.")
    parser.add_argument(
        "protocol", type=str, help="The DeFi protocol name (as listed on DeFiLlama)."
    )
    parser.add_argument("start_date", type=str, help="Start date in YYYY-MM-DD format (UTC).")
    parser.add_argument("end_date", type=str, help="End date in YYYY-MM-DD format (UTC).")
    parser.add_argument(
        "--format",
        choices=["csv", "json"],
        default="csv",
        help="Output format: csv (default) or json",
    )
    parser.add_argument(
        "--mean",
        action="store_true",
        help="Output only the average TVL (backward compatibility mode)",
    )
    parser.add_argument(
        "--no-extrapolate",
        action="store_true",
        help="Disable extrapolation at start/end dates. When disabled, only dates that can be "
        "interpolated between two data points are included. By default, extrapolation is enabled "
        "and uses linear extrapolation based on the two nearest data points to estimate values "
        "at the beginning or end of the date range where data exists only on one side.",
    )
    args = parser.parse_args()

    try:
        if args.mean:
            # Backward compatibility: output only the mean
            avg_tvl = get_average_tvl(args.protocol, args.start_date, args.end_date, extrapolate=not args.no_extrapolate)
            print(
                f"Average TVL for {args.protocol} from {args.start_date} to {args.end_date}: ${avg_tvl:,.2f}"
            )
        else:
            # Output full dataset
            dataset = get_tvl_dataset(args.protocol, args.start_date, args.end_date, extrapolate=not args.no_extrapolate)

            if args.format == "json":
                # JSON output
                output = json.dumps(dataset, indent=2)
                print(output)
            else:
                # CSV output (default)
                print("date,tvl,is_interpolated")
                for row in dataset:
                    print(f"{row['date']},{row['tvl']:.2f},{str(row['is_interpolated']).lower()}")

    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
