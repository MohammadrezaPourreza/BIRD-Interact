#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Consistency Analysis Helper for BIRD-Interact
This script handles SQL execution and consistency analysis for the consistency-based system.
"""
import os  
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.append(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'evaluation', 'src'))

import argparse  
import json   
from typing import Dict, List, Tuple, Any
import hashlib
from collections import Counter
import re

# Import evaluation functions
try:
    from postgresql_utils import execute_queries, get_connection_for_phase, close_postgresql_connection
    from eval_bird_interact import preprocess_results, remove_comments, remove_distinct, remove_round
except ImportError as e:
    print(f"Warning: Could not import evaluation modules: {e}")
    print("SQL execution will use mock results")


def execute_sql_queries(sql_queries: List[str], db_name: str, conn=None) -> List[Any]:
    """
    Execute SQL queries and return their results.
    """
    results = []
    need_close_conn = False
    
    try:
        # Get connection if not provided
        if conn is None:
            conn = get_connection_for_phase(db_name)
            need_close_conn = True
        
        for sql in sql_queries:
            try:
                # Clean the SQL query
                cleaned_sql = remove_comments([sql])[0]
                cleaned_sql = remove_distinct([cleaned_sql])[0]
                cleaned_sql = remove_round([cleaned_sql])[0]
                
                # Execute query
                query_result, execution_error, timeout_error = execute_queries([cleaned_sql], db_name, conn)
                
                if execution_error or timeout_error:
                    # Return error as result
                    results.append(f"Error: execution_error={execution_error}, timeout_error={timeout_error}")
                else:
                    # Preprocess results for comparison
                    if query_result:
                        processed_result = preprocess_results(query_result)
                        # Convert to hashable format for grouping
                        results.append(tuple(processed_result) if processed_result else tuple())
                    else:
                        results.append(tuple())  # Empty result
                        
            except Exception as e:
                results.append(f"Error: {str(e)}")
                
    except Exception as e:
        print(f"Database connection error: {e}")
        # Fallback to mock results
        results = [f"mock_result_for_{hash(sql) % 1000}" for sql in sql_queries]
    
    finally:
        if need_close_conn and conn:
            try:
                close_postgresql_connection(db_name, conn)
            except:
                pass
    
    return results


def extract_sql_from_response(response: str) -> str:
    """Extract SQL query from model response."""
    if "```postgresql" in response:
        start_idx = response.find("```postgresql")
        sql_block = response[start_idx:].replace("```postgresql", "").strip()
        if "```" in sql_block:
            end_idx = sql_block.find("```")
            sql_block = sql_block[:end_idx].strip()
        return sql_block
    elif "<t>" in response and "</t>" in response:
        start_idx = response.find("<t>")
        end_idx = response.find("</t>")
        sql_block = response[start_idx+3:end_idx].strip()
        if "```postgresql" in sql_block:
            sql_block = sql_block.replace("```postgresql", "").replace("```", "").strip()
        return sql_block
    else:
        return response.strip()


def hash_sql_result(sql_result: Any) -> str:
    """Create a hash of SQL execution result for grouping."""
    if sql_result is None:
        return "null_result"
    
    # Convert result to string for hashing
    result_str = str(sql_result)
    return hashlib.md5(result_str.encode()).hexdigest()


def group_queries_by_results(sql_queries: List[str], sql_results: List[Any]) -> Dict[Any, List[str]]:
    """Group SQL queries by their execution results."""
    result_groups = {}
    
    for sql, result in zip(sql_queries, sql_results):
        # Use the result directly as the key (since it's already processed)
        result_key = result if isinstance(result, (tuple, str)) else str(result)
        
        if result_key not in result_groups:
            result_groups[result_key] = []
        result_groups[result_key].append(sql)
    
    return result_groups


def get_highest_confidence_query(result_groups: Dict[Any, List[str]], num_resp: int) -> Tuple[str, float]:
    """Get the query from the largest group and calculate confidence."""
    if not result_groups:
        return "", 0.0
    
    # Find the largest group
    largest_group_key = max(result_groups.keys(), key=lambda k: len(result_groups[k]))
    largest_group = result_groups[largest_group_key]
    
    # Calculate confidence
    confidence = len(largest_group) / num_resp
    
    # Return the first query from the largest group
    highest_confidence_query = largest_group[0]
    
    return highest_confidence_query, confidence


def process_consistency_responses(response_file: str, output_file: str):
    """
    Process multiple SQL generation responses and perform consistency analysis.
    
    Args:
        response_file: JSONL file containing multiple responses for each instance
        output_file: Output file with consistency analysis results
    """
    
    # Group responses by instance_id
    instance_responses = {}
    with open(response_file, 'r', encoding='utf-8') as f:
        for line in f:
            response = json.loads(line)
            instance_id = response.get('instance_id')
            if instance_id not in instance_responses:
                instance_responses[instance_id] = []
            instance_responses[instance_id].append(response)
    
    processed_instances = []
    
    for instance_id, responses in instance_responses.items():
        if not responses:
            continue
            
        # Extract SQL queries from responses
        sql_queries = []
        for response in responses:
            if 'response' in response:
                sql = extract_sql_from_response(response['response'])
                if sql:
                    sql_queries.append(sql)
        
        if not sql_queries:
            continue
            
        # Execute SQL queries using the evaluation framework
        db_name = responses[0].get('selected_database', 'default')
        sql_results = execute_sql_queries(sql_queries, db_name)
        
        # Group by results
        result_groups = group_queries_by_results(sql_queries, sql_results)
        
        # Get highest confidence query
        highest_confidence_query, confidence = get_highest_confidence_query(result_groups, len(sql_queries))
        
        # Create processed instance
        processed_instance = responses[0].copy()  # Start with first response as base
        processed_instance.update({
            'generated_sql_queries': sql_queries,
            'sql_execution_results': sql_results,
            'result_groups_count': {k: len(v) for k, v in result_groups.items()},
            'highest_confidence_query': highest_confidence_query,
            'confidence': confidence,
            'consistency_mode': 'analyze_consistency',
            'num_unique_results': len(result_groups)
        })
        
        processed_instances.append(processed_instance)
    
    # Write processed instances
    with open(output_file, 'w', encoding='utf-8') as f:
        for instance in processed_instances:
            f.write(json.dumps(instance, ensure_ascii=False) + '\n')


def main():
    parser = argparse.ArgumentParser(description='Process consistency responses for BIRD-Interact')
    parser.add_argument('--response_file', type=str, required=True, 
                       help='JSONL file containing multiple responses')
    parser.add_argument('--output_file', type=str, required=True,
                       help='Output file for processed consistency data')
    
    args = parser.parse_args()
    
    process_consistency_responses(args.response_file, args.output_file)


if __name__ == "__main__":
    main()
