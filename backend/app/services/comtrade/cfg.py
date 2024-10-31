"""
cfg.py
Configuration file parser for COMTRADE files.

This module handles parsing and storage of COMTRADE configuration (CFG) files,
implementing the IEEE Std C37.111 specification.
"""

import datetime as dt
import io
import os
import re
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, TextIO, Tuple, Union

from .base import (
    AnalogChannel,
    ComtradeRevision,
    DataFormat,
    StatusChannel,
    TimeBase
)
from .exceptions import CfgValidationError

@dataclass
class SamplingRate:
    """Sampling rate information"""
    rate: float
    end_sample: int

    def __str__(self) -> str:
        return f"Sample rate of {self.rate} Hz to sample #{self.end_sample}"

@dataclass
class CfgTimingInfo:
    """Timing-related configuration data"""
    frequency: float = 60.0
    nrates: int = 1
    sample_rates: List[SamplingRate] = None
    start_timestamp: dt.datetime = None
    trigger_timestamp: dt.datetime = None
    time_multiplier: float = 1.0
    # 2013 standard specific
    time_code: int = 0
    local_code: int = 0
    tmq_code: int = 0
    leap_second: int = 0

    def __post_init__(self):
        if self.sample_rates is None:
            self.sample_rates = []
        if self.start_timestamp is None:
            self.start_timestamp = dt.datetime(1900, 1, 1)
        if self.trigger_timestamp is None:
            self.trigger_timestamp = dt.datetime(1900, 1, 1)

class Cfg:
    """Parser and container for COMTRADE configuration data"""

    # Regular expressions for parsing
    _RE_DATE = re.compile(r"([0-9]{1,2})/([0-9]{1,2})/([0-9]{2,4})")
    _RE_TIME = re.compile(r"([0-9]{1,2}):([0-9]{2}):([0-9]{2})(\.([0-9]{1,12}))?")
    
    def __init__(self, ignore_warnings: bool = False):
        """
        Initialize CFG parser
        
        Args:
            ignore_warnings: Whether to suppress warning messages
        """
        self.ignore_warnings = ignore_warnings
        self.filepath: Optional[Path] = None
        
        # Base configuration
        self._time_base = TimeBase.MICROSEC
        self._station_name = ""
        self._rec_dev_id = ""
        self._rev_year = ComtradeRevision.REV_2013.value
        
        # Channel configuration
        self._channels_count = 0
        self._analog_channels: List[AnalogChannel] = []
        self._status_channels: List[StatusChannel] = []
        self._analog_count = 0
        self._status_count = 0
        
        # Timing information
        self._timing = CfgTimingInfo()
        
        # File format
        self._data_format = DataFormat.ASCII
        self.timestamp_critical = False

    @property
    def station_name(self) -> str:
        """Recording device's station name"""
        return self._station_name

    @property
    def rec_dev_id(self) -> str:
        """Recording device ID"""
        return self._rec_dev_id

    @property
    def rev_year(self) -> str:
        """COMTRADE revision year"""
        return self._rev_year

    @property
    def channels_count(self) -> int:
        """Total number of channels"""
        return self._channels_count

    @property
    def analog_channels(self) -> List[AnalogChannel]:
        """List of analog channel descriptions"""
        return self._analog_channels

    @property
    def status_channels(self) -> List[StatusChannel]:
        """List of status channel descriptions"""
        return self._status_channels

    @property
    def analog_count(self) -> int:
        """Number of analog channels"""
        return self._analog_count

    @property
    def status_count(self) -> int:
        """Number of status channels"""
        return self._status_count

    @property
    def time_base(self) -> float:
        """Time base for timestamps"""
        return self._time_base

    @property
    def frequency(self) -> float:
        """System frequency in Hz"""
        return self._timing.frequency

    @property
    def ft(self) -> str:
        """Data file format"""
        return self._data_format.name

    @property
    def timemult(self) -> float:
        """Time multiplier"""
        return self._timing.time_multiplier

    @property
    def start_timestamp(self) -> dt.datetime:
        """Recording start timestamp"""
        return self._timing.start_timestamp

    @property
    def trigger_timestamp(self) -> dt.datetime:
        """Trigger timestamp"""
        return self._timing.trigger_timestamp

    @property
    def nrates(self) -> int:
        """Number of different sampling rates"""
        return self._timing.nrates

    @property
    def sample_rates(self) -> List[Tuple[float, int]]:
        """List of sampling rates and their end sample numbers"""
        return [(rate.rate, rate.end_sample) for rate in self._timing.sample_rates]

    def load(self, filepath: str, **kwargs) -> None:
        """
        Load and parse a CFG file
        
        Args:
            filepath: Path to CFG file
            **kwargs: Additional options (e.g., encoding)
        """
        self.filepath = Path(filepath)
        if not self.filepath.exists():
            raise FileNotFoundError(f"CFG file not found: {filepath}")

        encoding = kwargs.get('encoding', self._detect_encoding())
        with open(self.filepath, 'r', encoding=encoding) as cfg_file:
            self._parse_cfg_content(cfg_file)

    def read(self, cfg_content: Union[str, TextIO]) -> None:
        """
        Read CFG content from string or file object
        
        Args:
            cfg_content: CFG content to parse
        """
        if isinstance(cfg_content, str):
            self._parse_cfg_content(io.StringIO(cfg_content))
        else:
            self._parse_cfg_content(cfg_content)

    def _parse_cfg_content(self, cfg_file: TextIO) -> None:
        """
        Parse CFG file contents
        
        Args:
            cfg_file: File object containing CFG data
        """
        self._parse_header(cfg_file)
        self._parse_channel_counts(cfg_file)
        self._parse_analog_channels(cfg_file)
        self._parse_status_channels(cfg_file)
        self._parse_frequency(cfg_file)
        self._parse_sampling_rates(cfg_file)
        self._parse_timestamps(cfg_file)
        self._parse_file_format(cfg_file)
        
        if self._rev_year in (ComtradeRevision.REV_1999.value, ComtradeRevision.REV_2013.value):
            self._parse_time_multiplier(cfg_file)
            
        if self._rev_year == ComtradeRevision.REV_2013.value:
            self._parse_time_codes(cfg_file)

    def _parse_header(self, cfg_file: TextIO) -> None:
        """Parse station name, device ID, and revision"""
        line = self._read_line(cfg_file)
        parts = [part.strip() for part in line.split(',')]
        
        if len(parts) == 3:
            self._station_name, self._rec_dev_id, rev_year = parts
            if not ComtradeRevision.is_valid(rev_year):
                if not self.ignore_warnings:
                    warnings.warn(f"Unknown standard revision '{rev_year}'")
            self._rev_year = rev_year
        elif len(parts) == 2:
            self._station_name, self._rec_dev_id = parts
            self._rev_year = ComtradeRevision.REV_1991.value
        else:
            raise CfgValidationError("Invalid header format")

    def _parse_channel_counts(self, cfg_file: TextIO) -> None:
        """Parse total, analog, and status channel counts"""
        line = self._read_line(cfg_file)
        parts = [part.strip() for part in line.split(',')]
        
        if len(parts) < 3:
            raise CfgValidationError("Invalid channel count format")
            
        try:
            self._channels_count = int(parts[0])
            self._analog_count = int(parts[1].rstrip('A'))
            self._status_count = int(parts[2].rstrip('D'))
        except ValueError as e:
            raise CfgValidationError(f"Invalid channel count values: {str(e)}")

    def _parse_analog_channels(self, cfg_file: TextIO) -> None:
        """Parse analog channel configurations"""
        self._analog_channels = []
        for _ in range(self._analog_count):
            line = self._read_line(cfg_file)
            parts = [part.strip() for part in line.split(',')]
            
            if len(parts) < 13:
                parts.extend(['0'] * (13 - len(parts)))
                
            try:
                channel = AnalogChannel(
                    number=int(parts[0]),
                    name=parts[1],
                    phase=parts[2],
                    circuit_component=parts[3],
                    units=parts[4],
                    multiplier=float(parts[5]),
                    offset=float(parts[6] or 0),
                    skew=float(parts[7] or 0),
                    min_value=float(parts[8]),
                    max_value=float(parts[9]),
                    primary=float(parts[10]),
                    secondary=float(parts[11]),
                    ps_ratio=parts[12]
                )
                self._analog_channels.append(channel)
            except (ValueError, IndexError) as e:
                raise CfgValidationError(f"Invalid analog channel format: {str(e)}")

    def _parse_status_channels(self, cfg_file: TextIO) -> None:
        """Parse status channel configurations"""
        self._status_channels = []
        for _ in range(self._status_count):
            line = self._read_line(cfg_file)
            parts = [part.strip() for part in line.split(',')]
            
            if len(parts) < 5:
                parts.extend(['0'] * (5 - len(parts)))
                
            try:
                channel = StatusChannel(
                    number=int(parts[0]),
                    name=parts[1],
                    phase=parts[2],
                    circuit_component=parts[3],
                    initial_value=int(parts[4] or 0)
                )
                self._status_channels.append(channel)
            except (ValueError, IndexError) as e:
                raise CfgValidationError(f"Invalid status channel format: {str(e)}")

    def _parse_frequency(self, cfg_file: TextIO) -> None:
        """Parse line frequency"""
        line = self._read_line(cfg_file)
        try:
            self._timing.frequency = float(line) if line.strip() else 60.0
        except ValueError as e:
            raise CfgValidationError(f"Invalid frequency value: {str(e)}")

    def _parse_sampling_rates(self, cfg_file: TextIO) -> None:
        """Parse sampling rate information"""
        line = self._read_line(cfg_file)
        try:
            self._timing.nrates = int(line)
            if self._timing.nrates == 0:
                self._timing.nrates = 1
                self.timestamp_critical = True
            else:
                self.timestamp_critical = False
        except ValueError as e:
            raise CfgValidationError(f"Invalid number of rates: {str(e)}")

        self._timing.sample_rates = []
        for _ in range(self._timing.nrates):
            line = self._read_line(cfg_file)
            parts = [part.strip() for part in line.split(',')]
            
            try:
                rate = float(parts[0])
                end_sample = int(parts[1])
                self._timing.sample_rates.append(SamplingRate(rate, end_sample))
            except (ValueError, IndexError) as e:
                raise CfgValidationError(f"Invalid sampling rate format: {str(e)}")

    def _parse_timestamps(self, cfg_file: TextIO) -> None:
        """Parse start and trigger timestamps"""
        # Start timestamp
        start_ts, start_nano = self._parse_timestamp(self._read_line(cfg_file))
        self._timing.start_timestamp = start_ts
        self._time_base = TimeBase.get_time_base(start_nano)

        # Trigger timestamp
        trigger_ts, trigger_nano = self._parse_timestamp(self._read_line(cfg_file))
        self._timing.trigger_timestamp = trigger_ts
        self._time_base = min(self._time_base, TimeBase.get_time_base(trigger_nano))

    def _parse_timestamp(self, line: str) -> Tuple[dt.datetime, bool]:
        """Parse timestamp string"""
        if not line.strip():
            return dt.datetime(1900, 1, 1), False

        parts = [part.strip() for part in line.split(',')]
        if len(parts) < 2:
            return dt.datetime(1900, 1, 1), False

        date_str, time_str = parts[0:2]
        
        # Parse date
        date_match = self._RE_DATE.match(date_str)
        if not date_match:
            return dt.datetime(1900, 1, 1), False
            
        if self._rev_year == ComtradeRevision.REV_1991.value:
            month, day, year = map(int, date_match.groups())
        else:
            day, month, year = map(int, date_match.groups())
            
        if year < 100:  # Two-digit year
            year += 2000 if year < 70 else 1900
            
        # Parse time
        time_match = self._RE_TIME.match(time_str)
        if not time_match:
            return dt.datetime(year, month, day), False
            
        hour = int(time_match.group(1))
        minute = int(time_match.group(2))
        second = int(time_match.group(3))
        frac_str = time_match.group(5) or "0"
        
        # Handle precision
        nanoseconds = False
        if len(frac_str) <= 6:
            microsecond = int(frac_str.ljust(6, '0'))
        else:
            nanoseconds = True
            microsecond = int(int(frac_str.ljust(9, '0')) * 1E-3)
            if not self.ignore_warnings:
                warnings.warn("Nanosecond precision truncated to microseconds")
        
        return dt.datetime(year, month, day, hour, minute, second, microsecond), nanoseconds

    def _parse_file_format(self, cfg_file: TextIO) -> None:
        """Parse data file format"""
        line = self._read_line(cfg_file)
        try:
            self._data_format = DataFormat.from_string(line.strip())
        except ValueError as e:
            raise CfgValidationError(f"Invalid file format: {str(e)}")

    def _parse_time_multiplier(self, cfg_file: TextIO) -> None:
        """
        Parse time multiplier (1999 and 2013 standards)
        
        Args:
            cfg_file: File object containing CFG data
        """
        line = self._read_line(cfg_file)
        try:
            self._timing.time_multiplier = float(line) if line.strip() else 1.0
        except ValueError as e:
            raise CfgValidationError(f"Invalid time multiplier: {str(e)}")

    def _parse_time_codes(self, cfg_file: TextIO) -> None:
        """
        Parse time code information (2013 standard)
        
        Args:
            cfg_file: File object containing CFG data
        """
        # Time and local code
        line = self._read_line(cfg_file)
        if not line:
            return
            
        parts = [part.strip() for part in line.split(',')]
        if len(parts) >= 2:
            try:
                self._timing.time_code = int(parts[0])
                self._timing.local_code = int(parts[1])
            except ValueError as e:
                raise CfgValidationError(f"Invalid time/local code: {str(e)}")

        # Time quality and leap second
        line = self._read_line(cfg_file)
        if not line:
            return
            
        parts = [part.strip() for part in line.split(',')]
        if len(parts) >= 2:
            try:
                self._timing.tmq_code = int(parts[0])
                self._timing.leap_second = int(parts[1])
            except ValueError as e:
                raise CfgValidationError(f"Invalid time quality/leap second: {str(e)}")

    def _read_line(self, cfg_file: TextIO) -> str:
        """
        Read and return a line from the CFG file
        
        Args:
            cfg_file: File object to read from
            
        Returns:
            str: Line content
            
        Raises:
            CfgValidationError: If EOF is reached unexpectedly
        """
        line = cfg_file.readline()
        if not line:
            raise CfgValidationError("Unexpected end of CFG file")
        return line.strip()

    def _detect_encoding(self) -> Optional[str]:
        """
        Detect file encoding
        
        Returns:
            Optional[str]: Detected encoding or None for default
        """
        if not self.filepath:
            return None
            
        try:
            with open(self.filepath, 'r') as file:
                file.read()
                return None
        except UnicodeDecodeError:
            return 'utf-8'

    def validate(self) -> bool:
        """
        Validate CFG data
        
        Returns:
            bool: True if validation passes
            
        Raises:
            CfgValidationError: If validation fails
        """
        # Check required fields
        if not self._station_name or not self._rec_dev_id:
            raise CfgValidationError("Missing station name or device ID")

        # Validate channel counts
        if self._channels_count != (self._analog_count + self._status_count):
            raise CfgValidationError("Channel count mismatch")

        # Validate channel numbers
        for channel in self._analog_channels:
            if channel.number < 1 or channel.number > self._analog_count:
                raise CfgValidationError(f"Invalid analog channel number: {channel.number}")

        for channel in self._status_channels:
            if channel.number < 1 or channel.number > self._status_count:
                raise CfgValidationError(f"Invalid status channel number: {channel.number}")

        # Validate sampling rates
        if not self._timing.sample_rates:
            raise CfgValidationError("No sampling rates defined")

        prev_end = 0
        for rate in self._timing.sample_rates:
            if rate.rate <= 0:
                raise CfgValidationError(f"Invalid sampling rate: {rate.rate}")
            if rate.end_sample <= prev_end:
                raise CfgValidationError("Invalid sampling rate end sample")
            prev_end = rate.end_sample

        return True

    def get_channel_info(self, channel_type: str, number: int) -> Optional[Union[AnalogChannel, StatusChannel]]:
        """
        Get channel information by type and number
        
        Args:
            channel_type: Type of channel ('A' for analog, 'D' for status)
            number: Channel number
            
        Returns:
            Optional[Union[AnalogChannel, StatusChannel]]: Channel information or None if not found
        """
        if channel_type.upper() == 'A':
            for channel in self._analog_channels:
                if channel.number == number:
                    return channel
        elif channel_type.upper() == 'D':
            for channel in self._status_channels:
                if channel.number == number:
                    return channel
        return None

    def to_string(self) -> str:
        """
        Convert CFG data to string format
        
        Returns:
            str: String representation of CFG data
        """
        lines = []
        
        # Header
        header = f"{self._station_name},{self._rec_dev_id}"
        if self._rev_year != ComtradeRevision.REV_1991.value:
            header = f"{header},{self._rev_year}"
        lines.append(header)
        
        # Channel counts
        lines.append(f"{self._channels_count},{self._analog_count}A,{self._status_count}D")
        
        # Analog channels
        for channel in self._analog_channels:
            lines.append(str(channel))
            
        # Status channels
        for channel in self._status_channels:
            lines.append(str(channel))
            
        # Frequency
        lines.append(str(self._timing.frequency))
        
        # Sampling rates
        lines.append(str(self._timing.nrates))
        for rate in self._timing.sample_rates:
            lines.append(f"{rate.rate},{rate.end_sample}")
            
        # Timestamps
        lines.append(self._format_timestamp(self._timing.start_timestamp))
        lines.append(self._format_timestamp(self._timing.trigger_timestamp))
        
        # File format
        lines.append(self._data_format.value)
        
        # Time multiplier (1999 and 2013)
        if self._rev_year in (ComtradeRevision.REV_1999.value, ComtradeRevision.REV_2013.value):
            lines.append(str(self._timing.time_multiplier))
            
        # Time codes (2013)
        if self._rev_year == ComtradeRevision.REV_2013.value:
            lines.append(f"{self._timing.time_code},{self._timing.local_code}")
            lines.append(f"{self._timing.tmq_code},{self._timing.leap_second}")
            
        return "\n".join(lines)

    @staticmethod
    def _format_timestamp(timestamp: dt.datetime) -> str:
        """
        Format timestamp for CFG file
        
        Args:
            timestamp: Datetime object
            
        Returns:
            str: Formatted timestamp string
        """
        date_str = timestamp.strftime("%d/%m/%Y")
        time_str = timestamp.strftime("%H:%M:%S.%f")
        return f"{date_str},{time_str}"

    def __str__(self) -> str:
        """String representation of CFG data"""
        lines = [
            f"Station: {self._station_name}",
            f"Device: {self._rec_dev_id}",
            f"Revision: {self._rev_year}",
            f"Channels: {self._analog_count}A + {self._status_count}D = {self._channels_count}",
            f"Frequency: {self._timing.frequency} Hz",
            "Sample rates:"
        ]
        
        for rate in self._timing.sample_rates:
            lines.append(f"  {rate}")
            
        lines.extend([
            f"Start time: {self._timing.start_timestamp}",
            f"Trigger time: {self._timing.trigger_timestamp}",
            f"File format: {self._data_format.value}"
        ])
        
        return "\n".join(lines)