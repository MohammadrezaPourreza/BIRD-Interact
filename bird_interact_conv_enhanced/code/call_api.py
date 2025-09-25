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
from google.genai.types import HarmCategory, HarmBlockThreshold, GenerateContentConfig, ThinkingConfig
from config import model_config


def load_jsonl(file_path):
    data = []
    try:
        with open(file_path, "r", encoding="utf-8", errors='replace') as file:
            for line_num, line in enumerate(file, 1):
                try:
                    if line.strip():  # Skip empty lines
                        data.append(json.loads(line))
                except json.JSONDecodeError as e:
                    print(f"⚠️ JSON decode error at line {line_num}: {str(e)}")
                    print(f"Problematic line: {line[:100]}...")
                    continue
                except UnicodeDecodeError as e:
                    print(f"⚠️ Unicode decode error at line {line_num}: {str(e)}")
                    continue
    except Exception as e:
        print(f"❌ Error loading file {file_path}: {str(e)}")
        return []
    return data


def new_directory(path):
    if path and not os.path.exists(path):
        os.makedirs(path)


# GEMINI_API_KEYS = model_config["gemini"]
# Create an infinite key cycle
# gemini_key_cycle = itertools.cycle(GEMINI_API_KEYS)


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


def clean_response_encoding(response):
    """Clean and ensure response has valid UTF-8 encoding."""
    if not isinstance(response, str):
        return str(response)
    
    try:
        # Try to encode/decode to catch any encoding issues
        response.encode('utf-8')
        return response
    except UnicodeEncodeError:
        # Replace problematic characters
        return response.encode('utf-8', errors='replace').decode('utf-8')
    except Exception:
        # Last resort: convert to ASCII
        return str(response).encode('ascii', errors='replace').decode('ascii')


def api_request(messages, engine, client, backend, **kwargs):
    """
    Calls the underlying LLM endpoint depending on the 'backend'.
    """
    while True:
        try:
            if backend == "openai":
                completion = client.chat.completions.create(
                    model=engine,
                    messages=messages,
                    temperature=kwargs.get("temperature", 0),
                    max_tokens=kwargs.get("max_tokens", 2048),  # Increased default
                    top_p=kwargs.get("top_p", 1),
                    frequency_penalty=kwargs.get("frequency_penalty", 0),
                    presence_penalty=kwargs.get("presence_penalty", 0),
                    stop=kwargs.get("stop", None),
                )
                return clean_response_encoding(completion.choices[0].message.content)

            elif backend == "anthropic":
                message = client.messages.create(
                    model=engine,
                    messages=messages,
                    temperature=kwargs.get("temperature", 0),
                    max_tokens=kwargs.get("max_tokens", 2048),  # Increased default
                    top_p=kwargs.get("top_p", 1),
                    stop_sequences=kwargs.get("stop", None),
                )
                return clean_response_encoding(message.content[0].text)

            elif backend == "genai":
                response = client.models.generate_content(
                    model=engine,
                    contents=messages[0]["content"],
                    config=GenerateContentConfig(
                        temperature=kwargs.get("temperature", 0),
                        top_p=kwargs.get("top_p", 1),
                        max_output_tokens=kwargs.get("max_tokens", 64000),
                        presence_penalty=kwargs.get("presence_penalty", 0),
                        frequency_penalty=kwargs.get("frequency_penalty", 0),
                        stop_sequences=kwargs.get("stop", None),
                        # thinking_config=ThinkingConfig(thinking_budget=0) # Disables thinking
                    ),
                )
                try:
                    return clean_response_encoding(response.text)
                except ValueError as ve:
                    return clean_response_encoding(f"Model refused to generate a response {ve}")
                except Exception:
                    return clean_response_encoding("")

        except Exception as e:
            print(e)
            time.sleep(1)
            # Rotate API keys and retry if using the genai backend
            if backend == "genai":
                # genai.configure(api_key=next(gemini_key_cycle))
                # time.sleep(10)
                pass


def call_api_model(
    messages,
    model_name,
    temperature=0,
    max_tokens=64000,  # Increased from 512 to allow longer responses
    top_p=1,
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
        client = anthropic.Anthropic(
            api_key=model_config[model_name],
        )
        backend = "anthropic"

    elif "gemini" in model_name:
        engine = model_name
        # client = genai.GenerativeModel(engine)
        # genai.configure(api_key=GEMINI_API_KEYS[1])
        client = genai.Client(
            vertexai=True,
            project=model_config[model_name]["project"],
            location=model_config[model_name]["location"])
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
    return api_request(messages, engine, client, backend, **kwargs)


def worker_function(task, data_list, output_path, lock):
    """
    Processes a single prompt.
    """
    prompt, idx, model_name = task
    messages = [{"role": "user", "content": prompt}]
    
    # Show progress
    print(f"📊 Processing item {idx + 1}/{len(data_list)} with {model_name} (max_tokens=2048)", flush=True)
    
    try:
        response = call_api_model(messages, model_name, max_tokens=2048)  # Explicitly set higher limit
        
        # Clean response to ensure it's valid UTF-8
        if isinstance(response, str):
            # Replace any problematic characters
            response = response.encode('utf-8', errors='replace').decode('utf-8')
        
        # Log the response for monitoring
        # Also write full response to debug file if needed
        debug_log_path = output_path.replace('.jsonl', '_debug_responses.log')
        try:
            with open(debug_log_path, 'a', encoding='utf-8') as debug_f:
                debug_f.write(f"=== Item {idx + 1} ===\n")
                debug_f.write(f"Response length: {len(response)} characters\n")
                debug_f.write(f"Full response: {response}\n")
                debug_f.write(f"{'='*50}\n")
        except Exception as debug_e:
            pass  # Don't let debug logging break the main process
        
        # Break long responses into multiple lines to avoid terminal truncation
        # Use smaller chunks and ensure each line is flushed
        max_line_length = 120  # Shorter lines to avoid terminal issues
        if len(response) > max_line_length:
            # Split into chunks
            response_chunks = []
            for i in range(0, len(response), max_line_length):
                chunk = response[i:i + max_line_length]
                response_chunks.append(chunk)
            
            # Print the first chunk with header
            print(f"🤖 LLM Response for item {idx + 1} (1/{len(response_chunks)}): {response_chunks[0]}", flush=True)
            # Print remaining chunks
            for i, chunk in enumerate(response_chunks[1:], 2):
                print(f"🤖 LLM Response for item {idx + 1} ({i}/{len(response_chunks)}): {chunk}", flush=True)
        else:
            print(f"🤖 LLM Response for item {idx + 1}: {response}", flush=True)
        
        # Write to the file in real-time (append mode)
        with lock:
            try:
                with open(output_path, "a", encoding="utf-8", errors='replace') as f:
                    row = data_list[idx].copy()  # Create a copy to avoid modifying original
                    row["response"] = response
                    # Use the _index field to record the original index
                    row["_index"] = idx
                    row.pop("prompt", None)
                    f.write(json.dumps(row, ensure_ascii=False) + "\n")
            except UnicodeEncodeError as ue:
                print(f"⚠️ Unicode encode error for item {idx + 1}: {str(ue)}")
                # Fallback: write with ASCII encoding
                with open(output_path, "a", encoding="ascii", errors='replace') as f:
                    row = data_list[idx].copy()
                    row["response"] = response.encode('ascii', errors='replace').decode('ascii')
                    row["_index"] = idx
                    row.pop("prompt", None)
                    f.write(json.dumps(row, ensure_ascii=True) + "\n")

        return idx, response
        
    except Exception as e:
        error_msg = f"❌ Error processing item {idx + 1}: {str(e)}"
        print(error_msg)
        
        # Write error response with encoding safety
        with lock:
            try:
                with open(output_path, "a", encoding="utf-8", errors='replace') as f:
                    row = data_list[idx].copy()
                    row["response"] = f"Error: {str(e)}"
                    row["_index"] = idx
                    row.pop("prompt", None)
                    f.write(json.dumps(row, ensure_ascii=False) + "\n")
            except Exception as write_error:
                print(f"⚠️ Could not write error response: {str(write_error)}")
        
        return idx, f"Error: {str(e)}"


def final_sort_jsonl_by_index(file_path):
    """
    Reads an existing JSONL file, sorts it by the '_index' field,
    then overwrites the file. After sorting, you can remove the '_index' field.
    """
    all_data = []
    try:
        with open(file_path, "r", encoding="utf-8", errors='replace') as fin:
            for line_num, line in enumerate(fin, 1):
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                    all_data.append(row)
                except json.JSONDecodeError as e:
                    print(f"⚠️ JSON decode error at line {line_num} in {file_path}: {str(e)}")
                    continue
                except UnicodeDecodeError as e:
                    print(f"⚠️ Unicode decode error at line {line_num} in {file_path}: {str(e)}")
                    continue

        # Sort by '_index'
        all_data.sort(key=lambda x: x.get("_index", 0))

        # Overwrite the file, removing the '_index' field
        with open(file_path, "w", encoding="utf-8", errors='replace') as fout:
            for row in all_data:
                row.pop("_index", None)
                try:
                    fout.write(json.dumps(row, ensure_ascii=False) + "\n")
                except UnicodeEncodeError:
                    # Fallback to ASCII encoding if UTF-8 fails
                    fout.write(json.dumps(row, ensure_ascii=True) + "\n")
                    
    except Exception as e:
        print(f"❌ Error sorting file {file_path}: {str(e)}")
        # Don't raise the error, just log it to prevent experiment failure


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
    print(f"🚀 Starting API collection with {model_name}")
    print(f"📊 Total items to process: {len(prompt_list) - start_index}")
    print(f"🧵 Using {num_threads} threads")
    
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

        # Wait until all threads are done with progress tracking
        completed_count = 0
        for future in tqdm(as_completed(futures), total=len(futures), desc="Processing API calls"):
            try:
                idx, response = future.result()
                completed_count += 1
                print(f"✅ Completed {completed_count}/{len(futures)} API calls")
            except Exception as e:
                print(f"❌ Task failed: {str(e)}")

    print(f"🎉 All API calls completed! Sorting results...")
    
    # After all threads finish, perform a final sort of the output file
    final_sort_jsonl_by_index(output_path)
    
    print(f"✅ Results saved to: {output_path}")


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
