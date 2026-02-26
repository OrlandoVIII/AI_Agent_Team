import asyncio
import logging
import random
from typing import Callable, Awaitable, TypeVar

logger = logging.getLogger(__name__)

# Type variable for the retry function
T = TypeVar('T')


async def retry_with_exponential_backoff(
    func: Callable[[], Awaitable[T]], 
    max_retries: int = 3, 
    base_delay: int = 1, 
    max_delay: int = 60
) -> T:
    """
    Retry function with exponential backoff and jitter.
    
    Args:
        func: Async function to retry
        max_retries: Maximum retry attempts (default 3)
        base_delay: Base delay in seconds (default 1)
        max_delay: Maximum delay in seconds (default 60)
        
    Returns:
        Result of the function call
        
    Raises:
        Exception: The last exception encountered if all retries fail
        
    The function implements exponential backoff with jitter to prevent
    thundering herd problems when multiple instances retry simultaneously.
    """
    last_exception = None
    for attempt in range(max_retries):
        try:
            return await func()
        except Exception as e:
            last_exception = e
            if attempt == max_retries - 1:
                logger.error(f'All {max_retries} retry attempts failed for operation')
                raise
            logger.warning(f"Operation attempt {attempt + 1} failed: {e}. Retrying...")
            # Exponential backoff with jitter to prevent thundering herd
            delay = min(base_delay * (2 ** attempt) + random.uniform(0, 1), max_delay)
            await asyncio.sleep(delay)
    
    # This should never be reached, but added for completeness
    if last_exception:
        raise last_exception