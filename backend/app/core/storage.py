import aiofiles
from pathlib import Path
from typing import Optional
import logging

logger = logging.getLogger(__name__)

class StorageBackend:
    def __init__(self, base_dir: str = "storage"):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    async def save_file(self, ticker: str, year: int, filename: str, content: bytes) -> str:
        """
        Saves a downloaded filing to the local storage hierarchy:
        storage/companies/{ticker}/{year}/{filename}
        """
        target_dir = self.base_dir / "companies" / ticker.upper() / str(year)
        target_dir.mkdir(parents=True, exist_ok=True)
        
        file_path = target_dir / filename
        
        try:
            async with aiofiles.open(file_path, 'wb') as f:
                await f.write(content)
            logger.info(f"Saved file to {file_path}")
            return str(file_path)
        except Exception as e:
            logger.error(f"Failed to save file {file_path}: {e}")
            raise

    async def read_file(self, file_path: str) -> Optional[bytes]:
        try:
            async with aiofiles.open(file_path, 'rb') as f:
                return await f.read()
        except FileNotFoundError:
            logger.error(f"File not found: {file_path}")
            return None
