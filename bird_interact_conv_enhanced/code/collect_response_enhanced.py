#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Enhanced Response Processing for BIRD-Interact with SQL Execution

This module processes API responses from LLMs and handles SQL execution tool calls,
integrating the results back into the conversation flow.

Author: Enhanced BIRD-Interact Team
"""

import os
import sys
import json
import argparse
from typing import Dict, Any, List, Optional

# Import the SQL execution tool
from sql_execution_tool import SQLExecutionTool, parse_sql_tool_call, process_llm_response_with_sql_tool


class EnhancedResponseProcessor:
    """Processes LLM responses and handles SQL execution tool calls."""
    
    def __init__(self):
        self.sql_tools = {}  # Cache SQL tools by database name
    
    def get_sql_tool(self, db_name: str) -> SQLExecutionTool:
        """Get or create SQL tool for a database."""
        if db_name not in self.sql_tools:
            self.sql_tools[db_name] = SQLExecutionTool(db_name)
        return self.sql_tools[db_name]
    
    def process_response(self, response_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process a single response that may contain SQL tool calls.
        
        Args:
            response_data: Dictionary containing response data
            
        Returns:
            Updated response data with SQL execution results
        """
        if "response" not in response_data:
            return response_data
        
        original_response = response_data["response"]
        db_name = response_data.get("selected_database", "")
        
        if not db_name:
            # No database specified, can't execute SQL
            return response_data
        
        # Check for SQL execution calls
        sql_query, remaining_response = parse_sql_tool_call(original_response)
        
        if sql_query:
            # Get SQL tool and execute query
            sql_tool = self.get_sql_tool(db_name)
            execution_result = sql_tool.execute_sql(sql_query)
            
            # Format the result for the conversation
            formatted_result = sql_tool.format_result_for_llm(execution_result)
            
            # Update the response data
            response_data["sql_executed"] = True
            response_data["sql_query"] = sql_query
            response_data["sql_result"] = execution_result
            response_data["sql_formatted"] = formatted_result
            
            # Update the response to include SQL execution results
            if remaining_response.strip():
                response_data["response"] = f"{remaining_response.strip()}\n\n{formatted_result}"
            else:
                response_data["response"] = formatted_result
        else:
            response_data["sql_executed"] = False
        
        return response_data


def process_responses_batch(source_file: str, output_file: str):
    """
    Process a batch of responses from a JSONL file.
    
    Args:
        source_file: Path to input JSONL file with responses
        output_file: Path to output JSONL file with processed responses
    """
    processor = EnhancedResponseProcessor()
    
    with open(source_file, 'r', encoding='utf-8') as infile, \
         open(output_file, 'w', encoding='utf-8') as outfile:
        
        for line_num, line in enumerate(infile, 1):
            line = line.strip()
            if not line:
                continue
            
            try:
                response_data = json.loads(line)
                processed_data = processor.process_response(response_data)
                outfile.write(json.dumps(processed_data, ensure_ascii=False) + '\n')
                
            except json.JSONDecodeError as e:
                print(f"Warning: Failed to parse JSON on line {line_num}: {e}")
                # Write the original line to maintain file structure
                outfile.write(line + '\n')
            except Exception as e:
                print(f"Warning: Error processing line {line_num}: {e}")
                # Write the original line to maintain file structure
                outfile.write(line + '\n')


def collect_enhanced_responses(source_path: str, response_path: str, result_path: str):
    """
    Enhanced version of collect_response.py that handles SQL execution.
    
    This function merges source data with API responses and processes any SQL execution calls.
    
    Args:
        source_path: Path to source data JSONL file
        response_path: Path to API responses JSONL file  
        result_path: Path to output merged and processed JSONL file
    """
    # Load source data
    source_data = {}
    try:
        with open(source_path, 'r', encoding='utf-8') as file:
            for line_num, line in enumerate(file, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    instance_id = data.get("instance_id", str(line_num))
                    source_data[instance_id] = data
                except json.JSONDecodeError as e:
                    print(f"Warning: Failed to parse source data line {line_num}: {e}")
    except FileNotFoundError:
        print(f"Warning: Source file {source_path} not found")
        source_data = {}
    
    # Process responses with SQL execution
    processor = EnhancedResponseProcessor()
    
    with open(response_path, 'r', encoding='utf-8') as response_file, \
         open(result_path, 'w', encoding='utf-8') as output_file:
        
        for line_num, line in enumerate(response_file, 1):
            line = line.strip()
            if not line:
                continue
            
            try:
                response_data = json.loads(line)
                
                # Get corresponding source data
                instance_id = response_data.get("instance_id", str(line_num))
                if instance_id in source_data:
                    merged_data = source_data[instance_id].copy()
                    merged_data.update(response_data)
                else:
                    merged_data = response_data
                
                # Process SQL execution if present
                processed_data = processor.process_response(merged_data)
                
                # Write the processed result
                output_file.write(json.dumps(processed_data, ensure_ascii=False) + '\n')
                
            except json.JSONDecodeError as e:
                print(f"Warning: Failed to parse response line {line_num}: {e}")
            except Exception as e:
                print(f"Warning: Error processing response line {line_num}: {e}")


def main():
    parser = argparse.ArgumentParser(description='Enhanced response processing with SQL execution support')
    parser.add_argument('--source_path', type=str, help='Path to source data JSONL file')
    parser.add_argument('--response_path', type=str, required=True, help='Path to API responses JSONL file')
    parser.add_argument('--result_path', type=str, required=True, help='Path to output processed JSONL file')
    parser.add_argument('--mode', type=str, default='collect', choices=['collect', 'process'], 
                        help='Mode: collect (merge and process) or process (process only)')
    
    args = parser.parse_args()
    
    if args.mode == 'collect':
        if not args.source_path:
            print("Error: --source_path is required for collect mode")
            return
        collect_enhanced_responses(args.source_path, args.response_path, args.result_path)
        print(f"Enhanced response collection completed. Output saved to {args.result_path}")
    else:
        process_responses_batch(args.response_path, args.result_path)
        print(f"Response processing completed. Output saved to {args.result_path}")


if __name__ == "__main__":
    main()