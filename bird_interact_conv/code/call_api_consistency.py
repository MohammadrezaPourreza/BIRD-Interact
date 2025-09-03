#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Modified API caller for consistency-based system that can generate multiple responses.
"""
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


def write_jsonl(data, file_path):
    with open(file_path, "w", encoding="utf-8") as file:
        for item in data:
            file.write(json.dumps(item, ensure_ascii=False) + "\n")


@retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=1, min=4, max=60), 
       retry=retry_if_exception_type((Exception,)))
def call_openai_api(client, prompt, model_name, max_tokens=4096, temperature=0.0):
    try:
        response = client.chat.completions.create(
            model=model_name,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
            temperature=temperature
        )
        return response.choices[0].message.content, response.usage
    except Exception as e:
        if is_rate_limit_error(e):
            print(f"Rate limit hit for OpenAI, retrying: {e}")
            time.sleep(10)
        raise e


@retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=1, min=4, max=60), 
       retry=retry_if_exception_type((Exception,)))
def call_gemini_api(client, prompt, model_name, max_tokens=4096, temperature=0.0):
    try:
        response = client.models.generate_content(
            model=model_name,
            contents=prompt,
            config=types.GenerateContentConfig(
                max_output_tokens=max_tokens,
                temperature=temperature,
            )
        )
        
        if not response or not response.text:
            print("Received empty response from Gemini API.")
            raise ValueError("Empty response from Gemini API")
        return response.text, None
    except Exception as e:
        if is_rate_limit_error(e):
            print(f"Rate limit hit for Gemini, retrying: {e}")
            time.sleep(10)
        raise e


@retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=1, min=4, max=60), 
       retry=retry_if_exception_type((Exception,)))
def call_claude_api(client, prompt, model_name, max_tokens=4096, temperature=0.0):
    try:
        response = client.messages.create(
            model=model_name,
            max_tokens=max_tokens,
            temperature=temperature,
            messages=[{"role": "user", "content": prompt}]
        )
        return response.content[0].text, response.usage
    except Exception as e:
        if is_rate_limit_error(e):
            print(f"Rate limit hit for Claude, retrying: {e}")
            time.sleep(10)
        raise e


def get_api_client(model_name):
    """Get the appropriate API client based on model name."""
    config = model_config.get(model_name)
    if not config:
        raise ValueError(f"Model {model_name} not found in config")
    
    if "gpt" in model_name.lower():
        return OpenAI(
            base_url=config["base_url"],
            api_key=config["api_key"]
        )
    elif "gemini" in model_name.lower():
        return genai.Client(
            vertexai=True, 
            project=config["project"], 
            location=config["location"]
        )
    elif "claude" in model_name.lower():
        return AnthropicVertex(
            project_id=config["project"],
            region=config["location"]
        )
    else:
        raise ValueError(f"Unsupported model: {model_name}")


def call_model_api(client, prompt, model_name, max_tokens=4096, temperature=0.0):
    """Call the appropriate model API."""
    if "gpt" in model_name.lower():
        return call_openai_api(client, prompt, model_name, max_tokens, temperature)
    elif "gemini" in model_name.lower():
        return call_gemini_api(client, prompt, model_name, max_tokens, temperature)
    elif "claude" in model_name.lower():
        return call_claude_api(client, prompt, model_name, max_tokens, temperature)
    else:
        raise ValueError(f"Unsupported model: {model_name}")


def process_single_item_multiple_responses(item, model_name, num_responses=1, max_tokens=4096, temperature=0.0):
    """Process a single item and generate multiple responses."""
    try:
        client = get_api_client(model_name)
        prompt = item["prompt"]
        responses = []
        
        for i in range(num_responses):
            try:
                # Use slight temperature variation for diversity in multiple responses
                temp = temperature if i == 0 else min(temperature + 0.1 * i, 1.0)
                response_text, token_usage = call_model_api(client, prompt, model_name, max_tokens, temp)
                
                response_item = item.copy()
                response_item["response"] = response_text
                response_item["response_index"] = i
                if token_usage:
                    response_item["token_usage"] = token_usage
                responses.append(response_item)
                
                # Small delay between requests to avoid rate limiting
                if i < num_responses - 1:
                    time.sleep(0.5)
                    
            except Exception as e:
                print(f"Error processing response {i} for item {item.get('instance_id', 'unknown')}: {e}")
                error_response = item.copy()
                error_response["response"] = f"Error: {str(e)}"
                error_response["response_index"] = i
                responses.append(error_response)
        
        return responses
        
    except Exception as e:
        print(f"Error processing item {item.get('instance_id', 'unknown')}: {e}")
        error_response = item.copy()
        error_response["response"] = f"Error: {str(e)}"
        error_response["response_index"] = 0
        return [error_response]


def process_multiple_responses_parallel(data, model_name, num_responses=1, max_workers=5, max_tokens=4096, temperature=0.0):
    """Process data with multiple responses using parallel execution."""
    all_responses = []
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks
        future_to_item = {}
        for item in data:
            # Check if this item needs multiple responses
            item_num_responses = item.get('num_resp', num_responses)
            future = executor.submit(
                process_single_item_multiple_responses,
                item, model_name, item_num_responses, max_tokens, temperature
            )
            future_to_item[future] = item
        
        # Collect results
        for future in tqdm(as_completed(future_to_item), total=len(future_to_item), desc="Processing"):
            item = future_to_item[future]
            try:
                responses = future.result()
                all_responses.extend(responses)
            except Exception as e:
                print(f"Error processing item {item.get('instance_id', 'unknown')}: {e}")
                error_response = item.copy()
                error_response["response"] = f"Error: {str(e)}"
                all_responses.append(error_response)
    
    return all_responses


def main():
    parser = argparse.ArgumentParser(description='Call various LLM APIs with multiple response support')
    parser.add_argument('--model_name', type=str, required=True, help='Model name to use')
    parser.add_argument('--prompt_path', type=str, required=True, help='Path to JSONL file with prompts')
    parser.add_argument('--output_path', type=str, required=True, help='Output path for responses')
    parser.add_argument('--num_responses', type=int, default=1, help='Number of responses per prompt')
    parser.add_argument('--max_workers', type=int, default=5, help='Maximum number of parallel workers')
    parser.add_argument('--max_tokens', type=int, default=4096, help='Maximum tokens in response')
    parser.add_argument('--temperature', type=float, default=0.0, help='Temperature for response generation')
    
    args = parser.parse_args()
    
    # Load data
    data = load_jsonl(args.prompt_path)
    
    # Process with multiple responses
    results = process_multiple_responses_parallel(
        data, 
        args.model_name, 
        args.num_responses,
        args.max_workers,
        args.max_tokens,
        args.temperature
    )
    
    # Save results
    write_jsonl(results, args.output_path)
    print(f"Processed {len(data)} items, generated {len(results)} responses, saved to {args.output_path}")


if __name__ == "__main__":
    main()
