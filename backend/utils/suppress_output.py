"""
Utilities for ChromaDB operations.
"""
import sys
import os
from contextlib import contextmanager


def safe_embedding(e):
    """
    Ensure embedding is pure Python list for ChromaDB.
    
    ChromaDB expects List[List[float]], not numpy arrays or tensors.
    Passing numpy arrays can trigger internal validation/debug output.
    
    Args:
        e: Embedding (can be numpy array, torch tensor, or list)
        
    Returns:
        Pure Python list of floats
    """
    # Handle numpy arrays and torch tensors
    if hasattr(e, "squeeze"):
        e = e.squeeze()  # Remove dimensions of size 1
    
    if hasattr(e, "tolist"):
        e = e.tolist()  # Convert to Python list
    
    # Ensure 1D list (flatten if needed) - MUST do this BEFORE converting to floats
    while isinstance(e, list) and len(e) > 0 and isinstance(e[0], list):
        e = e[0]  # Keep flattening until we have a 1D list
    
    # Now ensure all elements are Python floats (now x will be a number, not a list)
    if isinstance(e, list):
        e = [float(x) if not isinstance(x, list) else float(x[0]) for x in e]
    
    return e


@contextmanager
def suppress_stdout_stderr():
    """Context manager to suppress stdout and stderr."""
    # Save original file descriptors
    old_stdout = sys.stdout
    old_stderr = sys.stderr
    old_stdout_fd = os.dup(1)
    old_stderr_fd = os.dup(2)
    
    try:
        # Redirect to devnull
        devnull = open(os.devnull, 'w')
        os.dup2(devnull.fileno(), 1)
        os.dup2(devnull.fileno(), 2)
        sys.stdout = devnull
        sys.stderr = devnull
        
        yield
        
    finally:
        # Restore original file descriptors
        os.dup2(old_stdout_fd, 1)
        os.dup2(old_stderr_fd, 2)
        sys.stdout = old_stdout
        sys.stderr = old_stderr
        os.close(old_stdout_fd)
        os.close(old_stderr_fd)
        devnull.close()
