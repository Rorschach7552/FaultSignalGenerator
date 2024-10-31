import warnings
from pathlib import Path
from typing import Dict, List, Optional, Union

from .base import ArrayFactory
from .cfg import Cfg
from .dat_readers import get_reader, DatReader
from .exceptions import ComtradeError, ComtradeFormatError
from .models import ComtradeFileSet, FileType

class Comtrade:
    """Main class for handling COMTRADE format data"""
    
    def __init__(self, *, use_numpy: bool = False, ignore_warnings: bool = False):
        """
        Initialize COMTRADE parser
        
        Args:
            use_numpy: Whether to use numpy arrays
            ignore_warnings: Whether to suppress warnings
        """
        self.use_numpy = use_numpy
        self.ignore_warnings = ignore_warnings
        
        # Initialize components
        self._cfg = Cfg(ignore_warnings=ignore_warnings)
        self._file_set: Optional[ComtradeFileSet] = None
        
        # Data storage
        self._time_values = ArrayFactory.create_array("f", 0, use_numpy)
        self._analog_values: List = []
        self._status_values: List = []
        self._total_samples = 0
        
        # Additional file contents
        self._hdr: Optional[str] = None
        self._inf: Optional[str] = None

    @property
    def cfg(self) -> Cfg:
        """Access to CFG object"""
        return self._cfg

    @property
    def time(self) -> Union['numpy.ndarray', List[float]]:
        """Time values"""
        return self._time_values

    @property
    def analog(self) -> List[Union['numpy.ndarray', List[float]]]:
        """Analog channel values"""
        return self._analog_values

    @property
    def status(self) -> List[Union['numpy.ndarray', List[int]]]:
        """Status channel values"""
        return self._status_values

    @property
    def total_samples(self) -> int:
        """Total number of samples"""
        return self._total_samples

    def load(self, filepath: Union[str, Path], dat_file: Optional[str] = None,
            **kwargs) -> None:
        """
        Load COMTRADE files
        
        Args:
            filepath: Path to CFG or CFF file
            dat_file: Optional DAT file path
            **kwargs: Additional options
        """
        path = Path(filepath)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {filepath}")

        if path.suffix.lower() == f".{FileType.CFF.extension}":
            self._load_cff(path, **kwargs)
        else:
            self._load_separate_files(path, dat_file, **kwargs)

    def read(self, cfg_content: str, dat_content: Union[str, bytes]) -> None:
        """
        Read COMTRADE data from strings
        
        Args:
            cfg_content: CFG file content
            dat_content: DAT file content
        """
        # Parse CFG
        self._cfg.read(cfg_content)
        
        # Get appropriate reader and parse DAT
        reader = get_reader(self._cfg.ft, self.use_numpy)
        reader.read(dat_content, self._cfg)
        
        # Extract data
        self._time_values = reader.time
        self._analog_values = reader.analog
        self._status_values = reader.status
        self._total_samples = reader.total_samples

    def _load_separate_files(self, cfg_path: Path, 
                           dat_path: Optional[Union[str, Path]] = None,
                           **kwargs) -> None:
        """Load separate COMTRADE files"""
        # Create file set
        self._file_set = ComtradeFileSet.from_cfg_path(cfg_path)
        if dat_path:
            self._file_set.dat_path = Path(dat_path)
            
        # Load CFG
        self._cfg.load(str(self._file_set.cfg_path), **kwargs)
        
        # Load DAT
        reader = get_reader(self._cfg.ft, self.use_numpy)
        reader.load(str(self._file_set.dat_path), self._cfg, **kwargs)
        
        # Extract data
        self._time_values = reader.time
        self._analog_values = reader.analog
        self._status_values = reader.status
        self._total_samples = reader.total_samples
        
        # Load additional files if present
        self._load_additional_files(**kwargs)

    def _load_additional_files(self, **kwargs) -> None:
        """Load HDR and INF files if present"""
        encoding = kwargs.get('encoding')
        
        for path, attr in [
            (self._file_set.hdr_path, '_hdr'),
            (self._file_set.inf_path, '_inf')
        ]:
            if path and path.exists():
                try:
                    with open(path, 'r', encoding=encoding) as f:
                        content = f.read()
                        setattr(self, attr, content if content else None)
                except Exception as e:
                    if not self.ignore_warnings:
                        warnings.warn(f"Error loading {path.name}: {str(e)}")

    def _load_cff(self, cff_path: Path, **kwargs) -> None:
        """Load CFF file"""
        raise NotImplementedError("CFF file support not implemented")

    def get_channel_index(self, channel_id: str, 
                         channel_type: str = 'analog') -> int:
        """
        Get channel index by ID
        
        Args:
            channel_id: Channel identifier
            channel_type: Type of channel ('analog' or 'status')
            
        Returns:
            int: Channel index
            
        Raises:
            ValueError: If channel not found
        """
        if channel_type.lower() == 'analog':
            channels = self._cfg.analog_channels
        elif channel_type.lower() == 'status':
            channels = self._cfg.status_channels
        else:
            raise ValueError(f"Invalid channel type: {channel_type}")
            
        for i, channel in enumerate(channels):
            if channel.name == channel_id:
                return i
        raise ValueError(f"Channel not found: {channel_id}")

    def get_channel_data(self, channel_id: str,
                        channel_type: str = 'analog') -> Union['numpy.ndarray', List]:
        """
        Get channel data by ID
        
        Args:
            channel_id: Channel identifier
            channel_type: Type of channel ('analog' or 'status')
            
        Returns:
            Union[numpy.ndarray, List]: Channel data
        """
        idx = self.get_channel_index(channel_id, channel_type)
        if channel_type.lower() == 'analog':
            return self._analog_values[idx]
        return self._status_values[idx]

    def __getattr__(self, name: str):
        """Delegate unknown attributes to CFG"""
        return getattr(self._cfg, name)

    def __str__(self) -> str:
        """String representation"""
        return f"COMTRADE Record\n{self._cfg}"