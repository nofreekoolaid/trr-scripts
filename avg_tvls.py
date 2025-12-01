import argparse
import datetime
import json
import statistics
import sys
from typing import Any, Optional

import requests


def get_tvl_dataset(protocol: str, start_date: str, end_date: str, extrapolate: bool = False, by_chain: bool = True) -> list[dict[str, Any]]:
    """
    Fetch the complete daily TVL dataset for a given protocol between start_date and end_date.
    Missing values are linearly interpolated between available data points.
    Dates are interpreted as UTC calendar days, and API timestamps are converted in UTC.
    
    For dates at the beginning or end of the range where data exists only on one side:
    - If extrapolate=False (default): Returns None for tvl_interpolated on these dates,
      indicating no reliable value can be computed. All dates in the range are still included.
    - If extrapolate=True: Uses linear extrapolation based on the two nearest 
      data points on that side to estimate the TVL value.

    Parameters:
    - protocol (str): The protocol name (as listed on DeFiLlama).
    - start_date (str): Start date in YYYY-MM-DD format (UTC).
    - end_date (str): End date in YYYY-MM-DD format (UTC).
    - extrapolate (bool): Whether to extrapolate values at start/end. Default: False.
    - by_chain (bool): Whether to break down TVL by chain. Default: True.

    Returns:
    - If by_chain=False: List of dictionaries with keys:
      - 'date' (str): The date in YYYY-MM-DD format
      - 'tvl_raw' (float|None): The actual raw data point, or None if no data exists for this date
      - 'tvl_interpolated' (float|None): The interpolated/extrapolated value, equals tvl_raw when
        raw data exists, computed value when interpolated, or None when cannot be computed
    - If by_chain=True: List of dictionaries with keys:
      - 'date' (str): The date in YYYY-MM-DD format
      - '{chain}_raw' (float|None): Raw TVL for each chain
      - '{chain}_interpolated' (float|None): Interpolated TVL for each chain
      - 'total_raw' (float|None): Sum of all chain raw values
      - 'total_interpolated' (float|None): Sum of all chain interpolated values
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

    if by_chain:
        return _get_tvl_dataset_by_chain(data, start_dt, end_dt, extrapolate)

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
            raw_tvl = tvl_map[current_date]
            result.append(
                {
                    "date": current_date.isoformat(),
                    "tvl_raw": raw_tvl,
                    "tvl_interpolated": raw_tvl,  # When raw exists, interpolated equals raw
                }
            )
        else:
            # Need to interpolate, extrapolate, or return None
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
                        "tvl_raw": None,
                        "tvl_interpolated": interpolated_tvl,
                    }
                )
            elif not extrapolate:
                # No extrapolation: include date with None values
                result.append(
                    {
                        "date": current_date.isoformat(),
                        "tvl_raw": None,
                        "tvl_interpolated": None,
                    }
                )
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
                            "tvl_raw": None,
                            "tvl_interpolated": extrapolated_tvl,
                        }
                    )
                else:
                    # Only one data point available, use it directly (fallback)
                    result.append(
                        {
                            "date": current_date.isoformat(),
                            "tvl_raw": None,
                            "tvl_interpolated": tvl_map[prev_date],
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
                            "tvl_raw": None,
                            "tvl_interpolated": extrapolated_tvl,
                        }
                    )
                else:
                    # Only one data point available, use it directly (fallback)
                    result.append(
                        {
                            "date": current_date.isoformat(),
                            "tvl_raw": None,
                            "tvl_interpolated": tvl_map[next_date],
                        }
                    )
            else:
                # No data available at all (shouldn't happen if we have data in range)
                if extrapolate:
                    result.append(
                        {"date": current_date.isoformat(), "tvl_raw": None, "tvl_interpolated": 0.0}
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


def _process_tvl_series(
    tvl_map: dict[datetime.date, float],
    current_date: datetime.date,
    all_available_dates: list[datetime.date],
    extrapolate: bool,
) -> tuple[Optional[float], Optional[float]]:
    """
    Process a single date for a TVL series, returning (raw, interpolated) values.
    
    Parameters:
    - tvl_map: Mapping of dates to TVL values
    - current_date: The date to process
    - all_available_dates: Sorted list of all dates with data
    - extrapolate: Whether to extrapolate at edges
    
    Returns:
    - Tuple of (tvl_raw, tvl_interpolated)
    """
    if current_date in tvl_map:
        raw_tvl = tvl_map[current_date]
        return (raw_tvl, raw_tvl)
    
    prev_date, next_date = _find_nearest_dates(current_date, all_available_dates)
    
    if prev_date is not None and next_date is not None:
        # Linear interpolation between two points
        prev_tvl = tvl_map[prev_date]
        next_tvl = tvl_map[next_date]
        days_between = (next_date - prev_date).days
        days_from_prev = (current_date - prev_date).days
        interpolated_tvl = prev_tvl + (next_tvl - prev_tvl) * (days_from_prev / days_between)
        return (None, interpolated_tvl)
    
    if not extrapolate:
        return (None, None)
    
    if prev_date is not None:
        # Forward extrapolation
        dates_before = [d for d in all_available_dates if d <= current_date or d == prev_date]
        if len(dates_before) >= 2:
            date1, date2 = dates_before[-2], dates_before[-1]
            slope = _get_extrapolation_slope(date1, tvl_map[date1], date2, tvl_map[date2])
            days_diff = (current_date - date2).days
            return (None, tvl_map[date2] + slope * days_diff)
        else:
            return (None, tvl_map[prev_date])
    
    if next_date is not None:
        # Backward extrapolation
        dates_after = [d for d in all_available_dates if d >= current_date or d == next_date]
        if len(dates_after) >= 2:
            date1, date2 = dates_after[0], dates_after[1]
            slope = _get_extrapolation_slope(date1, tvl_map[date1], date2, tvl_map[date2])
            days_diff = (current_date - date1).days
            return (None, tvl_map[date1] + slope * days_diff)
        else:
            return (None, tvl_map[next_date])
    
    return (None, 0.0 if extrapolate else None)


def _get_tvl_dataset_by_chain(
    data: dict[str, Any],
    start_dt: datetime.date,
    end_dt: datetime.date,
    extrapolate: bool,
) -> list[dict[str, Any]]:
    """
    Process TVL data broken down by chain.
    
    Parameters:
    - data: The full API response from DeFiLlama
    - start_dt: Start date
    - end_dt: End date
    - extrapolate: Whether to extrapolate at edges
    
    Returns:
    - List of dicts with per-chain columns and totals
    """
    import re
    
    chain_tvls = data.get("chainTvls", {})
    
    if not chain_tvls:
        raise ValueError("No chain TVL data found for protocol")
    
    # Filter to only plain chain names (exclude borrowed, staking, pool2 variants)
    excluded_pattern = re.compile(r"(-borrowed|-staking|-pool2|^borrowed$|^staking$|^pool2$)")
    chain_names = sorted([name for name in chain_tvls.keys() if not excluded_pattern.search(name)])
    
    if not chain_names:
        raise ValueError("No valid chain data found (all chains are borrowed/staking/pool2)")
    
    # Build TVL maps for each chain
    chain_maps: dict[str, dict[datetime.date, float]] = {}
    all_dates_set: set[datetime.date] = set()
    
    for chain_name in chain_names:
        chain_data = chain_tvls[chain_name]
        tvl_entries = chain_data.get("tvl", [])
        
        chain_map = {
            datetime.datetime.fromtimestamp(entry["date"], tz=datetime.timezone.utc).date(): entry["totalLiquidityUSD"]
            for entry in tvl_entries
        }
        chain_maps[chain_name] = chain_map
        all_dates_set.update(chain_map.keys())
    
    # Check if we have any data in range
    all_dates_in_range = [d for d in all_dates_set if start_dt <= d <= end_dt]
    if not all_dates_in_range:
        raise ValueError(f"No TVL data available between {start_dt.isoformat()} and {end_dt.isoformat()}")
    
    # Build result dataset
    result = []
    current_date = start_dt
    
    while current_date <= end_dt:
        row: dict[str, Any] = {"date": current_date.isoformat()}
        total_raw = 0.0
        total_interpolated = 0.0
        has_any_raw = False
        has_any_interpolated = False
        
        for chain_name in chain_names:
            chain_map = chain_maps[chain_name]
            all_chain_dates = sorted(chain_map.keys())
            
            raw_val, interp_val = _process_tvl_series(
                chain_map, current_date, all_chain_dates, extrapolate
            )
            
            row[f"{chain_name}_raw"] = raw_val
            row[f"{chain_name}_interpolated"] = interp_val
            
            if raw_val is not None:
                total_raw += raw_val
                has_any_raw = True
            if interp_val is not None:
                total_interpolated += interp_val
                has_any_interpolated = True
        
        row["total_raw"] = total_raw if has_any_raw else None
        row["total_interpolated"] = total_interpolated if has_any_interpolated else None
        
        result.append(row)
        current_date += datetime.timedelta(days=1)
    
    return result


def get_average_tvl(protocol: str, start_date: str, end_date: str, extrapolate: bool = False) -> float:
    """
    Fetch and average the daily TVL for a given protocol between start_date and end_date.

    Parameters:
    - protocol (str): The protocol name (as listed on DeFiLlama).
    - start_date (str): Start date in YYYY-MM-DD format (UTC).
    - end_date (str): End date in YYYY-MM-DD format (UTC).
    - extrapolate (bool): Whether to extrapolate values at start/end. Default: False.

    Returns:
    - The average TVL over the given period (uses tvl_interpolated values).
    """
    # Use by_chain=False for aggregate average calculation
    dataset = get_tvl_dataset(protocol, start_date, end_date, extrapolate, by_chain=False)
    tvls = [row["tvl_interpolated"] for row in dataset if row["tvl_interpolated"] is not None]
    if not tvls:
        raise ValueError("No TVL data available for averaging")
    return statistics.mean(tvls)


def _output_chain_csv(dataset: list[dict[str, Any]]) -> None:
    """
    Output chain breakdown data as CSV.
    
    Column order: date, chain1_raw, chain1_interpolated, chain2_raw, chain2_interpolated, ..., total_raw, total_interpolated
    """
    if not dataset:
        return
    
    # Get all column names except date and totals, extract unique chain names
    first_row = dataset[0]
    all_keys = set(first_row.keys()) - {"date", "total_raw", "total_interpolated"}
    
    # Extract chain names (remove _raw and _interpolated suffixes)
    chain_names = sorted(set(key.rsplit("_", 1)[0] for key in all_keys))
    
    # Build header: date, then each chain's raw and interpolated, then totals
    header_parts = ["date"]
    for chain in chain_names:
        header_parts.extend([f"{chain}_raw", f"{chain}_interpolated"])
    header_parts.extend(["total_raw", "total_interpolated"])
    
    print(",".join(header_parts))
    
    # Output each row
    for row in dataset:
        row_parts = [row["date"]]
        for chain in chain_names:
            raw_val = row.get(f"{chain}_raw")
            interp_val = row.get(f"{chain}_interpolated")
            row_parts.append(f"{raw_val:.2f}" if raw_val is not None else "")
            row_parts.append(f"{interp_val:.2f}" if interp_val is not None else "")
        
        total_raw = row.get("total_raw")
        total_interp = row.get("total_interpolated")
        row_parts.append(f"{total_raw:.2f}" if total_raw is not None else "")
        row_parts.append(f"{total_interp:.2f}" if total_interp is not None else "")
        
        print(",".join(row_parts))


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
        "--extrapolate",
        action="store_true",
        help="Enable extrapolation at start/end dates. When enabled, uses linear extrapolation "
        "based on the two nearest data points to estimate values at the beginning or end of the "
        "date range where data exists only on one side. By default, extrapolation is disabled "
        "and dates that cannot be interpolated will have None/null TVL values.",
    )
    parser.add_argument(
        "--no-by-chain",
        action="store_true",
        help="Disable chain breakdown and return aggregate TVL only. By default, TVL is "
        "broken down by chain with separate columns for each chain's raw and interpolated "
        "values, plus total columns.",
    )
    args = parser.parse_args()

    try:
        if args.mean:
            # Backward compatibility: output only the mean
            avg_tvl = get_average_tvl(args.protocol, args.start_date, args.end_date, extrapolate=args.extrapolate)
            print(
                f"Average TVL for {args.protocol} from {args.start_date} to {args.end_date}: ${avg_tvl:,.2f}"
            )
        else:
            # Output full dataset
            dataset = get_tvl_dataset(args.protocol, args.start_date, args.end_date, extrapolate=args.extrapolate, by_chain=not args.no_by_chain)

            if args.format == "json":
                # JSON output
                output = json.dumps(dataset, indent=2)
                print(output)
            else:
                # CSV output (default)
                if not args.no_by_chain:
                    _output_chain_csv(dataset)
                else:
                    print("date,tvl_raw,tvl_interpolated")
                    for row in dataset:
                        raw_str = f"{row['tvl_raw']:.2f}" if row['tvl_raw'] is not None else ""
                        interp_str = f"{row['tvl_interpolated']:.2f}" if row['tvl_interpolated'] is not None else ""
                        print(f"{row['date']},{raw_str},{interp_str}")

    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
