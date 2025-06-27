# Copyright 2025 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""
Logging helper functions
"""
import time as perftime
import functools
import asyncio


def log_exec_time(logger):
    """
    Log the execution time of the decorated function, supporting both
    synchronous and asynchronous functions.
    """
    def decorator(func):
        if asyncio.iscoroutinefunction(func):  # Check if the function is async
            @functools.wraps(func)
            async def wrapper(*args, **kwargs):
                start_time = perftime.perf_counter()
                result = await func(*args, **kwargs)  # Await async function
                end_time = perftime.perf_counter()
                execution_time = end_time - start_time
                logger.info("[%s] [%s] Execution time: %.4f seconds",
                             func.__name__, execution_time)
                return result
        else:  # Handle synchronous functions
            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                start_time = perftime.perf_counter()
                result = func(*args, **kwargs)
                end_time = perftime.perf_counter()
                execution_time = end_time - start_time
                logger.info("[%s] Execution time: %.4f seconds",
                              func.__name__, execution_time)
                return result
        return wrapper
    return decorator

