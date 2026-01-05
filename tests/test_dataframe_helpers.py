"""
Tests for DataFrame helper functions
"""

import pytest
import pandas as pd
from src.utils.dataframe_helpers import (
    get_latest_values,
    get_latest_value,
    get_latest_n_values
)


class TestDataFrameHelpers:
    """Tests for DataFrame helper functions"""
    
    def test_get_latest_values(self):
        """Test get_latest_values function"""
        df = pd.DataFrame({
            'close': [100, 101, 102, 103, 104]
        })
        latest_rows = get_latest_values(df, n=2)
        assert len(latest_rows) == 2
        assert latest_rows[0] is not None
        assert latest_rows[1] is not None
        # Latest row (index 0) should be the last row of DataFrame (104)
        # Previous row (index 1) should be second to last (103)
        assert latest_rows[0]['close'] == 104  # Last row
        assert latest_rows[1]['close'] == 103   # Second to last
    
    def test_get_latest_values_empty(self):
        """Test get_latest_values with empty DataFrame"""
        df = pd.DataFrame()
        latest_rows = get_latest_values(df, n=2)
        assert len(latest_rows) == 2
        assert latest_rows[0] is None
        assert latest_rows[1] is None
    
    def test_get_latest_value(self):
        """Test get_latest_value function"""
        df = pd.DataFrame({
            'close': [100, 101, 102]
        })
        value = get_latest_value(df, 'close')
        assert value == 102
    
    def test_get_latest_value_default(self):
        """Test get_latest_value with default"""
        df = pd.DataFrame()
        value = get_latest_value(df, 'close', default=0.0)
        assert value == 0.0
    
    def test_get_latest_n_values(self):
        """Test get_latest_n_values function"""
        df = pd.DataFrame({
            'close': [100, 101, 102, 103, 104]
        })
        values = get_latest_n_values(df, 'close', n=3)
        assert len(values) == 3
        assert values == [102, 103, 104]
