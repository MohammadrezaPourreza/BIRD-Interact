#!/usr/bin/env python
# -*- coding: utf-8 -*-
import os  
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import argparse  
import json   
import re
from collections import defaultdict, Counter
from typing import List, Dict, Tuple, Set

def extract_sql_from_response(response: str) -> str:
    """Extract SQL query from LLM response."""
    # Look for SQL between ```postgresql and ```
    pattern = r'```postgresql\s*(.*?)\s*```'
    matches = re.findall(pattern, response, re.DOTALL | re.IGNORECASE)
    if matches:
        return matches[-1].strip()  # Take the last match
    
    # Fallback: look for SQL between ``` and ```
    pattern = r'```\s*(.*?)\s*```'
    matches = re.findall(pattern, response, re.DOTALL)
    if matches:
        return matches[-1].strip()
    
    # If no code blocks found, return the whole response
    return response.strip()

def normalize_sql(sql: str) -> str:
    """Normalize SQL query for comparison."""
    # Remove extra whitespace and normalize case
    sql = re.sub(r'\s+', ' ', sql.strip())
    # Remove trailing semicolons
    sql = sql.rstrip(';')
    return sql

import re
from collections import defaultdict, Counter
from typing import List, Dict, Tuple, Set

def execute_sql_for_clustering(sql_query: str, db_name: str) -> Tuple[str, bool]:
    """
    Execute SQL query to get result for clustering using SQLEquivalenceChecker.
    Returns (result_signature, success_flag)
    """
    # Use the SQLEquivalenceChecker for execution and result comparison
    from evaluation.src.sql_equivalence_checker import SQLEquivalenceChecker
    
    checker = SQLEquivalenceChecker()
    
    # Execute the SQL query to get results
    result = checker.execute_sql(sql_query, db_name)
    
    if result['success']:
        # Create a signature based on the execution result
        if result['result_data']:
            # Hash the result data for comparison
            import hashlib
            import json
            result_str = json.dumps(result['result_data'], sort_keys=True, default=str)
            result_hash = hashlib.md5(result_str.encode()).hexdigest()[:12]
            signature = f"SUCCESS:{result_hash}:{len(result['result_data'])}"
        else:
            # Empty result set
            signature = "SUCCESS:EMPTY:0"
        return signature, True
    else:
        # Error occurred - use error message for clustering
        import hashlib
        error_hash = hashlib.md5(result['error'].encode()).hexdigest()[:8]
        signature = f"ERROR:{error_hash}"
        return signature, False
            

def cluster_sql_queries(sql_queries: List[str], db_name: str) -> List[List[int]]:
    """
    Cluster SQL queries based on their execution results using SQLEquivalenceChecker.
    Returns list of clusters, where each cluster is a list of indices.
    """
    try:
        # Use the SQLEquivalenceChecker for semantic clustering
        from evaluation.src.sql_equivalence_checker import SQLEquivalenceChecker
        
        checker = SQLEquivalenceChecker()
        
        # Execute all queries and collect results
        query_results = []
        for i, sql in enumerate(sql_queries):
            result = checker.execute_sql(sql, db_name)
            query_results.append({
                'index': i,
                'sql': sql,
                'result': result
            })
        
        # Cluster queries based on semantic equivalence
        clusters = []
        processed_indices = set()
        
        for i, query_data in enumerate(query_results):
            if i in processed_indices:
                continue
                
            # Start a new cluster with this query
            current_cluster = [i]
            processed_indices.add(i)
            
            # Find all other queries that are semantically equivalent
            for j, other_query_data in enumerate(query_results):
                if j in processed_indices:
                    continue
                
                # Check if queries are semantically equivalent
                equiv_result = checker.check_equivalence(
                    predicted_sql=query_data['sql'],
                    ground_truth_sql=other_query_data['sql'],
                    db_name=db_name
                )
                
                if equiv_result['equivalent']:
                    current_cluster.append(j)
                    processed_indices.add(j)
            
            clusters.append(current_cluster)
        
        # Sort clusters by size (largest first)
        clusters.sort(key=len, reverse=True)
        
        return clusters
        
    except ImportError:
        # Fallback to signature-based clustering if SQLEquivalenceChecker not available
        signatures = []
        for sql in sql_queries:
            signature, success = execute_sql_for_clustering(sql, db_name)
            signatures.append(signature)
        
        # Group queries by signature
        signature_to_indices = defaultdict(list)
        for i, signature in enumerate(signatures):
            signature_to_indices[signature].append(i)
        
        # Convert to list of clusters
        clusters = list(signature_to_indices.values())
        
        # Sort clusters by size (largest first)
        clusters.sort(key=len, reverse=True)
        
        return clusters
        
    except Exception as e:
        # Log the error but continue with fallback
        import logging
        logging.warning(f"Error in semantic clustering: {e}, falling back to signature-based clustering")
        
        # Fallback to signature-based clustering
        signatures = []
        for sql in sql_queries:
            signature, success = execute_sql_for_clustering(sql, db_name)
            signatures.append(signature)
        
        # Group queries by signature
        signature_to_indices = defaultdict(list)
        for i, signature in enumerate(signatures):
            signature_to_indices[signature].append(i)
        
        # Convert to list of clusters
        clusters = list(signature_to_indices.values())
        
        # Sort clusters by size (largest first)
        clusters.sort(key=len, reverse=True)
        
        return clusters

def select_representative_queries(detailed_clusters: List[Dict], max_representatives: int = 5) -> List[str]:
    """Select one representative query from each cluster."""
    representatives = []
    
    # Prioritize successful clusters
    successful_clusters = [c for c in detailed_clusters if c['execution_success']]
    failed_clusters = [c for c in detailed_clusters if not c['execution_success']]
    
    # Add representatives from successful clusters first
    for cluster in successful_clusters[:max_representatives]:
        representatives.append(cluster['representative_query'])
    
    # Add representatives from failed clusters if we have space
    remaining_slots = max_representatives - len(representatives)
    for cluster in failed_clusters[:remaining_slots]:
        representatives.append(cluster['representative_query'])
    
    return representatives

def calculate_confidence(clusters: List[List[int]], total_samples: int) -> float:
    """Calculate confidence based on largest cluster size."""
    if not clusters or total_samples == 0:
        return 0.0
    
    largest_cluster_size = len(clusters[0])  # clusters are sorted by size
    return largest_cluster_size / total_samples

def format_sql_queries_for_prompt(sql_queries: List[str]) -> str:
    """Format SQL queries for the disambiguator prompt."""
    formatted = []
    for i, sql in enumerate(sql_queries, 1):
        formatted.append(f"Interpretation {i}:\n```postgresql\n{sql}\n```")
    return "\n\n".join(formatted)

def wrap_up_consistency_prompt(data, DB_schema_path, external_kg_path, prompt_template, 
                             samples=10, confidence_threshold=0.6, turn_i=1, data_user_dict=None, phase="amb"):    
    """
    Create prompts for consistency-based SQL generation.
    """
    if "prompt" in data:
        del data["prompt"]
    
    # Handle error cases
    error_flg = False
    if 'prediction_turn_'+str(turn_i) in data and "Error:" in data['prediction_turn_'+str(turn_i)]:
        error_flg = True
        data["error_flg"] = error_flg
    else:
        data["error_flg"] = error_flg
    
    return_flg = 'prediction_turn_'+str(turn_i) in data and "Error:" not in data['prediction_turn_'+str(turn_i)]
    
    # Get user data if available
    if data_user_dict:
        data_user = data_user_dict.get(data["instance_id"], {})
    else:
        data_user = {}
    
    if phase == "amb":
        if "Terminate_flg" in data or return_flg:
            terminate_flag = True
            return data
        
        # Load database schema and external knowledge
        db_name = data.get('selected_database', '')
        question = data.get('amb_user_query', '')
        
        with open(DB_schema_path.replace("[[DB_name]]", db_name), 'r', encoding='utf-8') as file:
            DB_schema = file.read()
        
        # Handle external knowledge exclusions
        external_kg_list = []
        exclude_ids = []
        if "knowledge_ambiguity" in data:
            for knowledge_amb_i in data["knowledge_ambiguity"]:
                exclude_ids.append(knowledge_amb_i["deleted_knowledge"])
                
        with open(external_kg_path.replace("[[DB_name]]", db_name), "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                obj = json.loads(line)
                if obj.get("id") not in exclude_ids:
                    external_kg_list.append(json.dumps(obj))

        external_kg = "\n".join(external_kg_list)

        if turn_i == 1:
            # First turn: Generate multiple SQL queries for consistency check
            prompt = prompt_template.replace('[[user_query]]', question)
            prompt = prompt.replace('[[DB_name]]', db_name)
            prompt = prompt.replace('[[DB_schema]]', DB_schema)
            prompt = prompt.replace('[[external_kg]]', external_kg)
            
            # Store metadata for consistency processing
            data['consistency_samples'] = samples
            data['consistency_threshold'] = confidence_threshold
            data['db_name'] = db_name
            data['DB_schema'] = DB_schema
            data['external_kg'] = external_kg
            data['original_question'] = question
        
        else:
            # Later turns: Handle user response to clarification
            # This should be implemented when we have user responses
            prompt = data.get('prompt_turn_'+str(turn_i-1), '')
            # Add user response handling logic here
            # For now, return as is
            pass
            
        data['prompt_turn_'+str(turn_i)] = prompt
        data["prompt"] = prompt
        data['final_turn'] = turn_i
            
    elif phase in ["debug", "follow"]:
        # For debug and follow-up phases, generate multiple samples and pick from largest cluster
        db_name = data.get('db_name', data.get('selected_database', ''))
        
        if phase == "debug" and data_user and data_user.get("status") == "failed":
            # Debug phase: regenerate based on error
            question = data.get('original_question', data.get('amb_user_query', ''))
            error_msg = data_user.get("error_msg", "")
            
            prompt = prompt_template.replace('[[user_query]]', 
                f"{question}\n\nNote: Previous SQL had an error: {error_msg}. Please generate a corrected version.")
                
        elif phase == "follow" and data_user and data_user.get("status") == "success":
            # Follow-up phase: handle follow-up question
            follow_up_Q = data.get('follow_up', {}).get('query', '')
            prompt = prompt_template.replace('[[user_query]]', follow_up_Q)
        
        else:
            # Fallback
            question = data.get('original_question', data.get('amb_user_query', ''))
            prompt = prompt_template.replace('[[user_query]]', question)
        
        # Load schema and external knowledge
        with open(DB_schema_path.replace("[[DB_name]]", db_name), 'r', encoding='utf-8') as file:
            DB_schema = file.read()
            
        # Handle external knowledge exclusions (simplified for debug/follow)
        external_kg_list = []
        with open(external_kg_path.replace("[[DB_name]]", db_name), "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                obj = json.loads(line)
                external_kg_list.append(json.dumps(obj))
        
        external_kg = "\n".join(external_kg_list)
        
        prompt = prompt.replace('[[DB_name]]', db_name)
        prompt = prompt.replace('[[DB_schema]]', DB_schema)
        prompt = prompt.replace('[[external_kg]]', external_kg)
        
        # Store metadata
        data['consistency_samples'] = samples
        data['consistency_mode'] = 'select_best'  # Just select from largest cluster
        data['db_name'] = db_name
        
        turn_key = f'prediction_turn_{turn_i}' if turn_i > 1 else 'prediction_turn_1'
        data[f'prompt_turn_{turn_i}'] = prompt
        data["prompt"] = prompt
        data['final_turn'] = turn_i

    return data

def process_consistency_responses(data, responses: List[str], phase="amb"):
    """
    Process multiple responses for consistency-based approach using SQLEquivalenceChecker.
    """
    # Extract SQL queries from responses
    sql_queries = []
    for response in responses:
        sql = extract_sql_from_response(response)
        if sql:
            sql_queries.append(sql)
    
    if not sql_queries:
        # No valid SQL found
        data['consistency_result'] = 'no_sql_found'
        return data
    
    # Cluster the SQL queries using semantic equivalence
    clusters = cluster_sql_queries(sql_queries, data.get('db_name', ''))
    
    # Calculate confidence
    confidence = calculate_confidence(clusters, len(sql_queries))
    
    # Store clustering results with detailed information
    detailed_clusters = []
    try:
        from evaluation.src.sql_equivalence_checker import SQLEquivalenceChecker
        checker = SQLEquivalenceChecker()
        
        for cluster_indices in clusters:
            cluster_queries = [sql_queries[i] for i in cluster_indices]
            
            # Execute the first query to get result info
            first_query = cluster_queries[0]
            execution_result = checker.execute_sql(first_query, data.get('db_name', ''))
            
            cluster_info = {
                'size': len(cluster_indices),
                'indices': cluster_indices,
                'queries': cluster_queries,
                'representative_query': first_query,
                'execution_success': execution_result['success'],
                'result_summary': {
                    'success': execution_result['success'],
                    'row_count': len(execution_result['result_data']) if execution_result['success'] and execution_result['result_data'] else 0,
                    'error': execution_result.get('error', None) if not execution_result['success'] else None
                }
            }
            detailed_clusters.append(cluster_info)
            
    except ImportError:
        # Fallback to simple cluster information
        for cluster_indices in clusters:
            cluster_queries = [sql_queries[i] for i in cluster_indices]
            cluster_info = {
                'size': len(cluster_indices),
                'indices': cluster_indices,
                'queries': cluster_queries,
                'representative_query': cluster_queries[0],
                'execution_success': True,  # Assume success for fallback
                'result_summary': {'success': True, 'row_count': 'unknown', 'error': None}
            }
            detailed_clusters.append(cluster_info)
    
    data['consistency_clusters'] = detailed_clusters
    data['consistency_confidence'] = confidence
    data['consistency_total_samples'] = len(sql_queries)
    
    # Log clustering information
    cluster_summary = []
    for i, cluster in enumerate(detailed_clusters):
        success_str = "✓" if cluster['execution_success'] else "✗"
        cluster_summary.append(f"Cluster {i+1}: {cluster['size']} queries {success_str}")
    
    data['consistency_cluster_summary'] = "; ".join(cluster_summary)
    
    if phase == "amb":
        # Check if confidence is above threshold
        threshold = data.get('consistency_threshold', 0.6)
        
        if confidence >= threshold:
            # High confidence: use the query from largest successful cluster
            best_cluster = None
            for cluster in detailed_clusters:
                if cluster['execution_success']:
                    best_cluster = cluster
                    break
            
            if best_cluster:
                data['consistency_result'] = 'high_confidence'
                data['final_sql'] = best_cluster['representative_query']
                data['Terminate_flg'] = True
                data['confidence_reason'] = f"Largest successful cluster has {best_cluster['size']}/{len(sql_queries)} queries ({confidence:.1%})"
            else:
                # No successful clusters
                data['consistency_result'] = 'no_successful_queries'
                data['final_sql'] = detailed_clusters[0]['representative_query']  # Use largest cluster anyway
                data['Terminate_flg'] = True
                data['confidence_reason'] = "No successful executions, using most common query"
        else:
            # Low confidence: need clarification
            data['consistency_result'] = 'need_clarification'
            # Get representative queries for disambiguation (only successful ones if possible)
            successful_clusters = [c for c in detailed_clusters if c['execution_success']]
            if successful_clusters:
                representatives = [cluster['representative_query'] for cluster in successful_clusters[:3]]  # Top 3 successful
            else:
                representatives = [cluster['representative_query'] for cluster in detailed_clusters[:3]]  # Top 3 overall
            
            data['consistency_representatives'] = representatives
            data['confidence_reason'] = f"Low confidence: largest cluster has only {detailed_clusters[0]['size']}/{len(sql_queries)} queries ({confidence:.1%})"
    
    else:  # debug or follow phase
        # Just select the most common successful interpretation
        best_cluster = None
        for cluster in detailed_clusters:
            if cluster['execution_success']:
                best_cluster = cluster
                break
        
        if best_cluster:
            data['consistency_result'] = 'selected_best'
            data['final_sql'] = best_cluster['representative_query']
            data['confidence_reason'] = f"Selected from largest successful cluster ({best_cluster['size']}/{len(sql_queries)} queries)"
        else:
            # No successful clusters, use largest anyway
            data['consistency_result'] = 'selected_largest'
            data['final_sql'] = detailed_clusters[0]['representative_query']
            data['confidence_reason'] = f"No successful executions, selected from largest cluster ({detailed_clusters[0]['size']}/{len(sql_queries)} queries)"
        
        data['Terminate_flg'] = True
    
    return data

def load_from_jsonl_dataset(prompt_path, user_resp_path, result_path, DB_schema_path, external_kg_path, 
                           prompt_template, samples, confidence_threshold, turn_i, phase="amb"):
    """
    Load dataset and prepare prompts for consistency-based approach.
    """
    # Load user responses if available
    dataset_user = {}
    if user_resp_path and os.path.exists(user_resp_path):
        with open(user_resp_path, 'r') as f:
            for line in f:
                dict_item = json.loads(line)
                dataset_user[dict_item["instance_id"]] = dict_item
    
    # Load main dataset
    with open(prompt_path, 'r') as f:
        dataset = [json.loads(line) for line in f]
    
    # Process each item
    processed_dataset = []
    for item in dataset:
        processed_item = wrap_up_consistency_prompt(
            item, DB_schema_path, external_kg_path, prompt_template, 
            samples, confidence_threshold, turn_i, dataset_user, phase
        )
        processed_dataset.append(processed_item)
    
    # Save results
    with open(result_path, "w", encoding="utf-8") as f:
        for item in processed_dataset:
            if "prompt" in item:
                json_line = json.dumps(item, ensure_ascii=False)
                f.write(json_line + "\n")

def inference():  
    parser = argparse.ArgumentParser(description='Consistency-based SQL generation with clustering.')  
    parser.add_argument('--samples', type=int, default=10, help='Number of SQL samples to generate.')   
    parser.add_argument('--confidence_threshold', type=float, default=0.6, help='Confidence threshold for accepting SQL.')   
    parser.add_argument('--turn_num', type=int, default=1, help='Turn number.')   
    parser.add_argument('--prompt_path', type=str, required=True, help='Path to the input .jsonl file containing prompts.')  
    parser.add_argument('--user_resp_path', type=str, required=False, help='Path to the user_resp.jsonl file containing user responses.')
    parser.add_argument('--result_path', type=str, required=True, help='Path where the output .jsonl file with results will be saved.')  
    parser.add_argument('--DB_schema_path', type=str, required=True, help='Path where the DB_schema.json file will be saved.')
    parser.add_argument('--external_kg_path', type=str, required=True, help='Path where the external_kg.json file will be saved.')  
    parser.add_argument('--phase', type=str, required=False, default='amb', help='The phase you want to proceed: ["amb", "debug", "follow"]')

    args = parser.parse_args()  
    
    # Import the new consistency prompt
    from bird_interact_conv.prompts.prompts import system_consistency_single
    prompt_template = system_consistency_single

    load_from_jsonl_dataset(
        prompt_path=args.prompt_path, 
        user_resp_path=args.user_resp_path, 
        result_path=args.result_path, 
        DB_schema_path=args.DB_schema_path, 
        external_kg_path=args.external_kg_path, 
        prompt_template=prompt_template, 
        samples=args.samples,
        confidence_threshold=args.confidence_threshold,
        turn_i=args.turn_num, 
        phase=args.phase
    )
 
if __name__ == "__main__":  
    inference()
