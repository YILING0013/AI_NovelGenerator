# novel_generator/common.py
# -*- coding: utf-8 -*-
"""
Common retry, cleaning, and logging tools.
"""
import logging
import re
import time
import traceback

logging.basicConfig(
    filename='app.log',
    filemode='a',
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

def call_with_retry(func, max_retries=3, sleep_time=2, fallback_return=None, **kwargs):
    """
    Generic retry mechanism wrapper.
    :param func: Function to execute
    :param max_retries: Maximum number of retries
    :param sleep_time: Seconds to wait before retrying
    :param fallback_return: Return value if all retries fail
    :param kwargs: Named arguments passed to func
    :return: Result of func, or fallback_return if failed
    """
    for attempt in range(1, max_retries + 1):
        try:
            return func(**kwargs)
        except Exception as e:
            logging.warning(f"[call_with_retry] Attempt {attempt} failed with error: {e}")
            traceback.print_exc()
            if attempt < max_retries:
                time.sleep(sleep_time)
            else:
                logging.error("Max retries reached, returning fallback_return.")
                return fallback_return

def remove_think_tags(text: str) -> str:
    """Removes content wrapped in <think>...</think> tags."""
    return re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)

def debug_log(prompt: str, response_content: str):
    logging.info(
        f"\n[#########################################  Prompt  #########################################]\n{prompt}\n"
    )
    logging.info(
        f"\n[######################################### Response #########################################]\n{response_content}\n"
    )

def invoke_with_cleaning(llm_adapter, prompt: str, max_retries: int = 3) -> str:
    """Invokes the LLM and cleans the returned result."""
    print("\n" + "="*50)
    print("Prompt sent to LLM:")
    print("-"*50)
    print(prompt)
    print("="*50 + "\n")
    
    result = ""
    retry_count = 0
    
    while retry_count < max_retries:
        try:
            result = llm_adapter.invoke(prompt)
            print("\n" + "="*50)
            print("LLM Response Content:")
            print("-"*50)
            print(result)
            print("="*50 + "\n")
            
            # Clean special markdown markers from the result
            result = result.replace("```", "").strip()
            if result:
                return result
            retry_count += 1
        except Exception as e:
            print(f"Invocation failed ({retry_count + 1}/{max_retries}): {str(e)}")
            retry_count += 1
            if retry_count >= max_retries:
                raise e
    
    return result
