#!/usr/bin/env python3
"""
SQL Execution Clustering Utility

This utility provides actual SQL execution and result-based clustering
for the consistency-based approach.
"""

import os
import sys
import json
import hashlib
import psycopg2
import subprocess
from typing import List, Dict, Tuple, Set, Optional
from collections import defaultdict
import logging

class SQLExecutionClusterer:
    """
    Clusters SQL queries based on their actual execution results.
    """
    
    def __init__(self, db_configs: Optional[Dict[str, Dict]] = None):
        """
        Initialize the clusterer with database configurations.
        
        Args:
            db_configs: Dictionary mapping database names to connection configs
        """
        self.db_configs = db_configs or {}
        self.logger = logging.getLogger(__name__)
        
        # Default PostgreSQL configuration for BIRD-Interact
        self.default_config = {
            'host': 'localhost',
            'port': 5432,
            'user': 'postgres',
            'password': 'password'
        }
    
    def normalize_sql(self, sql: str) -> str:
        """Normalize SQL query for execution."""
        # Remove extra whitespace
        sql = ' '.join(sql.split())
        # Remove trailing semicolon
        sql = sql.rstrip(';')
        return sql
    
    def execute_sql_query(self, sql: str, db_name: str) -> Tuple[str, bool, Optional[str]]:
        """
        Execute SQL query and return result signature.
        
        Args:
            sql: SQL query to execute
            db_name: Database name
            
        Returns:
            Tuple of (result_signature, success, error_message)
        """
        try:
            # Get database configuration
            config = self.db_configs.get(db_name, self.default_config.copy())
            config['database'] = db_name.lower()
            
            # Normalize SQL
            normalized_sql = self.normalize_sql(sql)
            
            # Connect and execute
            with psycopg2.connect(**config) as conn:
                with conn.cursor() as cursor:
                    # Set a reasonable timeout
                    cursor.execute("SET statement_timeout = '30s'")
                    
                    # Execute the query
                    cursor.execute(normalized_sql)
                    
                    # Get results
                    if cursor.description:
                        # SELECT query - get column names and data
                        columns = [desc[0] for desc in cursor.description]
                        rows = cursor.fetchall()
                        
                        # Create result signature
                        result_data = {
                            'type': 'select',
                            'columns': columns,
                            'row_count': len(rows),
                            'data_hash': self._hash_result_data(rows)
                        }
                        
                        # For small result sets, include actual data
                        if len(rows) <= 100:  # Small result set
                            result_data['sample_rows'] = rows[:10]  # First 10 rows
                    else:
                        # Non-SELECT query (INSERT, UPDATE, DELETE, etc.)
                        result_data = {
                            'type': 'non_select',
                            'rowcount': cursor.rowcount
                        }
                    
                    # Create signature
                    signature = self._create_result_signature(result_data)
                    return signature, True, None
                    
        except psycopg2.Error as e:
            # Database error
            error_msg = str(e).strip()
            error_signature = f"ERROR:{hashlib.md5(error_msg.encode()).hexdigest()[:8]}"
            return error_signature, False, error_msg
            
        except Exception as e:
            # Other errors
            error_msg = str(e)
            self.logger.error(f"Unexpected error executing SQL: {error_msg}")
            error_signature = f"EXCEPTION:{hashlib.md5(error_msg.encode()).hexdigest()[:8]}"
            return error_signature, False, error_msg
    
    def _hash_result_data(self, rows: List[Tuple]) -> str:
        """Create a hash of result data for comparison."""
        # Convert to string representation and hash
        data_str = json.dumps(rows, sort_keys=True, default=str)
        return hashlib.md5(data_str.encode()).hexdigest()[:12]
    
    def _create_result_signature(self, result_data: Dict) -> str:
        """Create a signature string from result data."""
        if result_data['type'] == 'select':
            # For SELECT queries
            signature_parts = [
                f"SELECT",
                f"cols:{len(result_data['columns'])}",
                f"rows:{result_data['row_count']}",
                f"hash:{result_data['data_hash']}"
            ]
        else:
            # For non-SELECT queries
            signature_parts = [
                result_data['type'].upper(),
                f"affected:{result_data['rowcount']}"
            ]
        
        return "|".join(signature_parts)
    
    def cluster_sql_queries_by_execution(self, sql_queries: List[str], db_name: str) -> Dict:
        """
        Cluster SQL queries based on their execution results.
        
        Args:
            sql_queries: List of SQL query strings
            db_name: Database name to execute against
            
        Returns:
            Dictionary with clustering results
        """
        results = {
            'queries': sql_queries,
            'db_name': db_name,
            'execution_results': [],
            'clusters': [],
            'signatures': [],
            'success_count': 0,
            'error_count': 0
        }
        
        # Execute each query and collect signatures
        signatures = []
        execution_results = []
        
        for i, sql in enumerate(sql_queries):
            self.logger.debug(f"Executing query {i+1}/{len(sql_queries)}")
            
            signature, success, error_msg = self.execute_sql_query(sql, db_name)
            
            signatures.append(signature)
            execution_results.append({
                'query_index': i,
                'signature': signature,
                'success': success,
                'error_message': error_msg
            })
            
            if success:
                results['success_count'] += 1
            else:
                results['error_count'] += 1
        
        results['signatures'] = signatures
        results['execution_results'] = execution_results
        
        # Group by signature to create clusters
        signature_to_indices = defaultdict(list)
        for i, signature in enumerate(signatures):
            signature_to_indices[signature].append(i)
        
        # Convert to cluster format and sort by size
        clusters = []
        for signature, indices in signature_to_indices.items():
            cluster = {
                'signature': signature,
                'indices': indices,
                'size': len(indices),
                'queries': [sql_queries[i] for i in indices],
                'is_successful': execution_results[indices[0]]['success']  # All queries in cluster have same result
            }
            clusters.append(cluster)
        
        # Sort clusters by size (largest first)
        clusters.sort(key=lambda x: x['size'], reverse=True)
        
        results['clusters'] = clusters
        
        return results
    
    def calculate_confidence_from_clusters(self, clustering_results: Dict) -> float:
        """Calculate confidence based on clustering results."""
        clusters = clustering_results['clusters']
        total_queries = len(clustering_results['queries'])
        
        if not clusters or total_queries == 0:
            return 0.0
        
        # Find the largest successful cluster
        largest_successful_size = 0
        for cluster in clusters:
            if cluster['is_successful'] and cluster['size'] > largest_successful_size:
                largest_successful_size = cluster['size']
        
        return largest_successful_size / total_queries
    
    def get_representative_queries(self, clustering_results: Dict, max_representatives: int = 5) -> List[str]:
        """Get representative queries from different clusters."""
        clusters = clustering_results['clusters']
        representatives = []
        
        # Prioritize successful clusters
        successful_clusters = [c for c in clusters if c['is_successful']]
        failed_clusters = [c for c in clusters if not c['is_successful']]
        
        # Add representatives from successful clusters first
        for cluster in successful_clusters[:max_representatives]:
            representatives.append(cluster['queries'][0])  # First query from cluster
        
        # Add representatives from failed clusters if we have space
        remaining_slots = max_representatives - len(representatives)
        for cluster in failed_clusters[:remaining_slots]:
            representatives.append(cluster['queries'][0])
        
        return representatives
    
    def get_best_query_from_clustering(self, clustering_results: Dict) -> Optional[str]:
        """Get the best query from clustering results."""
        clusters = clustering_results['clusters']
        
        # Find the largest successful cluster
        for cluster in clusters:
            if cluster['is_successful'] and cluster['size'] > 0:
                return cluster['queries'][0]  # Return first query from largest successful cluster
        
        # If no successful clusters, return None
        return None

def test_sql_clustering():
    """Test function for SQL clustering."""
    # Example SQL queries that should cluster differently
    test_queries = [
        "SELECT COUNT(*) FROM users",
        "SELECT count(*) FROM users",  # Same result, different formatting
        "SELECT COUNT(DISTINCT user_id) FROM users",  # Different result
        "SELECT SUM(age) FROM users",  # Different result
        "SELECT COUNT(*) FROM users WHERE active = true",  # Different result (subset)
    ]
    
    clusterer = SQLExecutionClusterer()
    
    # Note: This would require an actual database connection
    # For testing without a database, we can mock the execution
    print("SQL Clustering Test")
    print("===================")
    
    for i, sql in enumerate(test_queries):
        print(f"Query {i+1}: {sql}")
    
    print("\nNote: This test requires a live database connection to demonstrate actual clustering.")
    print("In production, queries would be executed against the BIRD-Interact databases.")

if __name__ == "__main__":
    test_sql_clustering()
