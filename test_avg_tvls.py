import datetime
import json
import os
import sys
import unittest
from unittest import mock

# Add parent directory to path to import avg_tvls
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from avg_tvls import _find_nearest_dates, get_average_tvl, get_tvl_dataset


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
        base_date = datetime.date(2024, 1, 1)
        tvl_data = [
            {
                "date": int(
                    datetime.datetime.combine(
                        base_date + datetime.timedelta(days=i),
                        datetime.time.min,
                        tzinfo=datetime.timezone.utc,
                    ).timestamp()
                ),
                "totalLiquidityUSD": 1000000.0 + (i * 100000),
            }
            for i in range(3)
        ]

        self.mock_get.return_value = self._create_mock_response(tvl_data)

        result = get_tvl_dataset("test-protocol", "2024-01-01", "2024-01-03")

        self.assertEqual(len(result), 3)
        self.assertFalse(any(row["is_interpolated"] for row in result))
        self.assertEqual(result[0]["tvl"], 1000000.0)
        self.assertEqual(result[1]["tvl"], 1100000.0)
        self.assertEqual(result[2]["tvl"], 1200000.0)

    def test_linear_interpolation_between_points(self):
        """Test linear interpolation between two data points"""
        # Data on Jan 1 and Jan 3, missing Jan 2
        base_date = datetime.date(2024, 1, 1)
        tvl_data = [
            {
                "date": int(
                    datetime.datetime.combine(
                        base_date, datetime.time.min, tzinfo=datetime.timezone.utc
                    ).timestamp()
                ),
                "totalLiquidityUSD": 1000000.0,
            },
            {
                "date": int(
                    datetime.datetime.combine(
                        base_date + datetime.timedelta(days=2),
                        datetime.time.min,
                        tzinfo=datetime.timezone.utc,
                    ).timestamp()
                ),
                "totalLiquidityUSD": 1200000.0,
            },
        ]

        self.mock_get.return_value = self._create_mock_response(tvl_data)

        result = get_tvl_dataset("test-protocol", "2024-01-01", "2024-01-03")

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
        """Test forward-fill when data is missing at the start of range"""
        # Data starts on Jan 2, but range starts on Jan 1
        base_date = datetime.date(2024, 1, 2)
        tvl_data = [
            {
                "date": int(
                    datetime.datetime.combine(
                        base_date, datetime.time.min, tzinfo=datetime.timezone.utc
                    ).timestamp()
                ),
                "totalLiquidityUSD": 1000000.0,
            }
        ]

        self.mock_get.return_value = self._create_mock_response(tvl_data)

        result = get_tvl_dataset("test-protocol", "2024-01-01", "2024-01-02")

        self.assertEqual(len(result), 2)
        # Jan 1: forward-fill from Jan 2
        self.assertTrue(result[0]["is_interpolated"])
        self.assertEqual(result[0]["tvl"], 1000000.0)
        # Jan 2: raw data
        self.assertFalse(result[1]["is_interpolated"])
        self.assertEqual(result[1]["tvl"], 1000000.0)

    def test_backward_fill_at_end(self):
        """Test backward-fill when data is missing at the end of range"""
        # Data ends on Jan 1, but range ends on Jan 2
        base_date = datetime.date(2024, 1, 1)
        tvl_data = [
            {
                "date": int(
                    datetime.datetime.combine(
                        base_date, datetime.time.min, tzinfo=datetime.timezone.utc
                    ).timestamp()
                ),
                "totalLiquidityUSD": 1000000.0,
            }
        ]

        self.mock_get.return_value = self._create_mock_response(tvl_data)

        result = get_tvl_dataset("test-protocol", "2024-01-01", "2024-01-02")

        self.assertEqual(len(result), 2)
        # Jan 1: raw data
        self.assertFalse(result[0]["is_interpolated"])
        self.assertEqual(result[0]["tvl"], 1000000.0)
        # Jan 2: backward-fill from Jan 1
        self.assertTrue(result[1]["is_interpolated"])
        self.assertEqual(result[1]["tvl"], 1000000.0)

    def test_complex_interpolation_scenario(self):
        """Test a complex scenario with multiple gaps"""
        # Data on Jan 1, Jan 4, Jan 6; missing Jan 2, 3, 5
        base_date = datetime.date(2024, 1, 1)
        tvl_data = [
            {
                "date": int(
                    datetime.datetime.combine(
                        base_date, datetime.time.min, tzinfo=datetime.timezone.utc
                    ).timestamp()
                ),
                "totalLiquidityUSD": 1000000.0,
            },
            {
                "date": int(
                    datetime.datetime.combine(
                        base_date + datetime.timedelta(days=3),
                        datetime.time.min,
                        tzinfo=datetime.timezone.utc,
                    ).timestamp()
                ),
                "totalLiquidityUSD": 1300000.0,
            },
            {
                "date": int(
                    datetime.datetime.combine(
                        base_date + datetime.timedelta(days=5),
                        datetime.time.min,
                        tzinfo=datetime.timezone.utc,
                    ).timestamp()
                ),
                "totalLiquidityUSD": 1500000.0,
            },
        ]

        self.mock_get.return_value = self._create_mock_response(tvl_data)

        result = get_tvl_dataset("test-protocol", "2024-01-01", "2024-01-06")

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
        base_date = datetime.date(2024, 2, 1)
        tvl_data = [
            {
                "date": int(
                    datetime.datetime.combine(
                        base_date, datetime.time.min, tzinfo=datetime.timezone.utc
                    ).timestamp()
                ),
                "totalLiquidityUSD": 1000000.0,
            }
        ]

        self.mock_get.return_value = self._create_mock_response(tvl_data)

        with self.assertRaises(ValueError) as context:
            get_tvl_dataset("test-protocol", "2024-01-01", "2024-01-31")

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
        target = datetime.date(2024, 1, 3)
        available = [
            datetime.date(2024, 1, 1),
            datetime.date(2024, 1, 2),
            datetime.date(2024, 1, 4),
            datetime.date(2024, 1, 5),
        ]

        prev, next_date = _find_nearest_dates(target, available)

        self.assertEqual(prev, datetime.date(2024, 1, 2))
        self.assertEqual(next_date, datetime.date(2024, 1, 4))

    def test_find_only_previous(self):
        """Test when only previous date exists"""
        target = datetime.date(2024, 1, 5)
        available = [
            datetime.date(2024, 1, 1),
            datetime.date(2024, 1, 2),
            datetime.date(2024, 1, 3),
        ]

        prev, next_date = _find_nearest_dates(target, available)

        self.assertEqual(prev, datetime.date(2024, 1, 3))
        self.assertIsNone(next_date)

    def test_find_only_next(self):
        """Test when only next date exists"""
        target = datetime.date(2024, 1, 1)
        available = [
            datetime.date(2024, 1, 3),
            datetime.date(2024, 1, 4),
            datetime.date(2024, 1, 5),
        ]

        prev, next_date = _find_nearest_dates(target, available)

        self.assertIsNone(prev)
        self.assertEqual(next_date, datetime.date(2024, 1, 3))

    def test_target_equals_available_date(self):
        """Test when target equals an available date"""
        target = datetime.date(2024, 1, 2)
        available = [
            datetime.date(2024, 1, 1),
            datetime.date(2024, 1, 2),
            datetime.date(2024, 1, 3),
        ]

        prev, next_date = _find_nearest_dates(target, available)

        # Should find the target itself as previous, and the next one
        self.assertEqual(prev, datetime.date(2024, 1, 2))
        self.assertEqual(next_date, datetime.date(2024, 1, 3))


class TestAverageTVL(unittest.TestCase):
    """Test the get_average_tvl function (backward compatibility)"""

    def setUp(self):
        self.mock_response_patcher = mock.patch("avg_tvls.requests.get")
        self.mock_get = self.mock_response_patcher.start()

    def tearDown(self):
        self.mock_response_patcher.stop()

    def test_average_calculation(self):
        """Test that average is calculated correctly"""
        base_date = datetime.date(2024, 1, 1)
        tvl_data = [
            {
                "date": int(
                    datetime.datetime.combine(
                        base_date + datetime.timedelta(days=i),
                        datetime.time.min,
                        tzinfo=datetime.timezone.utc,
                    ).timestamp()
                ),
                "totalLiquidityUSD": 1000000.0 + (i * 100000),
            }
            for i in range(3)
        ]

        mock_response = mock.MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"tvl": tvl_data}
        self.mock_get.return_value = mock_response

        avg = get_average_tvl("test-protocol", "2024-01-01", "2024-01-03")

        # Average of 1M, 1.1M, 1.2M = 1.1M
        self.assertAlmostEqual(avg, 1100000.0, places=2)

    def test_average_with_interpolation(self):
        """Test that average includes interpolated values"""
        # Data on Jan 1 and Jan 3, missing Jan 2
        base_date = datetime.date(2024, 1, 1)
        tvl_data = [
            {
                "date": int(
                    datetime.datetime.combine(
                        base_date, datetime.time.min, tzinfo=datetime.timezone.utc
                    ).timestamp()
                ),
                "totalLiquidityUSD": 1000000.0,
            },
            {
                "date": int(
                    datetime.datetime.combine(
                        base_date + datetime.timedelta(days=2),
                        datetime.time.min,
                        tzinfo=datetime.timezone.utc,
                    ).timestamp()
                ),
                "totalLiquidityUSD": 1200000.0,
            },
        ]

        mock_response = mock.MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"tvl": tvl_data}
        self.mock_get.return_value = mock_response

        avg = get_average_tvl("test-protocol", "2024-01-01", "2024-01-03")

        # Average of 1M, 1.1M (interpolated), 1.2M = 1.1M
        self.assertAlmostEqual(avg, 1100000.0, places=2)


class TestCLIOutput(unittest.TestCase):
    """Test CLI output formats - simplified to test data formatting"""

    def setUp(self):
        self.mock_response_patcher = mock.patch("avg_tvls.requests.get")
        self.mock_get = self.mock_response_patcher.start()

        # Set up mock data
        base_date = datetime.date(2024, 1, 1)
        tvl_data = [
            {
                "date": int(
                    datetime.datetime.combine(
                        base_date + datetime.timedelta(days=i),
                        datetime.time.min,
                        tzinfo=datetime.timezone.utc,
                    ).timestamp()
                ),
                "totalLiquidityUSD": 1000000.0 + (i * 100000),
            }
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
        dataset = get_tvl_dataset("test-protocol", "2024-01-01", "2024-01-03")

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
        dataset = get_tvl_dataset("test-protocol", "2024-01-01", "2024-01-03")

        # Verify JSON serializable
        json_str = json.dumps(dataset)
        data = json.loads(json_str)

        # Check JSON structure
        self.assertIsInstance(data, list)
        self.assertEqual(len(data), 3)
        self.assertIn("date", data[0])
        self.assertIn("tvl", data[0])
        self.assertIn("is_interpolated", data[0])


if __name__ == "__main__":
    unittest.main()
