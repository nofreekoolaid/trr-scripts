import datetime
import json
import os
import sys
import unittest
from unittest import mock

# Add parent directory to path to import avg_tvls
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from avg_tvls import _find_nearest_dates, _get_extrapolation_slope, get_average_tvl, get_tvl_dataset


def make_tvl_entry(date: datetime.date, tvl_usd: float) -> dict:
    """Helper to create a TVL data entry with Unix timestamp"""
    timestamp = int(
        datetime.datetime.combine(date, datetime.time.min, tzinfo=datetime.timezone.utc).timestamp()
    )
    return {"date": timestamp, "totalLiquidityUSD": tvl_usd}


class TestTVLDataset(unittest.TestCase):
    """Test the get_tvl_dataset function with mocked API responses"""

    def setUp(self):
        """Set up mock API responses"""
        self.mock_response_patcher = mock.patch("avg_tvls.requests.get")
        self.mock_get = self.mock_response_patcher.start()

    def tearDown(self):
        self.mock_response_patcher.stop()

    def _create_mock_response(self, tvl_data):
        """Helper to create a mock API response"""
        mock_response = mock.MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"tvl": tvl_data}
        return mock_response

    def test_raw_data_only(self):
        """Test when all dates have raw data (no interpolation needed)"""
        # Create TVL data for 3 consecutive days
        base_date = datetime.date(2025, 1, 1)
        tvl_data = [
            make_tvl_entry(base_date + datetime.timedelta(days=i), 1000000.0 + (i * 100000))
            for i in range(3)
        ]

        self.mock_get.return_value = self._create_mock_response(tvl_data)

        result = get_tvl_dataset("test-protocol", "2025-01-01", "2025-01-03", by_chain=False)

        self.assertEqual(len(result), 3)
        # All rows should have raw data (tvl_raw is not None)
        self.assertTrue(all(row["tvl_raw"] is not None for row in result))
        self.assertEqual(result[0]["tvl_raw"], 1000000.0)
        self.assertEqual(result[1]["tvl_raw"], 1100000.0)
        self.assertEqual(result[2]["tvl_raw"], 1200000.0)
        # tvl_interpolated should equal tvl_raw when raw data exists
        self.assertEqual(result[0]["tvl_interpolated"], 1000000.0)
        self.assertEqual(result[1]["tvl_interpolated"], 1100000.0)
        self.assertEqual(result[2]["tvl_interpolated"], 1200000.0)

    def test_linear_interpolation_between_points(self):
        """Test linear interpolation between two data points"""
        # Data on Jan 1 and Jan 3, missing Jan 2
        base_date = datetime.date(2025, 1, 1)
        tvl_data = [
            make_tvl_entry(base_date, 1000000.0),
            make_tvl_entry(base_date + datetime.timedelta(days=2), 1200000.0),
        ]

        self.mock_get.return_value = self._create_mock_response(tvl_data)

        result = get_tvl_dataset("test-protocol", "2025-01-01", "2025-01-03", by_chain=False)

        self.assertEqual(len(result), 3)
        # Jan 1: raw data
        self.assertEqual(result[0]["tvl_raw"], 1000000.0)
        self.assertEqual(result[0]["tvl_interpolated"], 1000000.0)
        # Jan 2: interpolated (should be 1100000.0, midpoint)
        self.assertIsNone(result[1]["tvl_raw"])
        self.assertAlmostEqual(result[1]["tvl_interpolated"], 1100000.0, places=2)
        # Jan 3: raw data
        self.assertEqual(result[2]["tvl_raw"], 1200000.0)
        self.assertEqual(result[2]["tvl_interpolated"], 1200000.0)

    def test_no_extrapolation_at_start_by_default(self):
        """Test that by default, data missing at the start has None TVL"""
        # Data starts on Jan 2, but range starts on Jan 1
        base_date = datetime.date(2025, 1, 2)
        tvl_data = [make_tvl_entry(base_date, 1000000.0)]

        self.mock_get.return_value = self._create_mock_response(tvl_data)

        result = get_tvl_dataset("test-protocol", "2025-01-01", "2025-01-02", by_chain=False)

        self.assertEqual(len(result), 2)
        # Jan 1: no extrapolation by default, both fields are None
        self.assertIsNone(result[0]["tvl_raw"])
        self.assertIsNone(result[0]["tvl_interpolated"])
        # Jan 2: raw data
        self.assertEqual(result[1]["tvl_raw"], 1000000.0)
        self.assertEqual(result[1]["tvl_interpolated"], 1000000.0)

    def test_forward_fill_at_start_with_extrapolation(self):
        """Test forward-fill when data is missing at the start of range (with extrapolate=True)"""
        # Data starts on Jan 2, but range starts on Jan 1
        # With only one data point, should fallback to simple forward-fill
        base_date = datetime.date(2025, 1, 2)
        tvl_data = [make_tvl_entry(base_date, 1000000.0)]

        self.mock_get.return_value = self._create_mock_response(tvl_data)

        result = get_tvl_dataset("test-protocol", "2025-01-01", "2025-01-02", extrapolate=True, by_chain=False)

        self.assertEqual(len(result), 2)
        # Jan 1: forward-fill from Jan 2 (fallback with only 1 data point)
        self.assertIsNone(result[0]["tvl_raw"])
        self.assertEqual(result[0]["tvl_interpolated"], 1000000.0)
        # Jan 2: raw data
        self.assertEqual(result[1]["tvl_raw"], 1000000.0)
        self.assertEqual(result[1]["tvl_interpolated"], 1000000.0)

    def test_no_extrapolation_at_end_by_default(self):
        """Test that by default, data missing at the end has None TVL"""
        # Data ends on Jan 1, but range ends on Jan 2
        base_date = datetime.date(2025, 1, 1)
        tvl_data = [make_tvl_entry(base_date, 1000000.0)]

        self.mock_get.return_value = self._create_mock_response(tvl_data)

        result = get_tvl_dataset("test-protocol", "2025-01-01", "2025-01-02", by_chain=False)

        self.assertEqual(len(result), 2)
        # Jan 1: raw data
        self.assertEqual(result[0]["tvl_raw"], 1000000.0)
        self.assertEqual(result[0]["tvl_interpolated"], 1000000.0)
        # Jan 2: no extrapolation by default, both fields are None
        self.assertIsNone(result[1]["tvl_raw"])
        self.assertIsNone(result[1]["tvl_interpolated"])

    def test_backward_fill_at_end_with_extrapolation(self):
        """Test backward-fill when data is missing at the end of range (with extrapolate=True)"""
        # Data ends on Jan 1, but range ends on Jan 2
        # With only one data point, should fallback to simple backward-fill
        base_date = datetime.date(2025, 1, 1)
        tvl_data = [make_tvl_entry(base_date, 1000000.0)]

        self.mock_get.return_value = self._create_mock_response(tvl_data)

        result = get_tvl_dataset("test-protocol", "2025-01-01", "2025-01-02", extrapolate=True, by_chain=False)

        self.assertEqual(len(result), 2)
        # Jan 1: raw data
        self.assertEqual(result[0]["tvl_raw"], 1000000.0)
        self.assertEqual(result[0]["tvl_interpolated"], 1000000.0)
        # Jan 2: backward-fill from Jan 1 (fallback with only 1 data point)
        self.assertIsNone(result[1]["tvl_raw"])
        self.assertEqual(result[1]["tvl_interpolated"], 1000000.0)

    def test_complex_interpolation_scenario(self):
        """Test a complex scenario with multiple gaps"""
        # Data on Jan 1, Jan 4, Jan 6; missing Jan 2, 3, 5
        base_date = datetime.date(2025, 1, 1)
        tvl_data = [
            make_tvl_entry(base_date, 1000000.0),
            make_tvl_entry(base_date + datetime.timedelta(days=3), 1300000.0),
            make_tvl_entry(base_date + datetime.timedelta(days=5), 1500000.0),
        ]

        self.mock_get.return_value = self._create_mock_response(tvl_data)

        result = get_tvl_dataset("test-protocol", "2025-01-01", "2025-01-06", by_chain=False)

        self.assertEqual(len(result), 6)
        # Jan 1: raw
        self.assertEqual(result[0]["tvl_raw"], 1000000.0)
        # Jan 2: interpolated between Jan 1 (1M) and Jan 4 (1.3M) = 1.1M
        self.assertIsNone(result[1]["tvl_raw"])
        self.assertAlmostEqual(result[1]["tvl_interpolated"], 1100000.0, places=2)
        # Jan 3: interpolated = 1.2M
        self.assertIsNone(result[2]["tvl_raw"])
        self.assertAlmostEqual(result[2]["tvl_interpolated"], 1200000.0, places=2)
        # Jan 4: raw
        self.assertEqual(result[3]["tvl_raw"], 1300000.0)
        # Jan 5: interpolated between Jan 4 (1.3M) and Jan 6 (1.5M) = 1.4M
        self.assertIsNone(result[4]["tvl_raw"])
        self.assertAlmostEqual(result[4]["tvl_interpolated"], 1400000.0, places=2)
        # Jan 6: raw
        self.assertEqual(result[5]["tvl_raw"], 1500000.0)

    def test_no_data_in_range_error(self):
        """Test error when no data exists in the specified range"""
        # Data exists but outside the range
        base_date = datetime.date(2025, 2, 1)
        tvl_data = [make_tvl_entry(base_date, 1000000.0)]

        self.mock_get.return_value = self._create_mock_response(tvl_data)

        with self.assertRaises(ValueError) as context:
            get_tvl_dataset("test-protocol", "2025-01-01", "2025-01-31", by_chain=False)

        self.assertIn("No TVL data available", str(context.exception))

    def test_api_error(self):
        """Test handling of API errors"""
        mock_response = mock.MagicMock()
        mock_response.status_code = 404
        self.mock_get.return_value = mock_response

        with self.assertRaises(ValueError) as context:
            get_tvl_dataset("test-protocol", "2024-01-01", "2024-01-31", by_chain=False)

        self.assertIn("Error fetching data", str(context.exception))

    def test_empty_tvl_data(self):
        """Test error when API returns empty TVL data"""
        mock_response = mock.MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"tvl": []}
        self.mock_get.return_value = mock_response

        with self.assertRaises(ValueError) as context:
            get_tvl_dataset("test-protocol", "2024-01-01", "2024-01-31", by_chain=False)

        self.assertIn("No TVL data found", str(context.exception))


class TestFindNearestDates(unittest.TestCase):
    """Test the _find_nearest_dates helper function"""

    def test_find_both_dates(self):
        """Test finding both previous and next dates"""
        target = datetime.date(2025, 1, 3)
        available = [
            datetime.date(2025, 1, 1),
            datetime.date(2025, 1, 2),
            datetime.date(2025, 1, 4),
            datetime.date(2025, 1, 5),
        ]

        prev, next_date = _find_nearest_dates(target, available)

        self.assertEqual(prev, datetime.date(2025, 1, 2))
        self.assertEqual(next_date, datetime.date(2025, 1, 4))

    def test_find_only_previous(self):
        """Test when only previous date exists"""
        target = datetime.date(2025, 1, 5)
        available = [
            datetime.date(2025, 1, 1),
            datetime.date(2025, 1, 2),
            datetime.date(2025, 1, 3),
        ]

        prev, next_date = _find_nearest_dates(target, available)

        self.assertEqual(prev, datetime.date(2025, 1, 3))
        self.assertIsNone(next_date)

    def test_find_only_next(self):
        """Test when only next date exists"""
        target = datetime.date(2025, 1, 1)
        available = [
            datetime.date(2025, 1, 3),
            datetime.date(2025, 1, 4),
            datetime.date(2025, 1, 5),
        ]

        prev, next_date = _find_nearest_dates(target, available)

        self.assertIsNone(prev)
        self.assertEqual(next_date, datetime.date(2025, 1, 3))

    def test_target_equals_available_date(self):
        """Test when target equals an available date"""
        target = datetime.date(2025, 1, 2)
        available = [
            datetime.date(2025, 1, 1),
            datetime.date(2025, 1, 2),
            datetime.date(2025, 1, 3),
        ]

        prev, next_date = _find_nearest_dates(target, available)

        # Should find the target itself as previous, and the next one
        self.assertEqual(prev, datetime.date(2025, 1, 2))
        self.assertEqual(next_date, datetime.date(2025, 1, 3))


class TestAverageTVL(unittest.TestCase):
    """Test the get_average_tvl function (backward compatibility)"""

    def setUp(self):
        self.mock_response_patcher = mock.patch("avg_tvls.requests.get")
        self.mock_get = self.mock_response_patcher.start()

    def tearDown(self):
        self.mock_response_patcher.stop()

    def test_average_calculation(self):
        """Test that average is calculated correctly"""
        base_date = datetime.date(2025, 1, 1)
        tvl_data = [
            make_tvl_entry(base_date + datetime.timedelta(days=i), 1000000.0 + (i * 100000))
            for i in range(3)
        ]

        mock_response = mock.MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"tvl": tvl_data}
        self.mock_get.return_value = mock_response

        avg = get_average_tvl("test-protocol", "2025-01-01", "2025-01-03")

        # Average of 1M, 1.1M, 1.2M = 1.1M
        self.assertAlmostEqual(avg, 1100000.0, places=2)

    def test_average_with_interpolation(self):
        """Test that average includes interpolated values"""
        # Data on Jan 1 and Jan 3, missing Jan 2
        base_date = datetime.date(2025, 1, 1)
        tvl_data = [
            make_tvl_entry(base_date, 1000000.0),
            make_tvl_entry(base_date + datetime.timedelta(days=2), 1200000.0),
        ]

        mock_response = mock.MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"tvl": tvl_data}
        self.mock_get.return_value = mock_response

        avg = get_average_tvl("test-protocol", "2025-01-01", "2025-01-03")

        # Average of 1M, 1.1M (interpolated), 1.2M = 1.1M
        self.assertAlmostEqual(avg, 1100000.0, places=2)


class TestCLIOutput(unittest.TestCase):
    """Test CLI output formats - simplified to test data formatting"""

    def setUp(self):
        self.mock_response_patcher = mock.patch("avg_tvls.requests.get")
        self.mock_get = self.mock_response_patcher.start()

        # Set up mock data
        base_date = datetime.date(2025, 1, 1)
        tvl_data = [
            make_tvl_entry(base_date + datetime.timedelta(days=i), 1000000.0 + (i * 100000))
            for i in range(3)
        ]

        mock_response = mock.MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"tvl": tvl_data}
        self.mock_get.return_value = mock_response

    def tearDown(self):
        self.mock_response_patcher.stop()

    def test_dataset_format_for_csv(self):
        """Test that dataset format is suitable for CSV output"""
        dataset = get_tvl_dataset("test-protocol", "2025-01-01", "2025-01-03", by_chain=False)

        # Verify structure suitable for CSV
        self.assertIsInstance(dataset, list)
        self.assertEqual(len(dataset), 3)
        for row in dataset:
            self.assertIn("date", row)
            self.assertIn("tvl_raw", row)
            self.assertIn("tvl_interpolated", row)
            # Verify date format
            self.assertIsInstance(row["date"], str)
            # Verify TVL fields are numeric (when raw data exists)
            self.assertIsInstance(row["tvl_raw"], (int, float))
            self.assertIsInstance(row["tvl_interpolated"], (int, float))

    def test_dataset_format_for_json(self):
        """Test that dataset format is suitable for JSON output"""
        dataset = get_tvl_dataset("test-protocol", "2025-01-01", "2025-01-03", by_chain=False)

        # Verify JSON serializable
        json_str = json.dumps(dataset)
        data = json.loads(json_str)

        # Check JSON structure
        self.assertIsInstance(data, list)
        self.assertEqual(len(data), 3)
        self.assertIn("date", data[0])
        self.assertIn("tvl_raw", data[0])
        self.assertIn("tvl_interpolated", data[0])


class TestDefaultExtrapolationBehavior(unittest.TestCase):
    """Test the default extrapolation=False behavior"""

    def setUp(self):
        self.mock_response_patcher = mock.patch("avg_tvls.requests.get")
        self.mock_get = self.mock_response_patcher.start()

    def tearDown(self):
        self.mock_response_patcher.stop()

    def _create_mock_response(self, tvl_data):
        """Helper to create a mock API response"""
        mock_response = mock.MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"tvl": tvl_data}
        return mock_response

    def test_all_dates_included_in_range(self):
        """Test that all dates in range are included even without extrapolation"""
        # Data only on Jan 3, range from Jan 1-5
        base_date = datetime.date(2025, 1, 3)
        tvl_data = [make_tvl_entry(base_date, 1000000.0)]

        self.mock_get.return_value = self._create_mock_response(tvl_data)

        result = get_tvl_dataset("test-protocol", "2025-01-01", "2025-01-05", by_chain=False)

        # All 5 dates should be included
        self.assertEqual(len(result), 5)
        dates = [row["date"] for row in result]
        self.assertEqual(dates, ["2025-01-01", "2025-01-02", "2025-01-03", "2025-01-04", "2025-01-05"])

    def test_edge_dates_have_none_tvl(self):
        """Test that dates at edges without extrapolation have None TVL"""
        # Data only on Jan 3, range from Jan 1-5
        base_date = datetime.date(2025, 1, 3)
        tvl_data = [make_tvl_entry(base_date, 1000000.0)]

        self.mock_get.return_value = self._create_mock_response(tvl_data)

        result = get_tvl_dataset("test-protocol", "2025-01-01", "2025-01-05", by_chain=False)

        # Jan 1, 2 (before data) should have None for both fields
        self.assertIsNone(result[0]["tvl_raw"])
        self.assertIsNone(result[0]["tvl_interpolated"])
        self.assertIsNone(result[1]["tvl_raw"])
        self.assertIsNone(result[1]["tvl_interpolated"])
        # Jan 3 (raw data) should have value in both fields
        self.assertEqual(result[2]["tvl_raw"], 1000000.0)
        self.assertEqual(result[2]["tvl_interpolated"], 1000000.0)
        # Jan 4, 5 (after data) should have None for both fields
        self.assertIsNone(result[3]["tvl_raw"])
        self.assertIsNone(result[3]["tvl_interpolated"])
        self.assertIsNone(result[4]["tvl_raw"])
        self.assertIsNone(result[4]["tvl_interpolated"])

    def test_average_tvl_filters_none_values(self):
        """Test that get_average_tvl filters out None values"""
        # Data only on Jan 2, range from Jan 1-3
        base_date = datetime.date(2025, 1, 2)
        tvl_data = [make_tvl_entry(base_date, 1000000.0)]

        self.mock_get.return_value = self._create_mock_response(tvl_data)

        # Should only average the one valid value
        avg = get_average_tvl("test-protocol", "2025-01-01", "2025-01-03")
        self.assertEqual(avg, 1000000.0)


class TestSeparateRawAndInterpolatedFields(unittest.TestCase):
    """Test the separate tvl_raw and tvl_interpolated fields"""

    def setUp(self):
        self.mock_response_patcher = mock.patch("avg_tvls.requests.get")
        self.mock_get = self.mock_response_patcher.start()

    def tearDown(self):
        self.mock_response_patcher.stop()

    def _create_mock_response(self, tvl_data):
        """Helper to create a mock API response"""
        mock_response = mock.MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"tvl": tvl_data}
        return mock_response

    def test_raw_field_contains_actual_data(self):
        """Test that tvl_raw contains actual data points only"""
        # Data on Jan 1 and Jan 3, missing Jan 2
        base_date = datetime.date(2025, 1, 1)
        tvl_data = [
            make_tvl_entry(base_date, 1000000.0),
            make_tvl_entry(base_date + datetime.timedelta(days=2), 1200000.0),
        ]

        self.mock_get.return_value = self._create_mock_response(tvl_data)

        result = get_tvl_dataset("test-protocol", "2025-01-01", "2025-01-03", by_chain=False)

        # Jan 1: has raw data
        self.assertEqual(result[0]["tvl_raw"], 1000000.0)
        # Jan 2: no raw data (interpolated)
        self.assertIsNone(result[1]["tvl_raw"])
        # Jan 3: has raw data
        self.assertEqual(result[2]["tvl_raw"], 1200000.0)

    def test_interpolated_field_equals_raw_when_raw_exists(self):
        """Test that tvl_interpolated equals tvl_raw when raw data exists"""
        base_date = datetime.date(2025, 1, 1)
        tvl_data = [
            make_tvl_entry(base_date + datetime.timedelta(days=i), 1000000.0 + (i * 100000))
            for i in range(3)
        ]

        self.mock_get.return_value = self._create_mock_response(tvl_data)

        result = get_tvl_dataset("test-protocol", "2025-01-01", "2025-01-03", by_chain=False)

        for row in result:
            self.assertEqual(row["tvl_raw"], row["tvl_interpolated"])

    def test_interpolated_field_computed_for_gaps(self):
        """Test that tvl_interpolated is computed for dates without raw data"""
        # Data on Jan 1 and Jan 3, missing Jan 2
        base_date = datetime.date(2025, 1, 1)
        tvl_data = [
            make_tvl_entry(base_date, 1000000.0),
            make_tvl_entry(base_date + datetime.timedelta(days=2), 1200000.0),
        ]

        self.mock_get.return_value = self._create_mock_response(tvl_data)

        result = get_tvl_dataset("test-protocol", "2025-01-01", "2025-01-03", by_chain=False)

        # Jan 2: no raw data but has interpolated value
        self.assertIsNone(result[1]["tvl_raw"])
        self.assertIsNotNone(result[1]["tvl_interpolated"])
        self.assertAlmostEqual(result[1]["tvl_interpolated"], 1100000.0, places=2)

    def test_both_fields_none_when_cannot_interpolate(self):
        """Test that both fields are None when interpolation is not possible"""
        # Data only on Jan 2, range from Jan 1-3
        base_date = datetime.date(2025, 1, 2)
        tvl_data = [make_tvl_entry(base_date, 1000000.0)]

        self.mock_get.return_value = self._create_mock_response(tvl_data)

        result = get_tvl_dataset("test-protocol", "2025-01-01", "2025-01-03", extrapolate=False, by_chain=False)

        # Jan 1: no raw and cannot interpolate (no previous data)
        self.assertIsNone(result[0]["tvl_raw"])
        self.assertIsNone(result[0]["tvl_interpolated"])
        # Jan 2: has raw data
        self.assertEqual(result[1]["tvl_raw"], 1000000.0)
        self.assertEqual(result[1]["tvl_interpolated"], 1000000.0)
        # Jan 3: no raw and cannot interpolate (no next data)
        self.assertIsNone(result[2]["tvl_raw"])
        self.assertIsNone(result[2]["tvl_interpolated"])


class TestExtrapolationSlope(unittest.TestCase):
    """Test the _get_extrapolation_slope helper function"""

    def test_positive_slope(self):
        """Test slope calculation with increasing TVL"""
        date1 = datetime.date(2025, 1, 1)
        date2 = datetime.date(2025, 1, 3)
        tvl1 = 1000000.0
        tvl2 = 1200000.0
        
        slope = _get_extrapolation_slope(date1, tvl1, date2, tvl2)
        
        # Change of 200000 over 2 days = 100000 per day
        self.assertAlmostEqual(slope, 100000.0, places=2)

    def test_negative_slope(self):
        """Test slope calculation with decreasing TVL"""
        date1 = datetime.date(2025, 1, 1)
        date2 = datetime.date(2025, 1, 5)
        tvl1 = 2000000.0
        tvl2 = 1600000.0
        
        slope = _get_extrapolation_slope(date1, tvl1, date2, tvl2)
        
        # Change of -400000 over 4 days = -100000 per day
        self.assertAlmostEqual(slope, -100000.0, places=2)

    def test_zero_slope(self):
        """Test slope calculation with constant TVL"""
        date1 = datetime.date(2025, 1, 1)
        date2 = datetime.date(2025, 1, 10)
        tvl1 = 1000000.0
        tvl2 = 1000000.0
        
        slope = _get_extrapolation_slope(date1, tvl1, date2, tvl2)
        
        self.assertAlmostEqual(slope, 0.0, places=2)

    def test_same_date(self):
        """Test slope calculation when dates are the same (edge case)"""
        date1 = datetime.date(2025, 1, 1)
        date2 = datetime.date(2025, 1, 1)
        tvl1 = 1000000.0
        tvl2 = 1200000.0
        
        slope = _get_extrapolation_slope(date1, tvl1, date2, tvl2)
        
        # Should return 0 to avoid division by zero
        self.assertAlmostEqual(slope, 0.0, places=2)


class TestExtrapolation(unittest.TestCase):
    """Test linear extrapolation at start/end of date range"""

    def setUp(self):
        self.mock_response_patcher = mock.patch("avg_tvls.requests.get")
        self.mock_get = self.mock_response_patcher.start()

    def tearDown(self):
        self.mock_response_patcher.stop()

    def _create_mock_response(self, tvl_data):
        """Helper to create a mock API response"""
        mock_response = mock.MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"tvl": tvl_data}
        return mock_response

    def test_backward_extrapolation_at_start(self):
        """Test backward extrapolation when data exists after range start"""
        # Data on Jan 3 and Jan 5, need to extrapolate back to Jan 1-2
        base_date = datetime.date(2025, 1, 3)
        tvl_data = [
            make_tvl_entry(base_date, 1100000.0),  # Jan 3
            make_tvl_entry(base_date + datetime.timedelta(days=2), 1300000.0),  # Jan 5
        ]

        self.mock_get.return_value = self._create_mock_response(tvl_data)

        result = get_tvl_dataset("test-protocol", "2025-01-01", "2025-01-05", extrapolate=True, by_chain=False)

        self.assertEqual(len(result), 5)
        
        # Slope between Jan 3 (1.1M) and Jan 5 (1.3M) = 100k per day
        # Jan 1: 1.1M - (2 days * 100k) = 900k
        self.assertIsNone(result[0]["tvl_raw"])
        self.assertAlmostEqual(result[0]["tvl_interpolated"], 900000.0, places=2)
        
        # Jan 2: 1.1M - (1 day * 100k) = 1M
        self.assertIsNone(result[1]["tvl_raw"])
        self.assertAlmostEqual(result[1]["tvl_interpolated"], 1000000.0, places=2)
        
        # Jan 3: raw data
        self.assertEqual(result[2]["tvl_raw"], 1100000.0)
        self.assertEqual(result[2]["tvl_interpolated"], 1100000.0)
        
        # Jan 4: interpolated between Jan 3 and Jan 5
        self.assertIsNone(result[3]["tvl_raw"])
        self.assertAlmostEqual(result[3]["tvl_interpolated"], 1200000.0, places=2)
        
        # Jan 5: raw data
        self.assertEqual(result[4]["tvl_raw"], 1300000.0)
        self.assertEqual(result[4]["tvl_interpolated"], 1300000.0)

    def test_forward_extrapolation_at_end(self):
        """Test forward extrapolation when data exists before range end"""
        # Data on Jan 1 and Jan 3, need to extrapolate forward to Jan 4-5
        base_date = datetime.date(2025, 1, 1)
        tvl_data = [
            make_tvl_entry(base_date, 1000000.0),  # Jan 1
            make_tvl_entry(base_date + datetime.timedelta(days=2), 1200000.0),  # Jan 3
        ]

        self.mock_get.return_value = self._create_mock_response(tvl_data)

        result = get_tvl_dataset("test-protocol", "2025-01-01", "2025-01-05", extrapolate=True, by_chain=False)

        self.assertEqual(len(result), 5)
        
        # Jan 1: raw data
        self.assertEqual(result[0]["tvl_raw"], 1000000.0)
        self.assertEqual(result[0]["tvl_interpolated"], 1000000.0)
        
        # Jan 2: interpolated between Jan 1 and Jan 3
        self.assertIsNone(result[1]["tvl_raw"])
        self.assertAlmostEqual(result[1]["tvl_interpolated"], 1100000.0, places=2)
        
        # Jan 3: raw data
        self.assertEqual(result[2]["tvl_raw"], 1200000.0)
        self.assertEqual(result[2]["tvl_interpolated"], 1200000.0)
        
        # Slope between Jan 1 (1M) and Jan 3 (1.2M) = 100k per day
        # Jan 4: 1.2M + (1 day * 100k) = 1.3M
        self.assertIsNone(result[3]["tvl_raw"])
        self.assertAlmostEqual(result[3]["tvl_interpolated"], 1300000.0, places=2)
        
        # Jan 5: 1.2M + (2 days * 100k) = 1.4M
        self.assertIsNone(result[4]["tvl_raw"])
        self.assertAlmostEqual(result[4]["tvl_interpolated"], 1400000.0, places=2)

    def test_no_extrapolate_includes_start_dates_with_none(self):
        """Test that extrapolate=False includes all dates but with None for edges"""
        # Data on Jan 3 and Jan 5, range from Jan 1-5
        base_date = datetime.date(2025, 1, 3)
        tvl_data = [
            make_tvl_entry(base_date, 1100000.0),  # Jan 3
            make_tvl_entry(base_date + datetime.timedelta(days=2), 1300000.0),  # Jan 5
        ]

        self.mock_get.return_value = self._create_mock_response(tvl_data)

        result = get_tvl_dataset("test-protocol", "2025-01-01", "2025-01-05", extrapolate=False, by_chain=False)

        # Should have all 5 dates, Jan 1-2 with None TVL
        self.assertEqual(len(result), 5)
        self.assertEqual(result[0]["date"], "2025-01-01")
        self.assertIsNone(result[0]["tvl_interpolated"])
        self.assertEqual(result[1]["date"], "2025-01-02")
        self.assertIsNone(result[1]["tvl_interpolated"])
        self.assertEqual(result[2]["date"], "2025-01-03")
        self.assertEqual(result[2]["tvl_raw"], 1100000.0)
        self.assertEqual(result[3]["date"], "2025-01-04")
        self.assertAlmostEqual(result[3]["tvl_interpolated"], 1200000.0, places=2)
        self.assertEqual(result[4]["date"], "2025-01-05")
        self.assertEqual(result[4]["tvl_raw"], 1300000.0)

    def test_no_extrapolate_includes_end_dates_with_none(self):
        """Test that extrapolate=False includes all dates but with None for edges"""
        # Data on Jan 1 and Jan 3, range from Jan 1-5
        base_date = datetime.date(2025, 1, 1)
        tvl_data = [
            make_tvl_entry(base_date, 1000000.0),  # Jan 1
            make_tvl_entry(base_date + datetime.timedelta(days=2), 1200000.0),  # Jan 3
        ]

        self.mock_get.return_value = self._create_mock_response(tvl_data)

        result = get_tvl_dataset("test-protocol", "2025-01-01", "2025-01-05", extrapolate=False, by_chain=False)

        # Should have all 5 dates, Jan 4-5 with None TVL
        self.assertEqual(len(result), 5)
        self.assertEqual(result[0]["date"], "2025-01-01")
        self.assertEqual(result[0]["tvl_raw"], 1000000.0)
        self.assertEqual(result[1]["date"], "2025-01-02")
        self.assertAlmostEqual(result[1]["tvl_interpolated"], 1100000.0, places=2)
        self.assertEqual(result[2]["date"], "2025-01-03")
        self.assertEqual(result[2]["tvl_raw"], 1200000.0)
        self.assertEqual(result[3]["date"], "2025-01-04")
        self.assertIsNone(result[3]["tvl_interpolated"])
        self.assertEqual(result[4]["date"], "2025-01-05")
        self.assertIsNone(result[4]["tvl_interpolated"])

    def test_extrapolation_with_negative_slope(self):
        """Test extrapolation with decreasing TVL"""
        # Data on Jan 1 and Jan 3 with decreasing TVL, extrapolate to Jan 4-5
        base_date = datetime.date(2025, 1, 1)
        tvl_data = [
            make_tvl_entry(base_date, 1200000.0),  # Jan 1
            make_tvl_entry(base_date + datetime.timedelta(days=2), 1000000.0),  # Jan 3
        ]

        self.mock_get.return_value = self._create_mock_response(tvl_data)

        result = get_tvl_dataset("test-protocol", "2025-01-01", "2025-01-05", extrapolate=True, by_chain=False)

        self.assertEqual(len(result), 5)
        
        # Slope between Jan 1 (1.2M) and Jan 3 (1M) = -100k per day
        # Jan 4: 1M + (1 day * -100k) = 900k
        self.assertIsNone(result[3]["tvl_raw"])
        self.assertAlmostEqual(result[3]["tvl_interpolated"], 900000.0, places=2)
        
        # Jan 5: 1M + (2 days * -100k) = 800k
        self.assertIsNone(result[4]["tvl_raw"])
        self.assertAlmostEqual(result[4]["tvl_interpolated"], 800000.0, places=2)

    def test_average_tvl_with_extrapolation(self):
        """Test that get_average_tvl respects extrapolate parameter"""
        # Data on Jan 3 and Jan 5, range from Jan 1-5
        # This creates a situation where extrapolation is needed at the start
        base_date = datetime.date(2025, 1, 3)
        tvl_data = [
            make_tvl_entry(base_date, 1100000.0),  # Jan 3
            make_tvl_entry(base_date + datetime.timedelta(days=2), 1300000.0),  # Jan 5
        ]

        mock_response = mock.MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"tvl": tvl_data}
        self.mock_get.return_value = mock_response

        # With extrapolation (should have 5 days: Jan 1-5)
        # Slope = 100k/day, so Jan 1 = 900k, Jan 2 = 1M, Jan 3 = 1.1M, Jan 4 = 1.2M, Jan 5 = 1.3M
        # Average = (900k + 1M + 1.1M + 1.2M + 1.3M) / 5 = 5.5M / 5 = 1.1M
        avg_with = get_average_tvl("test-protocol", "2025-01-01", "2025-01-05", extrapolate=True)
        
        # Without extrapolation (Jan 1-2 have None, only uses Jan 3, 4, 5)
        # Jan 3 = 1.1M (raw), Jan 4 = 1.2M (interpolated), Jan 5 = 1.3M (raw)
        # Average = (1.1M + 1.2M + 1.3M) / 3 = 3.6M / 3 = 1.2M
        avg_without = get_average_tvl("test-protocol", "2025-01-01", "2025-01-05", extrapolate=False)
        
        # Averages should be different
        self.assertNotEqual(avg_with, avg_without)
        
        # With extrapolation average should be 1.1M
        self.assertAlmostEqual(avg_with, 1100000.0, places=2)
        
        # Without extrapolation should be 1.2M (None values are filtered out)
        self.assertAlmostEqual(avg_without, 1200000.0, places=2)


class TestChainBreakdown(unittest.TestCase):
    """Test the by_chain=True functionality"""

    def setUp(self):
        self.mock_response_patcher = mock.patch("avg_tvls.requests.get")
        self.mock_get = self.mock_response_patcher.start()

    def tearDown(self):
        self.mock_response_patcher.stop()

    def _create_mock_response_with_chains(self, chain_data: dict):
        """Helper to create a mock API response with chainTvls"""
        mock_response = mock.MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "tvl": [],  # Empty aggregate, chains only
            "chainTvls": chain_data,
        }
        return mock_response

    def test_by_chain_returns_chain_columns(self):
        """Test that by_chain=True returns separate columns for each chain"""
        base_date = datetime.date(2025, 1, 1)
        chain_data = {
            "Ethereum": {
                "tvl": [
                    make_tvl_entry(base_date, 1000000.0),
                    make_tvl_entry(base_date + datetime.timedelta(days=1), 1100000.0),
                ]
            },
            "Arbitrum": {
                "tvl": [
                    make_tvl_entry(base_date, 500000.0),
                    make_tvl_entry(base_date + datetime.timedelta(days=1), 550000.0),
                ]
            },
        }

        self.mock_get.return_value = self._create_mock_response_with_chains(chain_data)

        result = get_tvl_dataset("test-protocol", "2025-01-01", "2025-01-02", by_chain=True)

        self.assertEqual(len(result), 2)
        # Check for chain columns
        self.assertIn("Ethereum_raw", result[0])
        self.assertIn("Ethereum_interpolated", result[0])
        self.assertIn("Arbitrum_raw", result[0])
        self.assertIn("Arbitrum_interpolated", result[0])
        self.assertIn("total_raw", result[0])
        self.assertIn("total_interpolated", result[0])

    def test_chain_totals_sum_correctly(self):
        """Test that total columns are sum of individual chain values"""
        base_date = datetime.date(2025, 1, 1)
        chain_data = {
            "Ethereum": {
                "tvl": [make_tvl_entry(base_date, 1000000.0)]
            },
            "Arbitrum": {
                "tvl": [make_tvl_entry(base_date, 500000.0)]
            },
        }

        self.mock_get.return_value = self._create_mock_response_with_chains(chain_data)

        result = get_tvl_dataset("test-protocol", "2025-01-01", "2025-01-01", by_chain=True)

        # Total should be sum of chains
        self.assertEqual(result[0]["total_raw"], 1500000.0)
        self.assertEqual(result[0]["total_interpolated"], 1500000.0)

    def test_chain_interpolation_independent(self):
        """Test that each chain is interpolated independently"""
        base_date = datetime.date(2025, 1, 1)
        chain_data = {
            "Ethereum": {
                "tvl": [
                    make_tvl_entry(base_date, 1000000.0),
                    make_tvl_entry(base_date + datetime.timedelta(days=2), 1200000.0),
                ]
            },
            "Arbitrum": {
                "tvl": [
                    # Missing Jan 1, has Jan 2 only
                    make_tvl_entry(base_date + datetime.timedelta(days=1), 500000.0),
                ]
            },
        }

        self.mock_get.return_value = self._create_mock_response_with_chains(chain_data)

        result = get_tvl_dataset("test-protocol", "2025-01-01", "2025-01-03", by_chain=True)

        self.assertEqual(len(result), 3)
        
        # Jan 1: Ethereum has raw, Arbitrum has None (can't interpolate)
        self.assertEqual(result[0]["Ethereum_raw"], 1000000.0)
        self.assertIsNone(result[0]["Arbitrum_raw"])
        self.assertIsNone(result[0]["Arbitrum_interpolated"])
        
        # Jan 2: Ethereum interpolated (1.1M), Arbitrum has raw
        self.assertIsNone(result[1]["Ethereum_raw"])
        self.assertAlmostEqual(result[1]["Ethereum_interpolated"], 1100000.0, places=2)
        self.assertEqual(result[1]["Arbitrum_raw"], 500000.0)
        
        # Jan 3: Ethereum has raw (1.2M), Arbitrum has None
        self.assertEqual(result[2]["Ethereum_raw"], 1200000.0)
        self.assertIsNone(result[2]["Arbitrum_raw"])

    def test_by_chain_excludes_borrowed_variants(self):
        """Test that borrowed/staking/pool2 variants are excluded"""
        base_date = datetime.date(2025, 1, 1)
        chain_data = {
            "Ethereum": {
                "tvl": [make_tvl_entry(base_date, 1000000.0)]
            },
            "Ethereum-borrowed": {
                "tvl": [make_tvl_entry(base_date, 800000.0)]
            },
            "borrowed": {
                "tvl": [make_tvl_entry(base_date, 800000.0)]
            },
            "staking": {
                "tvl": [make_tvl_entry(base_date, 200000.0)]
            },
        }

        self.mock_get.return_value = self._create_mock_response_with_chains(chain_data)

        result = get_tvl_dataset("test-protocol", "2025-01-01", "2025-01-01", by_chain=True)

        # Should only have Ethereum, not borrowed variants
        self.assertIn("Ethereum_raw", result[0])
        self.assertNotIn("Ethereum-borrowed_raw", result[0])
        self.assertNotIn("borrowed_raw", result[0])
        self.assertNotIn("staking_raw", result[0])
        
        # Total should only include Ethereum
        self.assertEqual(result[0]["total_raw"], 1000000.0)

    def test_by_chain_false_returns_aggregate(self):
        """Test backward compatibility: by_chain=False returns aggregate data"""
        base_date = datetime.date(2025, 1, 1)
        
        # Create response with both aggregate tvl and chainTvls
        mock_response = mock.MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "tvl": [make_tvl_entry(base_date, 1500000.0)],
            "chainTvls": {
                "Ethereum": {"tvl": [make_tvl_entry(base_date, 1000000.0)]},
                "Arbitrum": {"tvl": [make_tvl_entry(base_date, 500000.0)]},
            },
        }
        self.mock_get.return_value = mock_response

        result = get_tvl_dataset("test-protocol", "2025-01-01", "2025-01-01", by_chain=False)

        # Should return aggregate format, not chain format
        self.assertIn("tvl_raw", result[0])
        self.assertIn("tvl_interpolated", result[0])
        self.assertNotIn("Ethereum_raw", result[0])
        self.assertEqual(result[0]["tvl_raw"], 1500000.0)

    def test_chain_data_with_extrapolation(self):
        """Test that extrapolation works with chain data"""
        base_date = datetime.date(2025, 1, 2)
        chain_data = {
            "Ethereum": {
                "tvl": [
                    make_tvl_entry(base_date, 1000000.0),
                    make_tvl_entry(base_date + datetime.timedelta(days=1), 1100000.0),
                ]
            },
        }

        self.mock_get.return_value = self._create_mock_response_with_chains(chain_data)

        # Request range starting before data
        result = get_tvl_dataset("test-protocol", "2025-01-01", "2025-01-03", by_chain=True, extrapolate=True)

        self.assertEqual(len(result), 3)
        
        # Jan 1: extrapolated backward
        self.assertIsNone(result[0]["Ethereum_raw"])
        self.assertIsNotNone(result[0]["Ethereum_interpolated"])
        
        # Jan 2: raw data
        self.assertEqual(result[1]["Ethereum_raw"], 1000000.0)


if __name__ == "__main__":
    unittest.main()
