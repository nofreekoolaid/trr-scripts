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

        result = get_tvl_dataset("test-protocol", "2025-01-01", "2025-01-03")

        self.assertEqual(len(result), 3)
        self.assertFalse(any(row["is_interpolated"] for row in result))
        self.assertEqual(result[0]["tvl"], 1000000.0)
        self.assertEqual(result[1]["tvl"], 1100000.0)
        self.assertEqual(result[2]["tvl"], 1200000.0)

    def test_linear_interpolation_between_points(self):
        """Test linear interpolation between two data points"""
        # Data on Jan 1 and Jan 3, missing Jan 2
        base_date = datetime.date(2025, 1, 1)
        tvl_data = [
            make_tvl_entry(base_date, 1000000.0),
            make_tvl_entry(base_date + datetime.timedelta(days=2), 1200000.0),
        ]

        self.mock_get.return_value = self._create_mock_response(tvl_data)

        result = get_tvl_dataset("test-protocol", "2025-01-01", "2025-01-03")

        self.assertEqual(len(result), 3)
        # Jan 1: raw data
        self.assertFalse(result[0]["is_interpolated"])
        self.assertEqual(result[0]["tvl"], 1000000.0)
        # Jan 2: interpolated (should be 1100000.0, midpoint)
        self.assertTrue(result[1]["is_interpolated"])
        self.assertAlmostEqual(result[1]["tvl"], 1100000.0, places=2)
        # Jan 3: raw data
        self.assertFalse(result[2]["is_interpolated"])
        self.assertEqual(result[2]["tvl"], 1200000.0)

    def test_forward_fill_at_start(self):
        """Test forward-fill when data is missing at the start of range (only one data point)"""
        # Data starts on Jan 2, but range starts on Jan 1
        # With only one data point, should fallback to simple forward-fill
        base_date = datetime.date(2025, 1, 2)
        tvl_data = [make_tvl_entry(base_date, 1000000.0)]

        self.mock_get.return_value = self._create_mock_response(tvl_data)

        result = get_tvl_dataset("test-protocol", "2025-01-01", "2025-01-02")

        self.assertEqual(len(result), 2)
        # Jan 1: forward-fill from Jan 2 (fallback with only 1 data point)
        self.assertTrue(result[0]["is_interpolated"])
        self.assertEqual(result[0]["tvl"], 1000000.0)
        # Jan 2: raw data
        self.assertFalse(result[1]["is_interpolated"])
        self.assertEqual(result[1]["tvl"], 1000000.0)

    def test_backward_fill_at_end(self):
        """Test backward-fill when data is missing at the end of range (only one data point)"""
        # Data ends on Jan 1, but range ends on Jan 2
        # With only one data point, should fallback to simple backward-fill
        base_date = datetime.date(2025, 1, 1)
        tvl_data = [make_tvl_entry(base_date, 1000000.0)]

        self.mock_get.return_value = self._create_mock_response(tvl_data)

        result = get_tvl_dataset("test-protocol", "2025-01-01", "2025-01-02")

        self.assertEqual(len(result), 2)
        # Jan 1: raw data
        self.assertFalse(result[0]["is_interpolated"])
        self.assertEqual(result[0]["tvl"], 1000000.0)
        # Jan 2: backward-fill from Jan 1 (fallback with only 1 data point)
        self.assertTrue(result[1]["is_interpolated"])
        self.assertEqual(result[1]["tvl"], 1000000.0)

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

        result = get_tvl_dataset("test-protocol", "2025-01-01", "2025-01-06")

        self.assertEqual(len(result), 6)
        # Jan 1: raw
        self.assertFalse(result[0]["is_interpolated"])
        # Jan 2: interpolated between Jan 1 (1M) and Jan 4 (1.3M) = 1.1M
        self.assertTrue(result[1]["is_interpolated"])
        self.assertAlmostEqual(result[1]["tvl"], 1100000.0, places=2)
        # Jan 3: interpolated = 1.2M
        self.assertTrue(result[2]["is_interpolated"])
        self.assertAlmostEqual(result[2]["tvl"], 1200000.0, places=2)
        # Jan 4: raw
        self.assertFalse(result[3]["is_interpolated"])
        # Jan 5: interpolated between Jan 4 (1.3M) and Jan 6 (1.5M) = 1.4M
        self.assertTrue(result[4]["is_interpolated"])
        self.assertAlmostEqual(result[4]["tvl"], 1400000.0, places=2)
        # Jan 6: raw
        self.assertFalse(result[5]["is_interpolated"])

    def test_no_data_in_range_error(self):
        """Test error when no data exists in the specified range"""
        # Data exists but outside the range
        base_date = datetime.date(2025, 2, 1)
        tvl_data = [make_tvl_entry(base_date, 1000000.0)]

        self.mock_get.return_value = self._create_mock_response(tvl_data)

        with self.assertRaises(ValueError) as context:
            get_tvl_dataset("test-protocol", "2025-01-01", "2025-01-31")

        self.assertIn("No TVL data available", str(context.exception))

    def test_api_error(self):
        """Test handling of API errors"""
        mock_response = mock.MagicMock()
        mock_response.status_code = 404
        self.mock_get.return_value = mock_response

        with self.assertRaises(ValueError) as context:
            get_tvl_dataset("test-protocol", "2024-01-01", "2024-01-31")

        self.assertIn("Error fetching data", str(context.exception))

    def test_empty_tvl_data(self):
        """Test error when API returns empty TVL data"""
        mock_response = mock.MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"tvl": []}
        self.mock_get.return_value = mock_response

        with self.assertRaises(ValueError) as context:
            get_tvl_dataset("test-protocol", "2024-01-01", "2024-01-31")

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
        dataset = get_tvl_dataset("test-protocol", "2025-01-01", "2025-01-03")

        # Verify structure suitable for CSV
        self.assertIsInstance(dataset, list)
        self.assertEqual(len(dataset), 3)
        for row in dataset:
            self.assertIn("date", row)
            self.assertIn("tvl", row)
            self.assertIn("is_interpolated", row)
            # Verify date format
            self.assertIsInstance(row["date"], str)
            # Verify TVL is numeric
            self.assertIsInstance(row["tvl"], (int, float))
            # Verify boolean flag
            self.assertIsInstance(row["is_interpolated"], bool)

    def test_dataset_format_for_json(self):
        """Test that dataset format is suitable for JSON output"""
        dataset = get_tvl_dataset("test-protocol", "2025-01-01", "2025-01-03")

        # Verify JSON serializable
        json_str = json.dumps(dataset)
        data = json.loads(json_str)

        # Check JSON structure
        self.assertIsInstance(data, list)
        self.assertEqual(len(data), 3)
        self.assertIn("date", data[0])
        self.assertIn("tvl", data[0])
        self.assertIn("is_interpolated", data[0])


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

        result = get_tvl_dataset("test-protocol", "2025-01-01", "2025-01-05", extrapolate=True)

        self.assertEqual(len(result), 5)
        
        # Slope between Jan 3 (1.1M) and Jan 5 (1.3M) = 100k per day
        # Jan 1: 1.1M - (2 days * 100k) = 900k
        self.assertTrue(result[0]["is_interpolated"])
        self.assertAlmostEqual(result[0]["tvl"], 900000.0, places=2)
        
        # Jan 2: 1.1M - (1 day * 100k) = 1M
        self.assertTrue(result[1]["is_interpolated"])
        self.assertAlmostEqual(result[1]["tvl"], 1000000.0, places=2)
        
        # Jan 3: raw data
        self.assertFalse(result[2]["is_interpolated"])
        self.assertEqual(result[2]["tvl"], 1100000.0)
        
        # Jan 4: interpolated between Jan 3 and Jan 5
        self.assertTrue(result[3]["is_interpolated"])
        self.assertAlmostEqual(result[3]["tvl"], 1200000.0, places=2)
        
        # Jan 5: raw data
        self.assertFalse(result[4]["is_interpolated"])
        self.assertEqual(result[4]["tvl"], 1300000.0)

    def test_forward_extrapolation_at_end(self):
        """Test forward extrapolation when data exists before range end"""
        # Data on Jan 1 and Jan 3, need to extrapolate forward to Jan 4-5
        base_date = datetime.date(2025, 1, 1)
        tvl_data = [
            make_tvl_entry(base_date, 1000000.0),  # Jan 1
            make_tvl_entry(base_date + datetime.timedelta(days=2), 1200000.0),  # Jan 3
        ]

        self.mock_get.return_value = self._create_mock_response(tvl_data)

        result = get_tvl_dataset("test-protocol", "2025-01-01", "2025-01-05", extrapolate=True)

        self.assertEqual(len(result), 5)
        
        # Jan 1: raw data
        self.assertFalse(result[0]["is_interpolated"])
        self.assertEqual(result[0]["tvl"], 1000000.0)
        
        # Jan 2: interpolated between Jan 1 and Jan 3
        self.assertTrue(result[1]["is_interpolated"])
        self.assertAlmostEqual(result[1]["tvl"], 1100000.0, places=2)
        
        # Jan 3: raw data
        self.assertFalse(result[2]["is_interpolated"])
        self.assertEqual(result[2]["tvl"], 1200000.0)
        
        # Slope between Jan 1 (1M) and Jan 3 (1.2M) = 100k per day
        # Jan 4: 1.2M + (1 day * 100k) = 1.3M
        self.assertTrue(result[3]["is_interpolated"])
        self.assertAlmostEqual(result[3]["tvl"], 1300000.0, places=2)
        
        # Jan 5: 1.2M + (2 days * 100k) = 1.4M
        self.assertTrue(result[4]["is_interpolated"])
        self.assertAlmostEqual(result[4]["tvl"], 1400000.0, places=2)

    def test_no_extrapolate_skips_start_dates(self):
        """Test that no_extrapolate=True skips dates at the start"""
        # Data on Jan 3 and Jan 5, range from Jan 1-5
        base_date = datetime.date(2025, 1, 3)
        tvl_data = [
            make_tvl_entry(base_date, 1100000.0),  # Jan 3
            make_tvl_entry(base_date + datetime.timedelta(days=2), 1300000.0),  # Jan 5
        ]

        self.mock_get.return_value = self._create_mock_response(tvl_data)

        result = get_tvl_dataset("test-protocol", "2025-01-01", "2025-01-05", extrapolate=False)

        # Should only have Jan 3, 4, 5 (Jan 1-2 are skipped)
        self.assertEqual(len(result), 3)
        self.assertEqual(result[0]["date"], "2025-01-03")
        self.assertEqual(result[1]["date"], "2025-01-04")
        self.assertEqual(result[2]["date"], "2025-01-05")

    def test_no_extrapolate_skips_end_dates(self):
        """Test that no_extrapolate=True skips dates at the end"""
        # Data on Jan 1 and Jan 3, range from Jan 1-5
        base_date = datetime.date(2025, 1, 1)
        tvl_data = [
            make_tvl_entry(base_date, 1000000.0),  # Jan 1
            make_tvl_entry(base_date + datetime.timedelta(days=2), 1200000.0),  # Jan 3
        ]

        self.mock_get.return_value = self._create_mock_response(tvl_data)

        result = get_tvl_dataset("test-protocol", "2025-01-01", "2025-01-05", extrapolate=False)

        # Should only have Jan 1, 2, 3 (Jan 4-5 are skipped)
        self.assertEqual(len(result), 3)
        self.assertEqual(result[0]["date"], "2025-01-01")
        self.assertEqual(result[1]["date"], "2025-01-02")
        self.assertEqual(result[2]["date"], "2025-01-03")

    def test_extrapolation_with_negative_slope(self):
        """Test extrapolation with decreasing TVL"""
        # Data on Jan 1 and Jan 3 with decreasing TVL, extrapolate to Jan 4-5
        base_date = datetime.date(2025, 1, 1)
        tvl_data = [
            make_tvl_entry(base_date, 1200000.0),  # Jan 1
            make_tvl_entry(base_date + datetime.timedelta(days=2), 1000000.0),  # Jan 3
        ]

        self.mock_get.return_value = self._create_mock_response(tvl_data)

        result = get_tvl_dataset("test-protocol", "2025-01-01", "2025-01-05", extrapolate=True)

        self.assertEqual(len(result), 5)
        
        # Slope between Jan 1 (1.2M) and Jan 3 (1M) = -100k per day
        # Jan 4: 1M + (1 day * -100k) = 900k
        self.assertTrue(result[3]["is_interpolated"])
        self.assertAlmostEqual(result[3]["tvl"], 900000.0, places=2)
        
        # Jan 5: 1M + (2 days * -100k) = 800k
        self.assertTrue(result[4]["is_interpolated"])
        self.assertAlmostEqual(result[4]["tvl"], 800000.0, places=2)

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
        
        # Without extrapolation (should have 3 days: Jan 3, 4, 5)
        # Jan 3 = 1.1M (raw), Jan 4 = 1.2M (interpolated), Jan 5 = 1.3M (raw)
        # Average = (1.1M + 1.2M + 1.3M) / 3 = 3.6M / 3 = 1.2M
        avg_without = get_average_tvl("test-protocol", "2025-01-01", "2025-01-05", extrapolate=False)
        
        # Averages should be different
        self.assertNotEqual(avg_with, avg_without)
        
        # With extrapolation average should be 1.1M
        self.assertAlmostEqual(avg_with, 1100000.0, places=2)
        
        # Without extrapolation should be 1.2M
        self.assertAlmostEqual(avg_without, 1200000.0, places=2)


if __name__ == "__main__":
    unittest.main()
