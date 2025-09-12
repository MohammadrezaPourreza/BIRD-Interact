#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
BIRD-Interact SQL Evaluator
独立的SQL评估脚本，提供详细的SQL正确性检查
"""
import os
import sys
import json
import argparse
import logging
import subprocess
from typing import Dict, Any, List, Optional, Tuple
from pathlib import Path

class SQLEvaluator:
    """SQL评估器类"""
    
    def __init__(self, 
                 eval_script_path: str = "/home/hailongli/BIRDInteract/BIRD-Interact/evaluation/src/eval_bird_interact_batch.py",
                 pg_password: str = "123123",
                 log_level: str = "INFO"):
        """
        初始化SQL评估器
        
        Args:
            eval_script_path: BIRD-Interact evaluation脚本路径
            pg_password: PostgreSQL密码
            log_level: 日志级别
        """
        self.eval_script_path = eval_script_path
        self.pg_password = pg_password
        self._setup_logging(log_level)
        
    def _setup_logging(self, log_level: str):
        """设置日志配置"""
        logging.basicConfig(
            level=getattr(logging, log_level.upper()),
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.StreamHandler(sys.stdout)
            ]
        )
        self.logger = logging.getLogger(__name__)
        
    def check_evaluation_environment(self) -> bool:
        """Check if evaluation environment is available"""
        # Check if evaluation script exists
        if not os.path.exists(self.eval_script_path):
            self.logger.error(f"Evaluation script not found: {self.eval_script_path}")
            return False
            
        # Check database dumps directory
        dumps_dir = "/home/hailongli/BIRDInteract/BIRD-Interact/evaluation/postgre_table_dumps"
        if not os.path.exists(dumps_dir):
            self.logger.error(f"Database dumps directory not found: {dumps_dir}")
            return False
            
        # Check PostgreSQL connection (simple check)
        try:
            result = subprocess.run(['pg_isready', '-h', 'localhost', '-p', '5432'], 
                                  capture_output=True, text=True, timeout=5)
            if result.returncode != 0:
                self.logger.warning("PostgreSQL may not be running. Evaluation might fail.")
        except Exception as e:
            self.logger.warning(f"Could not check PostgreSQL status: {e}")
            
        return True
    
    def _preprocess_jsonl_file(self, input_file):
        """Preprocess JSONL file, convert pred_sqls list to [split] separated string"""
        import tempfile
        import json
        
        # Create temporary file
        temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False)
        
        try:
            with open(input_file, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.strip():
                        data = json.loads(line)
                        
                        # Process pred_sqls field
                        if 'pred_sqls' in data and isinstance(data['pred_sqls'], list):
                            # Convert list to [split] separated string
                            data['pred_sqls'] = '[split]'.join(data['pred_sqls'])
                        
                        # Process sol_sql field
                        if 'sol_sql' in data and isinstance(data['sol_sql'], list):
                            # Convert list to [split] separated string
                            data['sol_sql'] = '[split]'.join(data['sol_sql'])
                        
                        # Write processed data
                        temp_file.write(json.dumps(data, ensure_ascii=False) + '\n')
            
            temp_file.close()
            self.logger.info(f"✅ Preprocessing completed, temp file: {temp_file.name}")
            return temp_file.name
            
        except Exception as e:
            self.logger.error(f"❌ Failed to preprocess JSONL file: {e}")
            temp_file.close()
            return input_file
        
    def run_evaluation(self, jsonl_file: str) -> Dict[str, Any]:
        """
        Run SQL evaluation
        
        Args:
            jsonl_file: Path to JSONL file containing prediction results
            
        Returns:
            Dictionary containing detailed evaluation results
        """
        if not os.path.exists(jsonl_file):
            self.logger.error(f"Input file not found: {jsonl_file}")
            return {}
            
        # Check environment
        if not self.check_evaluation_environment():
            self.logger.error("Evaluation environment check failed")
            return {}
            
        try:
            self.logger.info(f"🔍 Starting SQL evaluation: {jsonl_file}")
            
            # Preprocess JSONL file, convert pred_sqls list to [split] separated string
            processed_file = self._preprocess_jsonl_file(jsonl_file)
            
            # Run evaluation script
            result = subprocess.run([
                'python', self.eval_script_path,
                '--jsonl', processed_file,
                '--pg_password', self.pg_password
            ], capture_output=True, text=True, timeout=300)
            
            if result.returncode == 0:
                self.logger.info("✅ SQL evaluation completed")
                return self._parse_evaluation_results(processed_file)
            else:
                self.logger.error(f"Evaluation failed with return code {result.returncode}")
                self.logger.error(f"STDERR: {result.stderr}")
                return self._create_error_result("Evaluation script failed", result.stderr)
                
        except subprocess.TimeoutExpired:
            self.logger.error("Evaluation timeout (5 minutes)")
            return self._create_error_result("Timeout", "Evaluation took too long")
        except Exception as e:
            self.logger.error(f"Evaluation error: {e}")
            return self._create_error_result("Exception", str(e))
            
    def _parse_evaluation_results(self, jsonl_file: str) -> Dict[str, Any]:
        """Parse evaluation results"""
        output_file = jsonl_file.replace('.jsonl', '_output_with_status.jsonl')
        
        if not os.path.exists(output_file):
            self.logger.error(f"Evaluation output file not found: {output_file}")
            return self._create_error_result("Missing output", "Output file not generated")
            
        results = {
            'summary': {},
            'details': {},
            'errors': []
        }
        
        try:
            with open(output_file, 'r', encoding='utf-8') as f:
                for line_num, line in enumerate(f, 1):
                    if not line.strip():
                        continue
                        
                    try:
                        data = json.loads(line)
                        instance_id = data.get('instance_id', f'unknown_{line_num}')
                        
                        # Parse detailed results
                        detail = self._parse_single_result(data)
                        results['details'][instance_id] = detail
                        
                    except json.JSONDecodeError as e:
                        self.logger.warning(f"JSON decode error at line {line_num}: {e}")
                        results['errors'].append(f"Line {line_num}: JSON decode error")
                        
            # Calculate summary statistics
            results['summary'] = self._calculate_summary(results['details'])
            
        except Exception as e:
            self.logger.error(f"Error parsing evaluation results: {e}")
            results['errors'].append(f"Parse error: {e}")
            
        return results
        
    def _parse_single_result(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Parse single sample evaluation result"""
        return {
            'instance_id': data.get('instance_id', ''),
            'status': data.get('status', 'failed'),
            'generated_sql': data.get('pred_sqls', [''])[0] if data.get('pred_sqls') else '',
            'sol_sql': data.get('sol_sql', [''])[0] if data.get('sol_sql') else '',
            'generated_sql_execution_result': data.get('generated_sql_execution_result', ''),
            'sol_sql_execution_result': data.get('sol_sql_execution_result', ''),
            'error_msg': data.get('error_msg', ''),
            'execution_time': data.get('execution_time', 0),
            'is_correct': data.get('status') == 'success',
            'database': data.get('selected_database', ''),
            'query': data.get('query', ''),
            'conversation_turns': data.get('conversation_turns', 0)
        }
        
    def _calculate_summary(self, details: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        """Calculate summary statistics"""
        if not details:
            return {
                'total_samples': 0,
                'successful_generation': 0,
                'correct_sql': 0,
                'generation_success_rate': 0.0,
                'sql_correctness_rate': 0.0,
                'avg_conversation_turns': 0.0,
                'avg_execution_time': 0.0
            }
            
        total = len(details)
        successful_generation = sum(1 for d in details.values() if d.get('generated_sql', '').strip())
        correct_sql = sum(1 for d in details.values() if d.get('is_correct', False))
        avg_turns = sum(d.get('conversation_turns', 0) for d in details.values()) / total
        avg_exec_time = sum(d.get('execution_time', 0) for d in details.values()) / total
        
        return {
            'total_samples': total,
            'successful_generation': successful_generation,
            'correct_sql': correct_sql,
            'generation_success_rate': (successful_generation / total * 100) if total > 0 else 0.0,
            'sql_correctness_rate': (correct_sql / total * 100) if total > 0 else 0.0,
            'avg_conversation_turns': avg_turns,
            'avg_execution_time': avg_exec_time
        }
        
    def _create_error_result(self, error_type: str, error_msg: str) -> Dict[str, Any]:
        """Create error result"""
        return {
            'summary': {
                'total_samples': 0,
                'successful_generation': 0,
                'correct_sql': 0,
                'generation_success_rate': 0.0,
                'sql_correctness_rate': 0.0,
                'avg_conversation_turns': 0.0,
                'avg_execution_time': 0.0
            },
            'details': {},
            'errors': [f"{error_type}: {error_msg}"]
        }
        
    def print_detailed_results(self, results: Dict[str, Any]):
        """Print detailed evaluation results"""
        summary = results.get('summary', {})
        details = results.get('details', {})
        errors = results.get('errors', [])
        
        # Print error information
        if errors:
            print(f"\n⚠️  Evaluation Errors:")
            for error in errors:
                print(f"   - {error}")
                
        # Print summary statistics
        print(f"\n{'='*80}")
        print(f"BIRD-Interact SQL Evaluation Detailed Results")
        print(f"{'='*80}")
        print(f"Total Samples: {summary.get('total_samples', 0)}")
        print(f"Successful SQL Generation: {summary.get('successful_generation', 0)}")
        print(f"SQL Generation Success Rate: {summary.get('generation_success_rate', 0):.1f}%")
        print(f"SQL Correctness: {summary.get('correct_sql', 0)}/{summary.get('total_samples', 0)} ({summary.get('sql_correctness_rate', 0):.1f}%)")
        print(f"Average Conversation Turns: {summary.get('avg_conversation_turns', 0):.1f}")
        print(f"Average Execution Time: {summary.get('avg_execution_time', 0):.2f}s")
        print(f"{'='*80}")
        
        # Print detailed results
        for instance_id, detail in details.items():
            status_icon = "✅" if detail.get('is_correct', False) else "❌"
            gen_icon = "✅" if detail.get('generated_sql', '').strip() else "❌"
            turns = detail.get('conversation_turns', 0)
            database = detail.get('database', 'unknown')
            
            print(f"{gen_icon}{status_icon} {instance_id} - {database} - {turns} turns")
            
            # If there's error information, display it
            if detail.get('error_msg'):
                print(f"    Error: {detail['error_msg'][:100]}...")
                
        print(f"{'='*80}")
        print(f"Legend: First symbol=SQL Generation, Second symbol=SQL Correctness")
        print(f"        ✅=Success, ❌=Failed")
        
    def save_detailed_results(self, results: Dict[str, Any], output_file: str):
        """Save detailed evaluation results"""
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        self.logger.info(f"Detailed evaluation results saved to: {output_file}")

def main():
    """Main function"""
    parser = argparse.ArgumentParser(description='BIRD-Interact SQL Evaluator')
    parser.add_argument('--input', type=str, required=True, 
                       help='Input JSONL file path')
    parser.add_argument('--eval_script', type=str, 
                       default='/home/hailongli/BIRDInteract/BIRD-Interact/evaluation/src/eval_bird_interact_batch.py',
                       help='BIRD-Interact evaluation script path')
    parser.add_argument('--pg_password', type=str, default='123123',
                       help='PostgreSQL password')
    parser.add_argument('--output', type=str, 
                       help='Output detailed results file path (optional)')
    parser.add_argument('--log_level', type=str, choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'], 
                       default='INFO', help='Logging level')
    
    args = parser.parse_args()
    
    # Create evaluator
    evaluator = SQLEvaluator(
        eval_script_path=args.eval_script,
        pg_password=args.pg_password,
        log_level=args.log_level
    )
    
    # 运行evaluation
    results = evaluator.run_evaluation(args.input)
    
    # 打印结果
    evaluator.print_detailed_results(results)
    
    # 保存结果（如果指定了输出文件）
    if args.output:
        evaluator.save_detailed_results(results, args.output)

if __name__ == "__main__":
    main()
