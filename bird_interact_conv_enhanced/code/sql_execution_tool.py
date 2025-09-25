#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
SQL Execution Tool for BIRD-Interact Enhanced

This tool allows LLMs to execute SQL queries directly during the clarification phase,
enabling iterative exploration and refinement of queries before providing the final answer.

Author: Enhanced BIRD-Interact Team
"""

import os
import sys
import json
import re
import traceback
from typing import Dict, Any, List, Tuple, Optional

# Add evaluation utils to path
sys.path.append(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'evaluation', 'src'))

try:
    from postgresql_utils import perform_query_on_postgresql_databases, get_connection_for_phase
except ImportError:
    print("Warning: Could not import postgresql_utils. SQL execution will not be available.")
    perform_query_on_postgresql_databases = None


class SQLExecutionTool:
    """
    A tool that allows LLMs to execute SQL queries during conversations.
    """
    
    def __init__(self, db_name: str, max_rows: int = 100, timeout_seconds: int = 30):
        """
        Initialize the SQL execution tool.
        
        Args:
            db_name: Name of the database to execute queries against
            max_rows: Maximum number of rows to return in results
            timeout_seconds: Query timeout in seconds
        """
        self.db_name = db_name
        self.max_rows = max_rows
        self.timeout_seconds = timeout_seconds
        
    def execute_sql(self, sql_query: str) -> Dict[str, Any]:
        """
        Execute a SQL query and return results or error information.
        
        Args:
            sql_query: The SQL query to execute
            
        Returns:
            Dict containing either results or error information
        """
        if perform_query_on_postgresql_databases is None:
            return {
                "success": False,
                "error": "SQL execution not available - postgresql_utils not imported",
                "error_type": "system_error"
            }
            
        try:
            # Clean the SQL query
            sql_query = sql_query.strip()
            if not sql_query:
                return {
                    "success": False,
                    "error": "Empty SQL query provided",
                    "error_type": "invalid_input"
                }
            
            # Execute the query
            result, _ = perform_query_on_postgresql_databases(sql_query, self.db_name)
            
            if result is None:
                # Query executed but returned no result (e.g., INSERT, UPDATE, DELETE)
                return {
                    "success": True,
                    "result": "Query executed successfully (no result set returned)",
                    "rows_affected": "Unknown",
                    "query_type": self._get_query_type(sql_query)
                }
            
            # Format the result
            if isinstance(result, list):
                # Limit the number of rows returned
                limited_result = result[:self.max_rows]
                truncated = len(result) > self.max_rows
                
                return {
                    "success": True,
                    "result": limited_result,
                    "total_rows": len(result),
                    "displayed_rows": len(limited_result),
                    "truncated": truncated,
                    "query_type": self._get_query_type(sql_query),
                    "columns": self._get_column_info(limited_result) if limited_result else []
                }
            else:
                return {
                    "success": True,
                    "result": str(result),
                    "query_type": self._get_query_type(sql_query)
                }
                
        except Exception as e:
            error_message = str(e)
            error_type = self._classify_error(error_message)
            
            return {
                "success": False,
                "error": error_message,
                "error_type": error_type,
                "query": sql_query,
                "suggestion": self._get_error_suggestion(error_type, error_message)
            }
    
    def _get_query_type(self, sql_query: str) -> str:
        """Determine the type of SQL query."""
        sql_lower = sql_query.strip().lower()
        if sql_lower.startswith('select'):
            return 'SELECT'
        elif sql_lower.startswith('insert'):
            return 'INSERT'
        elif sql_lower.startswith('update'):
            return 'UPDATE'
        elif sql_lower.startswith('delete'):
            return 'DELETE'
        elif sql_lower.startswith('create'):
            return 'CREATE'
        elif sql_lower.startswith('drop'):
            return 'DROP'
        elif sql_lower.startswith('alter'):
            return 'ALTER'
        elif sql_lower.startswith('with'):
            return 'CTE'
        else:
            return 'OTHER'
    
    def _get_column_info(self, result: List) -> List[str]:
        """Extract column information from result set."""
        if not result or not isinstance(result, list):
            return []
        
        if isinstance(result[0], (list, tuple)):
            # If we have row data, we can't easily get column names without cursor description
            # Return generic column names
            if result[0]:
                return [f"column_{i+1}" for i in range(len(result[0]))]
        
        return []
    
    def _classify_error(self, error_message: str) -> str:
        """Classify the type of error for better suggestions."""
        error_lower = error_message.lower()
        
        if 'syntax error' in error_lower or 'invalid syntax' in error_lower:
            return 'syntax_error'
        elif 'does not exist' in error_lower:
            if 'relation' in error_lower or 'table' in error_lower:
                return 'table_not_found'
            elif 'column' in error_lower:
                return 'column_not_found'
            else:
                return 'object_not_found'
        elif 'permission denied' in error_lower or 'access denied' in error_lower:
            return 'permission_error'
        elif 'timeout' in error_lower or 'time limit' in error_lower:
            return 'timeout_error'
        elif 'connection' in error_lower:
            return 'connection_error'
        elif 'type' in error_lower and ('mismatch' in error_lower or 'cannot' in error_lower):
            return 'type_error'
        elif 'unique constraint' in error_lower or 'duplicate' in error_lower:
            return 'constraint_violation'
        else:
            return 'unknown_error'
    
    def _get_error_suggestion(self, error_type: str, error_message: str) -> str:
        """Provide helpful suggestions based on error type."""
        suggestions = {
            'syntax_error': "Check your SQL syntax. Common issues include missing commas, incorrect keywords, or unmatched parentheses.",
            'table_not_found': "The table name might be misspelled or doesn't exist. Check the database schema or use correct table name.",
            'column_not_found': "The column name might be misspelled or doesn't exist in the specified table. Verify column names in the schema.",
            'object_not_found': "The database object (function, index, etc.) doesn't exist. Check the schema or spelling.",
            'permission_error': "You don't have permission to perform this operation on the database object.",
            'timeout_error': "The query took too long to execute. Consider optimizing the query or adding appropriate indexes.",
            'connection_error': "There's an issue connecting to the database. Check database availability.",
            'type_error': "There's a data type mismatch. Check that you're comparing compatible data types.",
            'constraint_violation': "The operation violates a database constraint (unique, foreign key, etc.).",
            'unknown_error': "An unexpected error occurred. Review the query and error message carefully."
        }
        
        return suggestions.get(error_type, "Review the error message and adjust your query accordingly.")
    
    def format_result_for_llm(self, execution_result: Dict[str, Any]) -> str:
        """
        Format the execution result in a way that's easy for LLMs to understand.
        
        Args:
            execution_result: The result from execute_sql method
            
        Returns:
            Formatted string representation
        """
        if not execution_result['success']:
            error_msg = f"❌ **SQL Execution Error**\n"
            error_msg += f"**Error Type:** {execution_result['error_type']}\n"
            error_msg += f"**Error Message:** {execution_result['error']}\n"
            if 'suggestion' in execution_result:
                error_msg += f"**Suggestion:** {execution_result['suggestion']}\n"
            if 'query' in execution_result:
                error_msg += f"**Query:** ```sql\n{execution_result['query']}\n```"
            return error_msg
        
        # Success case
        result_msg = f"✅ **SQL Execution Successful**\n"
        result_msg += f"**Query Type:** {execution_result.get('query_type', 'Unknown')}\n"
        
        if 'total_rows' in execution_result:
            result_msg += f"**Total Rows:** {execution_result['total_rows']}\n"
            result_msg += f"**Displayed Rows:** {execution_result['displayed_rows']}\n"
            
            if execution_result.get('truncated', False):
                result_msg += f"⚠️ *Results truncated to {self.max_rows} rows*\n"
            
            result_msg += "\n**Results:**\n"
            
            if execution_result['result']:
                # Format as a simple table
                result_msg += "```\n"
                for i, row in enumerate(execution_result['result']):
                    if isinstance(row, (list, tuple)):
                        result_msg += f"Row {i+1}: {' | '.join(str(col) for col in row)}\n"
                    else:
                        result_msg += f"Row {i+1}: {str(row)}\n"
                result_msg += "```\n"
            else:
                result_msg += "*No rows returned*\n"
        else:
            result_msg += f"**Result:** {execution_result.get('result', 'Success')}\n"
        
        return result_msg


def parse_sql_tool_call(llm_response: str) -> Tuple[Optional[str], str]:
    """
    Parse LLM response to extract SQL tool calls.
    
    Expected format: <sql_execute>SELECT * FROM table;</sql_execute>
    
    Args:
        llm_response: The full response from the LLM
        
    Returns:
        Tuple of (sql_query, remaining_response)
    """
    sql_pattern = r'<sql_execute>(.*?)</sql_execute>'
    match = re.search(sql_pattern, llm_response, re.DOTALL | re.IGNORECASE)
    
    if match:
        sql_query = match.group(1).strip()
        # Remove the SQL execute block from the response
        remaining_response = re.sub(sql_pattern, '', llm_response, flags=re.DOTALL | re.IGNORECASE).strip()
        return sql_query, remaining_response
    
    return None, llm_response


def process_llm_response_with_sql_tool(llm_response: str, sql_tool: SQLExecutionTool) -> str:
    """
    Process LLM response that may contain SQL tool calls.
    
    Args:
        llm_response: The response from the LLM
        sql_tool: The SQL execution tool instance
        
    Returns:
        The processed response with SQL execution results
    """
    sql_query, remaining_response = parse_sql_tool_call(llm_response)
    
    if sql_query:
        # Execute the SQL query
        execution_result = sql_tool.execute_sql(sql_query)
        formatted_result = sql_tool.format_result_for_llm(execution_result)
        
        # Combine the remaining response with the SQL execution result
        if remaining_response:
            return f"{remaining_response}\n\n{formatted_result}"
        else:
            return formatted_result
    
    return llm_response


# Example usage and testing
if __name__ == "__main__":
    # Test the SQL execution tool
    tool = SQLExecutionTool("test_db")
    
    # Test with a simple query
    test_query = "SELECT 1 as test_column;"
    result = tool.execute_sql(test_query)
    print("Test Result:")
    print(json.dumps(result, indent=2))
    print()
    print("Formatted for LLM:")
    print(tool.format_result_for_llm(result))
    
    # Test parsing
    test_response = """I need to check the data first.

<sql_execute>SELECT COUNT(*) FROM users;</sql_execute>

Based on the results, I can now provide a better answer."""
    
    sql_query, remaining = parse_sql_tool_call(test_response)
    print(f"\nParsed SQL: {sql_query}")
    print(f"Remaining response: {remaining}")