import pytest
from app import get_domingos_mes, format_data_br

def test_get_domingos_mes():
    # Test for February 2024 (Leap year, ends on Thursday, Sundays on 4, 11, 18, 25)
    domingos = get_domingos_mes(2024, 2)
    assert len(domingos) == 4
    assert domingos[0] == {"iso": "2024-02-04", "br": "04/02/2024"}
    assert domingos[-1] == {"iso": "2024-02-25", "br": "25/02/2024"}

    # Test for March 2024 (Sundays on 3, 10, 17, 24, 31)
    domingos = get_domingos_mes(2024, 3)
    assert len(domingos) == 5
    assert domingos[0]["iso"] == "2024-03-03"
    assert domingos[-1]["iso"] == "2024-03-31"

def test_format_data_br():
    # Test valid ISO date
    assert format_data_br("2024-05-20") == "20/05/2024"
    
    # Test invalid length
    assert format_data_br("2024-05") == "2024-05"
    
    # Test None
    assert format_data_br(None) is None
    
    # Test empty string
    assert format_data_br("") == ""
    
    # Test non-iso format with dashes but wrong order
    # Current implementation: if len == 10 and 3 parts, it flips it.
    # "20-05-2024" -> "2024/05/20"
    assert format_data_br("20-05-2024") == "2024/05/20"
