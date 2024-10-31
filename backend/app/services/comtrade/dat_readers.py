"""
dat_readers.py
Data file readers for COMTRADE files.

This module implements readers for different COMTRADE DAT file formats:
- ASCII
- Binary (16-bit)
- Binary32 (32-bit)
- Float32 (32-bit float)
"""

import array
import io
import math
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, List, Optional, TextIO, Tuple, Union

from .base import ArrayFactory, DatReader
from .exceptions import DatReaderError

# Special value indicating missing timestamp
TIMESTAMP_MISSING = 0xFFFFFFFF

@dataclass
class SampleData:
    """Single sample of data from DAT file"""
    number: int
    timestamp: float
    analog_values: List[float]
    status_values: List[int]

class AsciiDatReader(DatReader):
    """Reader for ASCII format DAT files"""
    
    def __init__(self, use_numpy: bool = False):
        super().__init__(use_numpy)
        self.separator = ','
        
    def parse(self, content: Union[str, TextIO]) -> None:
        """
        Parse ASCII DAT file contents
        
        Args:
            content: File content as string or file object
            
        Raises:
            DatReaderError: If parsing fails
        """
        lines = content.splitlines() if isinstance(content, str) else content
        
        # Get scaling factors from CFG
        analog_gains = [ch.multiplier for ch in self._cfg.analog_channels]
        analog_offsets = [ch.offset for ch in self._cfg.analog_channels]
        time_mult = self._cfg.timemult
        time_base = self._cfg.time_base
        
        for line_number, line in enumerate(lines, 1):
            if line_number > self.total_samples:
                break
                
            try:
                sample = self._parse_line(
                    line.strip(), 
                    analog_gains, 
                    analog_offsets,
                    time_mult,
                    time_base
                )
                
                # Store sample data
                idx = line_number - 1
                self.time[idx] = sample.timestamp
                for i, value in enumerate(sample.analog_values):
                    self.analog[i][idx] = value
                for i, value in enumerate(sample.status_values):
                    self.status[i][idx] = value
                    
            except Exception as e:
                raise DatReaderError(f"Error parsing line {line_number}: {str(e)}")

    def _parse_line(self, line: str, gains: List[float], offsets: List[float],
                   time_mult: float, time_base: float) -> SampleData:
        """
        Parse a single line of ASCII data
        
        Args:
            line: Line of data
            gains: Analog channel scaling factors
            offsets: Analog channel offsets
            time_mult: Time multiplier
            time_base: Time base value
            
        Returns:
            SampleData: Parsed sample data
        """
        values = [val.strip() for val in line.split(self.separator)]
        
        if len(values) < 2 + self._cfg.analog_count + self._cfg.status_count:
            raise DatReaderError("Insufficient values in line")
            
        try:
            # Parse sample number and timestamp
            sample_number = int(values[0])
            timestamp_val = float(values[1])
            timestamp = self._calculate_timestamp(
                sample_number, timestamp_val, time_base, time_mult
            )
            
            # Parse analog values
            analog_start = 2
            analog_end = analog_start + self._cfg.analog_count
            analog_values = [
                float(val) * gain + offset
                for val, gain, offset in zip(
                    values[analog_start:analog_end],
                    gains,
                    offsets
                )
            ]
            
            # Parse status values
            status_values = [
                int(val)
                for val in values[analog_end:analog_end + self._cfg.status_count]
            ]
            
            return SampleData(
                sample_number,
                timestamp,
                analog_values,
                status_values
            )
            
        except (ValueError, IndexError) as e:
            raise DatReaderError(f"Invalid value format: {str(e)}")

class BaseBinaryReader(DatReader):
    """Base class for binary format readers"""
    
    read_mode = "rb"
    
    def __init__(self, use_numpy: bool = False):
        super().__init__(use_numpy)
        self.sample_number_bytes = 4
        self.timestamp_bytes = 4
        self.struct_format = "I" if struct.calcsize("L") == 4 else "Q"
        
    def parse(self, content: Union[bytes, BinaryIO]) -> None:
        """
        Parse binary DAT file contents
        
        Args:
            content: Binary content as bytes or file object
            
        Raises:
            DatReaderError: If parsing fails
        """
        if isinstance(content, io.IOBase):
            content = content.read()
            
        # Calculate row format and size
        analog_count = self._cfg.analog_count
        status_count = self._cfg.status_count
        status_bytes = math.ceil(status_count / 16.0) * 2
        
        row_format = self._get_row_format(analog_count, status_bytes)
        row_size = struct.calcsize(row_format)
        
        # Get scaling factors
        analog_gains = [ch.multiplier for ch in self._cfg.analog_channels]
        analog_offsets = [ch.offset for ch in self._cfg.analog_channels]
        
        try:
            row_reader = struct.Struct(row_format)
            
            for i, values in enumerate(row_reader.iter_unpack(content)):
                if i >= self.total_samples:
                    break
                    
                sample = self._parse_values(
                    values,
                    analog_count,
                    analog_gains,
                    analog_offsets,
                    status_count,
                    self._cfg.timemult,
                    self._cfg.time_base
                )
                
                # Store sample data
                self.time[i] = sample.timestamp
                for j, value in enumerate(sample.analog_values):
                    self.analog[j][i] = value
                for j, value in enumerate(sample.status_values):
                    self.status[j][i] = value
                    
        except struct.error as e:
            raise DatReaderError(f"Error parsing binary data: {str(e)}")

    def _get_row_format(self, analog_count: int, status_bytes: int) -> str:
        """Get struct format string for a row"""
        raise NotImplementedError

    def _parse_values(self, values: Tuple, analog_count: int,
                     gains: List[float], offsets: List[float],
                     status_count: int, time_mult: float,
                     time_base: float) -> SampleData:
        """
        Parse binary values into sample data
        
        Args:
            values: Tuple of binary values
            analog_count: Number of analog channels
            gains: Analog channel scaling factors
            offsets: Analog channel offsets
            status_count: Number of status channels
            time_mult: Time multiplier
            time_base: Time base value
            
        Returns:
            SampleData: Parsed sample data
        """
        sample_num = values[0]
        timestamp_val = values[1]
        timestamp = self._calculate_timestamp(
            sample_num, timestamp_val, time_base, time_mult
        )
        
        # Process analog values
        analog_values = [
            val * gain + offset
            for val, gain, offset in zip(
                values[2:2+analog_count],
                gains,
                offsets
            )
        ]
        
        # Process status values
        status_raw = values[2+analog_count:]
        status_values = self._extract_status_bits(status_raw, status_count)
        
        return SampleData(
            sample_num,
            timestamp,
            analog_values,
            status_values
        )

    def _extract_status_bits(self, status_words: Tuple[int, ...],
                           total_status: int) -> List[int]:
        """
        Extract individual status bits from packed words
        
        Args:
            status_words: Tuple of packed status words
            total_status: Total number of status channels
            
        Returns:
            List[int]: List of status values
        """
        status_values = []
        for word in status_words:
            for bit in range(min(16, total_status - len(status_values))):
                mask = 1 << bit
                value = (word & mask) >> bit
                status_values.append(value)
        return status_values

class BinaryDatReader(BaseBinaryReader):
    """Reader for 16-bit binary format"""
    
    analog_bytes = 2
    status_bytes = 2
    
    def _get_row_format(self, analog_count: int, status_bytes: int) -> str:
        """Get struct format string for 16-bit binary data"""
        base_format = f"{self.struct_format}{self.struct_format}"
        
        if analog_count > 0 and status_bytes > 0:
            return f"{base_format}{analog_count}h{status_bytes // 2}H"
        elif analog_count > 0:
            return f"{base_format}{analog_count}h"
        else:
            return f"{base_format}{status_bytes // 2}H"

class Binary32DatReader(BaseBinaryReader):
    """Reader for 32-bit binary format"""
    
    analog_bytes = 4
    status_bytes = 2
    
    def _get_row_format(self, analog_count: int, status_bytes: int) -> str:
        """Get struct format string for 32-bit binary data"""
        base_format = f"{self.struct_format}{self.struct_format}"
        
        if analog_count > 0 and status_bytes > 0:
            return f"{base_format}{analog_count}l{status_bytes // 2}H"
        elif analog_count > 0:
            return f"{base_format}{analog_count}l"
        else:
            return f"{base_format}{status_bytes // 2}H"

class Float32DatReader(BaseBinaryReader):
    """Reader for 32-bit float format"""
    
    analog_bytes = 4
    status_bytes = 2
    
    def _get_row_format(self, analog_count: int, status_bytes: int) -> str:
        """Get struct format string for 32-bit float data"""
        base_format = f"{self.struct_format}{self.struct_format}"
        
        if analog_count > 0 and status_bytes > 0:
            return f"{base_format}{analog_count}f{status_bytes // 2}H"
        elif analog_count > 0:
            return f"{base_format}{analog_count}f"
        else:
            return f"{base_format}{status_bytes // 2}H"

    def _parse_values(self, values: Tuple, analog_count: int,
                     gains: List[float], offsets: List[float],
                     status_count: int, time_mult: float,
                     time_base: float) -> SampleData:
        """Parse float32 values (overrides base implementation)"""
        sample_num = values[0]
        timestamp_val = values[1]
        timestamp = self._calculate_timestamp(
            sample_num, timestamp_val, time_base, time_mult
        )
        
        # Float values don't need scaling
        analog_values = list(values[2:2+analog_count])
        
        # Process status values
        status_raw = values[2+analog_count:]
        status_values = self._extract_status_bits(status_raw, status_count)
        
        return SampleData(
            sample_num,
            timestamp,
            analog_values,
            status_values
        )

def get_reader(format_type: str, use_numpy: bool = False) -> DatReader:
    """
    Factory function to create appropriate DAT reader
    
    Args:
        format_type: DAT file format type
        use_numpy: Whether to use numpy arrays
        
    Returns:
        DatReader: Appropriate reader instance
        
    Raises:
        DatReaderError: If format type is not supported
    """
    readers = {
        "ASCII": AsciiDatReader,
        "BINARY": BinaryDatReader,
        "BINARY32": Binary32DatReader,
        "FLOAT32": Float32DatReader
    }
    
    reader_class = readers.get(format_type.upper())
    if not reader_class:
        raise DatReaderError(f"Unsupported data format: {format_type}")
        
    return reader_class(use_numpy)