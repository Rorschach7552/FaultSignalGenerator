"""
base.py
Core components and base classes for COMTRADE file parsing.

This module contains the fundamental classes and constants used throughout
the COMTRADE parser implementation.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Union, BinaryIO, TextIO
import array
import datetime as dt
import math
import os
import warnings

# Try to import numpy - optional dependency
try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False

class ComtradeRevision(Enum):
    """COMTRADE standard revisions"""
    REV_1991 = "1991"
    REV_1999 = "1999"
    REV_2013 = "2013"

    @classmethod
    def is_valid(cls, revision: str) -> bool:
        """Check if a revision string is valid"""
        return any(revision == rev.value for rev in cls)

class DataFormat(Enum):
    """DAT file format types"""
    ASCII = "ASCII"
    BINARY = "BINARY"
    BINARY32 = "BINARY32"
    FLOAT32 = "FLOAT32"

    @classmethod
    def from_string(cls, format_str: str) -> 'DataFormat':
        """Convert string format to enum value"""
        try:
            return cls(format_str.upper())
        except ValueError:
            raise ValueError(f"Unsupported data format: {format_str}")

class TimeBase:
    """Time base constants and utilities for timestamp handling"""
    NANOSEC: float = 1E-9
    MICROSEC: float = 1E-6

    @staticmethod
    def get_time_base(using_nanoseconds: bool) -> float:
        """
        Return appropriate time base based on timestamp precision
        
        Args:
            using_nanoseconds: Whether nanosecond precision is used
            
        Returns:
            float: Time base value (NANOSEC or MICROSEC)
        """
        return TimeBase.NANOSEC if using_nanoseconds else TimeBase.MICROSEC

class ArrayFactory:
    """Factory for creating arrays based on numpy availability"""
    
    TYPE_MAPPING_NUMPY = {
        "f": "float32",
        "i": "int32"
    }
    
    @classmethod
    def create_array(cls, array_type: str, size: int, use_numpy: bool = False) -> Union[array.array, 'np.ndarray']:
        """
        Create an array of specified type and size
        
        Args:
            array_type: Type of array ('f' for float, 'i' for integer)
            size: Size of array
            use_numpy: Whether to use numpy arrays if available
            
        Returns:
            Union[array.array, np.ndarray]: Created array
        """
        if HAS_NUMPY and use_numpy:
            return np.zeros(size, dtype=cls.TYPE_MAPPING_NUMPY[array_type])
        return array.array(array_type, [0]) * size

@dataclass
class Channel:
    """Base class for COMTRADE channels"""
    number: int
    name: str = ""
    phase: str = ""
    circuit_component: str = ""
    
    def __str__(self) -> str:
        """String representation of channel"""
        return ','.join([
            str(self.number),
            self.name,
            self.phase,
            self.circuit_component
        ])

@dataclass
class AnalogChannel(Channel):
    """Analog channel information"""
    multiplier: float = 1.0
    offset: float = 0.0
    skew: float = 0.0
    min_value: float = -32767
    max_value: float = 32767
    units: str = ""
    primary: float = 1.0
    secondary: float = 1.0
    ps_ratio: str = "P"  # P for primary, S for secondary

    def __str__(self) -> str:
        """String representation of analog channel"""
        fields = [
            str(self.number),
            self.name,
            self.phase,
            self.circuit_component,
            self.units,
            str(self.multiplier),
            str(self.offset),
            str(self.skew),
            str(self.min_value),
            str(self.max_value),
            str(self.primary),
            str(self.secondary),
            self.ps_ratio
        ]
        return ','.join(fields)

    def scale_value(self, raw_value: float) -> float:
        """
        Scale a raw value using channel parameters
        
        Args:
            raw_value: Raw value from DAT file
            
        Returns:
            float: Scaled value
        """
        return raw_value * self.multiplier + self.offset

@dataclass
class StatusChannel(Channel):
    """Status channel information"""
    initial_value: int = 0

    def __str__(self) -> str:
        """String representation of status channel"""
        return ','.join([
            str(self.number),
            self.name,
            self.phase,
            self.circuit_component,
            str(self.initial_value)
        ])

class DatReader:
    """Base class for DAT file readers"""
    
    def __init__(self, use_numpy: bool = False):
        """
        Initialize DAT reader
        
        Args:
            use_numpy: Whether to use numpy arrays for data storage
        """
        self.use_numpy = use_numpy
        self.file_path = ""
        self._cfg = None
        self.time = ArrayFactory.create_array("f", 0, use_numpy)
        self.analog: List[Union[array.array, 'np.ndarray']] = []
        self.status: List[Union[array.array, 'np.ndarray']] = []
        self.total_samples = 0

    def load(self, filepath: str, cfg: 'Cfg', **kwargs) -> None:
        """
        Load DAT file from disk
        
        Args:
            filepath: Path to DAT file
            cfg: Associated CFG object
            **kwargs: Additional options (e.g., encoding)
        """
        if not os.path.isfile(filepath):
            raise FileNotFoundError(f"DAT file not found: {filepath}")
            
        self.file_path = filepath
        self._cfg = cfg
        self._preallocate()
        
        encoding = kwargs.get('encoding', self._detect_encoding())
        mode = getattr(self, 'read_mode', 'r')
        
        with open(filepath, mode, encoding=encoding) as file:
            self.parse(file)

    def read(self, content: Union[str, bytes, TextIO, BinaryIO], cfg: 'Cfg') -> None:
        """
        Read DAT content from string, bytes, or file object
        
        Args:
            content: DAT file content
            cfg: Associated CFG object
        """
        self._cfg = cfg
        self._preallocate()
        self.parse(content)

    def _preallocate(self) -> None:
        """Preallocate arrays for data storage"""
        self.total_samples = self._cfg.sample_rates[-1][1]
        
        self.time = ArrayFactory.create_array("f", self.total_samples, self.use_numpy)
        self.analog = []
        self.status = []
        
        # Preallocate channel arrays
        for _ in range(self._cfg.analog_count):
            self.analog.append(
                ArrayFactory.create_array("f", self.total_samples, self.use_numpy)
            )
        for _ in range(self._cfg.status_count):
            self.status.append(
                ArrayFactory.create_array("i", self.total_samples, self.use_numpy)
            )

    def _detect_encoding(self) -> Optional[str]:
        """Detect file encoding"""
        try:
            with open(self.file_path, 'r') as file:
                file.read()
                return None
        except UnicodeDecodeError:
            return 'utf-8'

    def parse(self, content: Union[str, bytes, TextIO, BinaryIO]) -> None:
        """
        Parse DAT file contents - to be implemented by subclasses
        
        Args:
            content: DAT file content to parse
        """
        raise NotImplementedError("Subclasses must implement parse method")

    def _get_sample_rate(self, sample_number: int) -> float:
        """
        Get sample rate for a given sample number
        
        Args:
            sample_number: Sample number (1-based index)
            
        Returns:
            float: Sample rate in Hz
        """
        for rate, end_sample in self._cfg.sample_rates:
            if sample_number <= end_sample:
                return rate
        return self._cfg.sample_rates[-1][0] if self._cfg.sample_rates else 1.0

    def _calculate_timestamp(self, sample_number: int, timestamp_value: float,
                           time_base: float, time_mult: float) -> float:
        """
        Calculate timestamp for a sample
        
        Args:
            sample_number: Sample number (1-based)
            timestamp_value: Raw timestamp value
            time_base: Time base value
            time_mult: Time multiplier
            
        Returns:
            float: Calculated timestamp in seconds
        """
        if (not self._cfg.timestamp_critical or 
            timestamp_value == 0xFFFFFFFF):  # Missing timestamp
            sample_rate = self._get_sample_rate(sample_number)
            if sample_rate == 0:
                raise ValueError("Missing timestamp and no sample rate provided")
            return (sample_number - 1) / sample_rate
            
        return timestamp_value * time_base * time_mult