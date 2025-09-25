#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Enhanced Final Score Calculation for BIRD-Interact with SQL Execution Tool

This script calculates comprehensive scores for the enhanced BIRD-Interact evaluation,
including metrics for SQL execution tool usage and efficiency.

Author: Enhanced BIRD-Interact Team
"""

import os
import sys
import json
import argparse
from pathlib import Path
from typing import Dict, List, Optional, Tuple


class EnhancedScoreCalculator:
    """Calculate comprehensive scores for enhanced BIRD-Interact evaluation."""
    
    def __init__(self, result_dir: str, patience: int, max_sql_executions: int):
        self.result_dir = Path(result_dir)
        self.patience = patience
        self.max_sql_executions = max_sql_executions
        self.scores = {}
        
    def load_evaluation_results(self, filename: str) -> Dict:
        """Load evaluation results from a JSONL file."""
        results = {}
        filepath = self.result_dir / filename
        
        if not filepath.exists():
            print(f"Warning: {filepath} not found")
            return {}
            
        with open(filepath, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    instance_id = data.get("instance_id", "unknown")
                    results[instance_id] = data
                except json.JSONDecodeError:
                    continue
                    
        return results
    
    def calculate_traditional_scores(self) -> Dict:
        """Calculate traditional BIRD-Interact scores."""
        # Phase 1 scores
        phase1_first = self.load_evaluation_results("sql_results_output_with_status.jsonl")
        phase1_debug = self.load_evaluation_results("sql_results_debug_output_with_status.jsonl")
        
        # Phase 2 scores  
        phase2_first = self.load_evaluation_results("sql_results_fu_output_with_status.jsonl")
        phase2_debug = self.load_evaluation_results("sql_results_fu_debug_output_with_status.jsonl")
        
        total_instances = len(set(
            list(phase1_first.keys()) + list(phase1_debug.keys()) + 
            list(phase2_first.keys()) + list(phase2_debug.keys())
        ))
        
        if total_instances == 0:
            return {"error": "No evaluation data found"}
        
        # Calculate rewards
        phase1_first_successes = sum(1 for data in phase1_first.values() if data.get("status") == "success")
        phase1_debug_successes = sum(1 for data in phase1_debug.values() if data.get("status") == "success")
        phase2_first_successes = sum(1 for data in phase2_first.values() if data.get("status") == "success")
        phase2_debug_successes = sum(1 for data in phase2_debug.values() if data.get("status") == "success")
        
        # Traditional scoring weights
        total_reward = (
            phase1_first_successes * 0.7 +
            (phase1_debug_successes - phase1_first_successes) * 0.5 +
            phase2_first_successes * 0.3 +
            (phase2_debug_successes - phase2_first_successes) * 0.2
        )
        
        normalized_reward = total_reward / total_instances if total_instances > 0 else 0
        
        return {
            "total_instances": total_instances,
            "phase1_first_success": phase1_first_successes,
            "phase1_debug_success": phase1_debug_successes,
            "phase2_first_success": phase2_first_successes, 
            "phase2_debug_success": phase2_debug_successes,
            "total_reward": total_reward,
            "normalized_reward": normalized_reward
        }
    
    def analyze_sql_execution_usage(self) -> Dict:
        """Analyze SQL execution tool usage patterns."""
        system_interactions = self.load_evaluation_results("system_interaction.jsonl")
        
        sql_usage_stats = {
            "instances_with_sql": 0,
            "total_sql_executions": 0,
            "avg_sql_per_instance": 0,
            "sql_efficiency_score": 0,
            "successful_sql_rate": 0,
            "sql_error_categories": {}
        }
        
        instances_with_sql = []
        total_sql_count = 0
        successful_sql_count = 0
        
        for instance_id, data in system_interactions.items():
            instance_sql_count = 0
            instance_successful_sql = 0
            
            # Count SQL executions in conversation history
            if "conversation_state" in data:
                conv_state = data["conversation_state"]
                if isinstance(conv_state, dict):
                    sql_history = conv_state.get("sql_execution_history", [])
                    instance_sql_count = len(sql_history)
                    
                    for sql_exec in sql_history:
                        total_sql_count += 1
                        if sql_exec.get("result", {}).get("success", False):
                            successful_sql_count += 1
                            instance_successful_sql += 1
            
            if instance_sql_count > 0:
                sql_usage_stats["instances_with_sql"] += 1
                instances_with_sql.append(instance_sql_count)
        
        sql_usage_stats["total_sql_executions"] = total_sql_count
        sql_usage_stats["avg_sql_per_instance"] = (
            sum(instances_with_sql) / len(instances_with_sql) if instances_with_sql else 0
        )
        sql_usage_stats["successful_sql_rate"] = (
            successful_sql_count / total_sql_count if total_sql_count > 0 else 0
        )
        
        # SQL efficiency: successful SQL / budget usage
        avg_budget_usage = total_sql_count / len(system_interactions) if system_interactions else 0
        budget_efficiency = avg_budget_usage / self.max_sql_executions if self.max_sql_executions > 0 else 0
        sql_usage_stats["sql_efficiency_score"] = min(1.0, budget_efficiency * sql_usage_stats["successful_sql_rate"])
        
        return sql_usage_stats
    
    def calculate_enhanced_metrics(self) -> Dict:
        """Calculate enhanced metrics specific to SQL execution tool."""
        traditional = self.calculate_traditional_scores()
        sql_usage = self.analyze_sql_execution_usage()
        
        # Enhanced scoring that considers SQL tool effectiveness
        sql_boost_factor = 1.0 + (sql_usage["sql_efficiency_score"] * 0.1)  # Up to 10% boost
        enhanced_reward = traditional.get("normalized_reward", 0) * sql_boost_factor
        
        return {
            "enhanced_normalized_reward": enhanced_reward,
            "sql_boost_factor": sql_boost_factor,
            "sql_tool_effectiveness": sql_usage["sql_efficiency_score"],
            **sql_usage
        }
    
    def generate_comprehensive_report(self) -> Dict:
        """Generate a comprehensive evaluation report."""
        traditional_scores = self.calculate_traditional_scores()
        enhanced_metrics = self.calculate_enhanced_metrics()
        
        report = {
            "evaluation_config": {
                "patience_budget": self.patience,
                "sql_execution_budget": self.max_sql_executions,
                "result_directory": str(self.result_dir)
            },
            "traditional_scores": traditional_scores,
            "enhanced_metrics": enhanced_metrics,
            "summary": {
                "traditional_score": traditional_scores.get("normalized_reward", 0),
                "enhanced_score": enhanced_metrics.get("enhanced_normalized_reward", 0),
                "improvement": enhanced_metrics.get("enhanced_normalized_reward", 0) - traditional_scores.get("normalized_reward", 0),
                "sql_adoption_rate": enhanced_metrics.get("instances_with_sql", 0) / traditional_scores.get("total_instances", 1),
                "avg_sql_per_instance": enhanced_metrics.get("avg_sql_per_instance", 0),
                "sql_success_rate": enhanced_metrics.get("successful_sql_rate", 0)
            }
        }
        
        return report
    
    def save_report(self, report: Dict, filename: str = "enhanced_evaluation_report.json"):
        """Save the comprehensive report to a JSON file."""
        output_path = self.result_dir / filename
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        return output_path


def print_summary_table(report: Dict):
    """Print a formatted summary table."""
    print("\n" + "="*80)
    print("🏆 ENHANCED BIRD-INTERACT EVALUATION REPORT")
    print("="*80)
    
    config = report["evaluation_config"]
    traditional = report["traditional_scores"]
    enhanced = report["enhanced_metrics"]
    summary = report["summary"]
    
    print(f"📊 Configuration:")
    print(f"   Clarification Budget: {config['patience_budget']} turns")
    print(f"   SQL Execution Budget: {config['sql_execution_budget']} queries")
    print(f"   Total Instances: {traditional.get('total_instances', 0)}")
    
    print(f"\n🎯 Performance Scores:")
    print(f"   Traditional Score: {traditional.get('normalized_reward', 0):.4f}")
    print(f"   Enhanced Score:    {enhanced.get('enhanced_normalized_reward', 0):.4f}")
    print(f"   Improvement:       {summary.get('improvement', 0):+.4f}")
    
    print(f"\n🔧 SQL Tool Usage:")
    print(f"   Adoption Rate:     {summary.get('sql_adoption_rate', 0):.2%}")
    print(f"   Avg SQL/Instance:  {summary.get('avg_sql_per_instance', 0):.2f}")
    print(f"   SQL Success Rate:  {summary.get('sql_success_rate', 0):.2%}")
    print(f"   Tool Effectiveness: {enhanced.get('sql_tool_effectiveness', 0):.4f}")
    
    print(f"\n📈 Phase Breakdown:")
    print(f"   Phase 1 First Try: {traditional.get('phase1_first_success', 0)}/{traditional.get('total_instances', 0)}")
    print(f"   Phase 1 w/ Debug:  {traditional.get('phase1_debug_success', 0)}/{traditional.get('total_instances', 0)}")  
    print(f"   Phase 2 First Try: {traditional.get('phase2_first_success', 0)}/{traditional.get('total_instances', 0)}")
    print(f"   Phase 2 w/ Debug:  {traditional.get('phase2_debug_success', 0)}/{traditional.get('total_instances', 0)}")
    
    print("\n" + "="*80)


def main():
    parser = argparse.ArgumentParser(description='Calculate enhanced BIRD-Interact scores')
    parser.add_argument('--result_dir', type=str, required=True, help='Results directory path')
    parser.add_argument('--patience', type=int, default=3, help='Clarification question budget')
    parser.add_argument('--sql_executions', type=int, default=5, help='SQL execution budget')
    parser.add_argument('--output_file', type=str, help='Output JSON report file name')
    parser.add_argument('--quiet', action='store_true', help='Suppress detailed output')
    
    args = parser.parse_args()
    
    calculator = EnhancedScoreCalculator(args.result_dir, args.patience, args.sql_executions)
    report = calculator.generate_comprehensive_report()
    
    # Save report
    output_filename = args.output_file or "enhanced_evaluation_report.json"
    output_path = calculator.save_report(report, output_filename)
    
    if not args.quiet:
        print_summary_table(report)
        print(f"\n💾 Full report saved to: {output_path}")
    
    # Return exit code based on performance
    enhanced_score = report["summary"]["enhanced_score"]
    if enhanced_score >= 0.8:
        sys.exit(0)  # Excellent performance
    elif enhanced_score >= 0.6:
        sys.exit(1)  # Good performance  
    elif enhanced_score >= 0.4:
        sys.exit(2)  # Average performance
    else:
        sys.exit(3)  # Needs improvement


if __name__ == "__main__":
    main()