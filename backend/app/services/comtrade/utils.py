import os
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple, Union

def detect_encoding(filepath: Union[str, Path]) -> Optional[str]:
    """
    Detect file encoding
    
    Args:
        filepath: Path to file
        
    Returns:
        Optional[str]: Detected encoding or None for default
    """
    try:
        with open(filepath, 'r') as f:
            f.read()
            return None
    except UnicodeDecodeError:
        return 'utf-8'

def parse_timestamp(timestamp_str: str, revision_year: str) -> Tuple[datetime, bool]:
    """
    Parse COMTRADE timestamp string
    
    Args:
        timestamp_str: Timestamp string
        revision_year: COMTRADE revision year
        
    Returns:
        Tuple[datetime, bool]: Parsed timestamp and nanosecond flag
    """
    import re
    
    RE_DATE = re.compile(r"([0-9]{1,2})/([0-9]{1,2})/([0-9]{2,4})")
    RE_TIME = re.compile(r"([0-9]{1,2}):([0-9]{2}):([0-9]{2})(\.([0-9]{1,12}))?")
    
    if not timestamp_str.strip():
        return datetime.min, False

    date_str, time_str = [x.strip() for x in timestamp_str.split(',')][:2]
    
    # Parse date
    date_match = RE_DATE.match(date_str)
    if not date_match:
        return datetime.min, False
        
    if revision_year == "1991":
        month, day, year = map(int, date_match.groups())
    else:
        day, month, year = map(int, date_match.groups())
        
    if year < 100:
        year += 2000 if year < 70 else 1900
        
    # Parse time
    time_match = RE_TIME.match(time_str)
    if not time_match:
        return datetime(year, month, day), False
        
    hour = int(time_match.group(1))
    minute = int(time_match.group(2))
    second = int(time_match.group(3))
    frac_str = time_match.group(5) or "0"
    
    # Handle precision
    uses_nanoseconds = len(frac_str) > 6
    if uses_nanoseconds:
        microsecond = int(int(frac_str.ljust(9, '0')) * 1E-3)
    else:
        microsecond = int(frac_str.ljust(6, '0'))
    
    return datetime(year, month, day, hour, minute, second, microsecond), uses_nanoseconds

def calculate_timestamp(sample_number: int, timestamp_value: float,
                      time_base: float, time_mult: float,
                      sample_rate: float) -> float:
    """
    Calculate timestamp for a sample
    
    Args:
        sample_number: Sample number (1-based)
        timestamp_value: Raw timestamp value
        time_base: Time base value
        time_mult: Time multiplier
        sample_rate: Sample rate in Hz
        
    Returns:
        float: Calculated timestamp in seconds
    """
    if timestamp_value == 0xFFFFFFFF:  # Missing timestamp
        if sample_rate == 0:
            raise ValueError("Missing timestamp and no sample rate provided")
        return (sample_number - 1) / sample_rate
        
    return timestamp_value * time_base * time_mult