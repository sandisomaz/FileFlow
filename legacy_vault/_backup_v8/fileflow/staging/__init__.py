"""
FileFlow Staging Module
Manages file staging, deduplication, and entity resolution.
"""

from .manager import StagingManager, StagedFile

__all__ = ['StagingManager', 'StagedFile']
