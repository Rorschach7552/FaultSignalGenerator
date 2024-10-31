from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import List, Optional, Union
from pathlib import Path

class FileType(Enum):
    """Types of COMTRADE files"""
    CFG = auto()
    DAT = auto()
    HDR = auto()
    INF = auto()
    CFF = auto()

    @property
    def extension(self) -> str:
        """Get file extension"""
        return self.name.lower()

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
    sample_rates: List[SamplingRate] = field(default_factory=list)
    start_timestamp: datetime = field(default_factory=lambda: datetime.min)
    trigger_timestamp: datetime = field(default_factory=lambda: datetime.min)
    time_multiplier: float = 1.0
    time_code: int = 0
    local_code: int = 0
    tmq_code: int = 0
    leap_second: int = 0

@dataclass
class SampleData:
    """Single sample of data"""
    number: int
    timestamp: float
    analog_values: List[float]
    status_values: List[int]

@dataclass
class CFFHeader:
    """CFF file section header information"""
    file_type: str
    format: Optional[str] = None
    byte_count: Optional[int] = None

@dataclass
class ComtradeFileSet:
    """Collection of COMTRADE files"""
    cfg_path: Path
    dat_path: Optional[Path] = None
    hdr_path: Optional[Path] = None
    inf_path: Optional[Path] = None

    @classmethod
    def from_cfg_path(cls, cfg_path: Union[str, Path]) -> 'ComtradeFileSet':
        """Create file set from CFG file path"""
        cfg_path = Path(cfg_path)
        return cls(
            cfg_path=cfg_path,
            dat_path=cfg_path.with_suffix('.dat'),
            hdr_path=cfg_path.with_suffix('.hdr'),
            inf_path=cfg_path.with_suffix('.inf')
        )