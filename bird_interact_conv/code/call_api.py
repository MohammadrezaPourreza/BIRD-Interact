import argparse
import os
import json
import time
import itertools

from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

from openai import OpenAI
import anthropic
from google import genai
# from google.generativeai.types import HarmCategory, HarmBlockThreshold, GenerationConfig
from google.genai import types
from config import model_config
from anthropic import AnthropicVertex
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type



def is_rate_limit_error(exception):
    """Check if the exception is related to rate limiting."""
    error_str = str(exception).lower()
    return any(keyword in error_str for keyword in [
        'rate limit', 'rate_limit', 'too many requests', '429', 
        'quota', 'throttle', 'resource_exhausted'
    ])


def is_retryable_error(exception):
    """Check if the exception is retryable."""
    error_str = str(exception).lower()
    retryable_keywords = [
        'rate limit', 'rate_limit', 'too many requests', '429',
        'quota', 'throttle', 'resource_exhausted', 'timeout',
        'connection', 'network', 'service unavailable', '503',
        'internal server error', '500', 'bad gateway', '502'
    ]
    return any(keyword in error_str for keyword in retryable_keywords)


def load_jsonl(file_path):
    data = []
    with open(file_path, "r", encoding="utf-8") as file:
        for line in file:
            data.append(json.loads(line))
    return data


def new_directory(path):
    if path and not os.path.exists(path):
        os.makedirs(path)


GEMINI_API_KEYS = model_config.get("gemini")
if GEMINI_API_KEYS is not None:
    # Create an infinite key cycle
    gemini_key_cycle = itertools.cycle(GEMINI_API_KEYS)


def write_response(results, data_list, output_path):
    """
    By default, each result is a single response.
    """
    formatted_data = []
    for i, data in enumerate(data_list):
        data["responses"] = results[i]
        data.pop("prompt", None)
        formatted_data.append(data)

    if output_path:
        directory_path = os.path.dirname(output_path)
        new_directory(directory_path)
        with open(output_path, "w") as f:
            for instance in formatted_data:
                f.write(json.dumps(instance, ensure_ascii=False) + "\n")


def api_request(messages, engine, client, backend, **kwargs):
    """
    Calls the underlying LLM endpoint depending on the 'backend'.
    """
    # @retry(
    #     stop=stop_after_attempt(5),
    #     wait=wait_exponential(multiplier=2, min=4, max=120),
    #     retry=is_retryable_error,
    #     reraise=True
    # )
    def _make_api_call():
        if backend == "openai":
            completion = client.chat.completions.create(
                model=engine,
                messages=messages,
                temperature=kwargs.get("temperature", 0),
                max_tokens=kwargs.get("max_tokens", 512),
                top_p=kwargs.get("top_p", 1),
                frequency_penalty=kwargs.get("frequency_penalty", 0),
                presence_penalty=kwargs.get("presence_penalty", 0),
                stop=kwargs.get("stop", None),
            )
            return completion.choices[0].message.content

        elif backend == "anthropic":
            message = client.messages.create(
                model=engine,
                messages=messages,
                temperature=kwargs.get("temperature", 0),
                max_tokens=kwargs.get("max_tokens", 512),
                top_p=kwargs.get("top_p", 1),
                stop_sequences=kwargs.get("stop", None),
            )
            return message.content[0].text

        elif backend == "genai":
            response = client.models.generate_content(
                model=engine,
                contents=messages[0]["content"],
                config=types.GenerateContentConfig(
                    temperature=kwargs.get("temperature", 0),
                    top_p=kwargs.get("top_p", 1),
                    # max_output_tokens=60000,
                    # thinking_config=types.ThinkingConfig(
                    #     thinking_budget=128
                    # ),
                    presence_penalty=kwargs.get("presence_penalty", 0),
                    frequency_penalty=kwargs.get("frequency_penalty", 0),
                    stop_sequences=kwargs.get("stop", None),
                ),
            )
            if not response or not response.text:
                print("Received empty response from Gemini API.")
                print(response)
                raise ValueError("Empty response from Gemini API")
            return response.text

    wait_exponential = 2
    base_wait_time = 10
    try:
        return _make_api_call()
    except Exception as e:
        # try to run it 3 more time with sleep 100 seconds
        for i in range(5):
            time.sleep(base_wait_time * wait_exponential ** i)
            try:
                return _make_api_call()
            except Exception as retry_e:
                print(f"Retry failed: {retry_e}")
        print(f"API request failed after all retries: {e}")



def call_api_model(
    messages,
    model_name,
    temperature=0,
    max_tokens=2048,
    top_p=0.9,
    frequency_penalty=0,
    presence_penalty=0,
    timeout=10,
    stop=None,
):
    """
    Sets up the correct backend client + model engine, then calls 'api_request'.
    """
    if "gpt" in model_name:
        engine = model_name
        client = OpenAI(
            base_url=model_config[model_name]["base_url"],
            api_key=model_config[model_name]["api_key"],
        )
        backend = "openai"

    elif "claude" in model_name:
        engine = model_name
        # client = anthropic.Anthropic(
        #     api_key=model_config[model_name],
        # )
        try:
            client = AnthropicVertex(
                project_id=model_config[model_name]["project"],
                region=model_config[model_name]["location"],
            )
        except Exception as e:
            print(f"Error occurred while calling Anthropic model: {e}")
        backend = "anthropic"

    elif "gemini" in model_name:
        engine = model_name
        # client = genai.GenerativeModel(engine)
        # genai.configure(api_key=GEMINI_API_KEYS[1])
        client = genai.Client(vertexai=True, project=model_config[model_name]["project"], location=model_config[model_name]["location"])
        backend = "genai"

    else:
        print(f"Unsupported model name: {model_name}")
        raise ValueError(f"Unsupported model name: {model_name}")

    kwargs = {
        "temperature": temperature,
        "max_tokens": max_tokens,
        "top_p": top_p,
        "frequency_penalty": frequency_penalty,
        "presence_penalty": presence_penalty,
        "stop": stop,
    }
    result = api_request(messages, engine, client, backend, **kwargs)
    
    # Ensure we never return None
    if result is None:
        return "Error: API request failed after multiple retries"
    
    return result


def worker_function(task, data_list, output_path, lock):
    """
    Processes a single prompt.
    """
    prompt, idx, model_name = task
    messages = [{"role": "user", "content": prompt}]
    response = call_api_model(messages, model_name)
    print(response)
    # Write to the file in real-time (append mode)
    with lock:
        with open(output_path, "a", encoding="utf-8") as f:
            row = data_list[idx]
            row["response"] = response
            # Use the _index field to record the original index
            row["_index"] = idx
            row.pop("prompt", None)
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    return idx, response


def final_sort_jsonl_by_index(file_path):
    """
    Reads an existing JSONL file, sorts it by the '_index' field,
    then overwrites the file. After sorting, you can remove the '_index' field.
    """
    all_data = []
    with open(file_path, "r", encoding="utf-8") as fin:
        for line in fin:
            if not line.strip():
                continue
            row = json.loads(line)
            all_data.append(row)

    # Sort by '_index'
    all_data.sort(key=lambda x: x["_index"])

    # Overwrite the file, removing the '_index' field
    with open(file_path, "w", encoding="utf-8") as fout:
        for row in all_data:
            row.pop("_index", None)
            fout.write(json.dumps(row, ensure_ascii=False) + "\n")


def collect_response_from_api(
    prompt_list,
    model_name,
    data_list,
    output_path,
    num_threads=8,
    start_index=0,
):
    """
    In multi-threading, write to a file in real-time, then sort the final output.
    """
    # Only process tasks from 'start_index' onward
    tasks = [
        (prompt_list[i], i, model_name) for i in range(start_index, len(prompt_list))
    ]

    # Ensure the output directory exists
    new_directory(os.path.dirname(output_path))

    # If starting from scratch, use 'w' to clear the file; otherwise use 'a' to append
    file_mode = "a" if start_index > 0 else "w"
    if file_mode == "w":
        # Clear the file first
        open(output_path, "w", encoding="utf-8").close()

    # Lock for protecting the write operation
    lock = threading.Lock()

    with ThreadPoolExecutor(max_workers=num_threads) as executor:
        futures = []
        for t in tasks:
            futures.append(
                executor.submit(worker_function, t, data_list, output_path, lock)
            )

        # Wait until all threads are done
        for _ in tqdm(as_completed(futures), total=len(futures)):
            pass

    # After all threads finish, perform a final sort of the output file
    final_sort_jsonl_by_index(output_path)


if __name__ == "__main__":
    args_parser = argparse.ArgumentParser()
    args_parser.add_argument("--prompt_path", type=str)
    args_parser.add_argument("--output_path", type=str)
    args_parser.add_argument("--model_name", type=str, default="claude")
    args_parser.add_argument("--start_index", type=int, default=0)
    args = args_parser.parse_args()

    data_list = load_jsonl(args.prompt_path)
    prompts = [data["prompt"] for data in data_list]
    print(prompts[0])
    collect_response_from_api(
        prompts,
        args.model_name,
        data_list,
        args.output_path,
        start_index=args.start_index,
    )
