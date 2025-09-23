#!/usr/bin/env python3
"""
Consistency-based BIRD-Interact Experiment Runner

This script implements a consistency-based approach to SQL generation:
1. Generate multiple SQL queries for the same question
2. Cluster them based on execution results  
3. Use confidence threshold to decide whether to ask clarification
4. For clarification, use representative queries from different clusters
5. For debug/follow-up, select from the largest cluster
"""

import os
import sys
import json
import logging
import subprocess
import time
import argparse
from pathlib import Path
from typing import List, Dict, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.append(str(project_root))

class ConsistencyBIRDInteractExperiment:
    """
    Manages consistency-based BIRD-Interact experiments with confidence estimation.
    """
    
    def __init__(self, 
                 model_name: str,
                 api_provider: str = "openai",
                 samples: int = 10,
                 confidence_threshold: float = 0.6,
                 patience: int = 3,
                 max_workers: int = 10,
                 output_dir: str = "./results/consistency",
                 experiment_name: Optional[str] = None):
        
        self.model_name = model_name
        self.api_provider = api_provider
        self.samples = samples
        self.confidence_threshold = confidence_threshold
        self.patience = patience
        self.max_workers = max_workers
        self.output_dir = Path(output_dir)
        self.experiment_name = experiment_name or f"{model_name}_consistency_{int(time.time())}"
        
        # Create experiment directory
        self.experiment_dir = self.output_dir / self.experiment_name
        self.experiment_dir.mkdir(parents=True, exist_ok=True)
        
        # Setup logging
        self.setup_logging()
        
        # File paths
        self.setup_file_paths()
        
        self.logger.info(f"Initialized consistency experiment: {self.experiment_name}")
        self.logger.info(f"Samples: {samples}, Confidence threshold: {confidence_threshold}")
    
    def setup_logging(self):
        """Setup logging for the experiment."""
        log_file = self.experiment_dir / "experiment.log"
        
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_file, encoding='utf-8'),
                logging.StreamHandler(sys.stdout)
            ]
        )
        
        self.logger = logging.getLogger(f"ConsistencyExperiment-{self.experiment_name}")
    
    def setup_file_paths(self):
        """Setup all the file paths needed for the experiment."""
        base_dir = Path(__file__).parent.parent
        
        # Input data paths
        self.data_dir = base_dir / "data" / "bird-interact-lite"
        self.schema_path = str(base_dir / "data" / "bird-interact-lite" / "[[DB_name]]" / "[[DB_name]].sql")
        self.external_kg_path = str(base_dir / "data" / "bird-interact-lite" / "[[DB_name]]" / "external_kg.jsonl")
        
        # System files
        self.system_file = self.experiment_dir / "system_consistency.jsonl"
        
        # Phase-specific files
        self.phase_files = {
            'amb': {
                'prompt': self.experiment_dir / "system_consistency_prompt.jsonl",
                'response': self.experiment_dir / "system_consistency_response.jsonl",
                'sql_results': self.experiment_dir / "sql_results_consistency.jsonl",
                'status': self.experiment_dir / "sql_results_consistency_output_with_status.jsonl"
            },
            'debug': {
                'prompt': self.experiment_dir / "system_consistency_debug_prompt.jsonl",
                'response': self.experiment_dir / "system_consistency_debug_response.jsonl", 
                'sql_results': self.experiment_dir / "sql_results_consistency_debug.jsonl",
                'status': self.experiment_dir / "sql_results_consistency_debug_output_with_status.jsonl"
            },
            'follow': {
                'prompt': self.experiment_dir / "system_consistency_fu_prompt.jsonl",
                'response': self.experiment_dir / "system_consistency_fu_response.jsonl",
                'sql_results': self.experiment_dir / "sql_results_consistency_fu.jsonl", 
                'status': self.experiment_dir / "sql_results_consistency_fu_output_with_status.jsonl"
            }
        }
    
    def load_initial_data(self) -> bool:
        """Load and prepare the initial dataset."""
        try:
            source_file = self.data_dir / "instances.jsonl"
            if not source_file.exists():
                self.logger.error(f"Source data file not found: {source_file}")
                return False
            
            # Copy initial data to system file
            import shutil
            shutil.copy2(source_file, self.system_file)
            
            self.logger.info(f"Loaded initial data from {source_file}")
            return True
            
        except Exception as e:
            self.logger.error(f"Error loading initial data: {e}")
            return False
    
    def generate_prompts(self, phase: str, turn_num: int = 1, user_resp_file: Optional[str] = None) -> bool:
        """Generate prompts for a specific phase using consistency approach."""
        try:
            self.logger.info(f"Generating {phase} prompts (turn {turn_num})...")
            
            # Determine input file based on phase and turn
            if phase == 'amb' and turn_num == 1:
                input_file = self.system_file
            else:
                # For later turns or other phases, use appropriate previous file
                input_file = self.system_file  # Simplify for now
            
            # Prepare command
            cmd = [
                sys.executable, 
                str(Path(__file__).parent / "infer_api_system_consistency.py"),
                "--prompt_path", str(input_file),
                "--result_path", str(self.phase_files[phase]['prompt']),
                "--DB_schema_path", self.schema_path,
                "--external_kg_path", self.external_kg_path,
                "--phase", phase,
                "--turn_num", str(turn_num),
                "--samples", str(self.samples),
                "--confidence_threshold", str(self.confidence_threshold)
            ]
            
            if user_resp_file:
                cmd.extend(["--user_resp_path", str(user_resp_file)])
            
            # Execute command
            result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8')
            
            if result.returncode != 0:
                self.logger.error(f"Error generating {phase} prompts: {result.stderr}")
                return False
            
            self.logger.info(f"Successfully generated {phase} prompts")
            return True
            
        except Exception as e:
            self.logger.error(f"Error in generate_prompts: {e}")
            return False
    
    def call_llm_api_multiple(self, phase: str, turn_num: int = 1) -> bool:
        """Call LLM API multiple times for consistency sampling."""
        try:
            self.logger.info(f"Calling LLM API for {phase} (turn {turn_num}, {self.samples} samples)...")
            
            prompt_file = self.phase_files[phase]['prompt']
            if not prompt_file.exists():
                self.logger.error(f"Prompt file not found: {prompt_file}")
                return False
            
            # Load prompts
            prompts = []
            with open(prompt_file, 'r', encoding='utf-8') as f:
                for line in f:
                    data = json.loads(line)
                    if 'prompt' in data:
                        prompts.append(data)
            
            if not prompts:
                self.logger.error("No prompts found in file")
                return False
            
            # Prepare for multiple API calls per prompt
            all_responses = []
            
            def call_api_for_sample(prompt_data, sample_idx):
                """Call API for a single sample."""
                # Create a copy with sample-specific metadata
                sample_data = prompt_data.copy()
                sample_data['sample_idx'] = sample_idx
                sample_data['total_samples'] = self.samples
                
                # Call the regular API function
                cmd = [
                    sys.executable,
                    str(Path(__file__).parent / "call_api.py"),
                    "--prompt_file", "/dev/stdin",
                    "--result_path", "/dev/stdout",
                    "--model", self.model_name,
                    "--api_provider", self.api_provider,
                    "--max_workers", "1"  # Single worker for individual calls
                ]
                
                try:
                    # Prepare input
                    input_line = json.dumps(sample_data, ensure_ascii=False) + "\n"
                    
                    # Execute
                    result = subprocess.run(cmd, input=input_line, capture_output=True, 
                                          text=True, encoding='utf-8')
                    
                    if result.returncode == 0:
                        # Parse response
                        response_line = result.stdout.strip()
                        if response_line:
                            response_data = json.loads(response_line)
                            response_data['sample_idx'] = sample_idx
                            return response_data
                    
                except Exception as e:
                    self.logger.warning(f"Error in API call for sample {sample_idx}: {e}")
                
                return None
            
            # Process each prompt
            final_responses = []
            
            for prompt_idx, prompt_data in enumerate(prompts):
                self.logger.info(f"Processing prompt {prompt_idx + 1}/{len(prompts)} with {self.samples} samples...")
                
                # Generate multiple samples for this prompt
                sample_responses = []
                
                # Use ThreadPoolExecutor for parallel API calls
                with ThreadPoolExecutor(max_workers=min(self.max_workers, self.samples)) as executor:
                    # Submit all sample tasks
                    future_to_sample = {
                        executor.submit(call_api_for_sample, prompt_data, sample_idx): sample_idx 
                        for sample_idx in range(self.samples)
                    }
                    
                    # Collect results
                    completed_samples = 0
                    for future in as_completed(future_to_sample):
                        sample_idx = future_to_sample[future]
                        try:
                            response_data = future.result()
                            if response_data:
                                sample_responses.append(response_data['prediction'])
                                completed_samples += 1
                                
                                if completed_samples % 2 == 0:  # Progress update every 2 samples
                                    self.logger.info(f"  Completed {completed_samples}/{self.samples} samples")
                                    
                        except Exception as e:
                            self.logger.warning(f"Error processing sample {sample_idx}: {e}")
                
                if len(sample_responses) < self.samples // 2:  # Less than half succeeded
                    self.logger.error(f"Too few successful samples for prompt {prompt_idx}: {len(sample_responses)}")
                    continue
                
                # Process consistency for this prompt
                from infer_api_system_consistency import process_consistency_responses
                
                processed_data = prompt_data.copy()
                processed_data = process_consistency_responses(processed_data, sample_responses, phase)
                
                # Add response information
                if 'final_sql' in processed_data:
                    processed_data['prediction'] = processed_data['final_sql']
                elif processed_data.get('consistency_result') == 'need_clarification':
                    # Need to generate clarification question
                    processed_data['prediction'] = self.generate_clarification_question(processed_data)
                else:
                    # Fallback
                    if sample_responses:
                        processed_data['prediction'] = sample_responses[0]
                
                final_responses.append(processed_data)
            
            # Save responses
            response_file = self.phase_files[phase]['response']
            with open(response_file, 'w', encoding='utf-8') as f:
                for response in final_responses:
                    json_line = json.dumps(response, ensure_ascii=False)
                    f.write(json_line + "\n")
            
            self.logger.info(f"Successfully completed {phase} API calls with consistency sampling")
            return True
            
        except Exception as e:
            self.logger.error(f"Error in call_llm_api_multiple: {e}")
            return False
    
    def generate_clarification_question(self, data: Dict) -> str:
        """Generate a clarification question using the disambiguator prompt."""
        try:
            from bird_interact_conv.prompts.prompts import system_consistency_disambiguator
            
            # Format the disambiguator prompt
            prompt = system_consistency_disambiguator
            prompt = prompt.replace('[[DB_schema]]', data.get('DB_schema', ''))
            prompt = prompt.replace('[[external_kg]]', data.get('external_kg', ''))
            prompt = prompt.replace('[[user_query]]', data.get('original_question', ''))
            
            # Format the SQL queries
            representatives = data.get('consistency_representatives', [])
            if representatives:
                formatted_queries = []
                for i, sql in enumerate(representatives, 1):
                    formatted_queries.append(f"Interpretation {i}:\n```postgresql\n{sql}\n```")
                sql_queries_text = "\n\n".join(formatted_queries)
            else:
                sql_queries_text = "No representative queries available"
            
            prompt = prompt.replace('[[sql_queries]]', sql_queries_text)
            
            # Call API to generate clarification question
            cmd = [
                sys.executable,
                str(Path(__file__).parent / "call_api.py"),
                "--prompt_file", "/dev/stdin",
                "--result_path", "/dev/stdout",
                "--model", self.model_name,
                "--api_provider", self.api_provider,
                "--max_workers", "1"
            ]
            
            # Prepare input data
            temp_data = {"prompt": prompt, "instance_id": data.get("instance_id", "unknown")}
            input_line = json.dumps(temp_data, ensure_ascii=False) + "\n"
            
            # Execute
            result = subprocess.run(cmd, input=input_line, capture_output=True, 
                                  text=True, encoding='utf-8')
            
            if result.returncode == 0:
                response_line = result.stdout.strip()
                if response_line:
                    response_data = json.loads(response_line)
                    return response_data.get('prediction', '<s>Could not generate clarification question</s>')
            
            return '<s>Error generating clarification question</s>'
            
        except Exception as e:
            self.logger.error(f"Error generating clarification question: {e}")
            return '<s>Error generating clarification question</s>'
    
    def extract_sql_results(self, phase: str) -> bool:
        """Extract SQL results from API responses."""
        try:
            self.logger.info(f"Extracting SQL results for {phase}...")
            
            response_file = self.phase_files[phase]['response']
            sql_results_file = self.phase_files[phase]['sql_results']
            
            cmd = [
                sys.executable,
                str(Path(__file__).parent / "wrap_up_sql.py"),
                "--input_path", str(response_file),
                "--output_path", str(sql_results_file)
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8')
            
            if result.returncode != 0:
                self.logger.error(f"Error extracting SQL results: {result.stderr}")
                return False
            
            self.logger.info(f"Successfully extracted SQL results for {phase}")
            return True
            
        except Exception as e:
            self.logger.error(f"Error in extract_sql_results: {e}")
            return False
    
    def evaluate_sql(self, phase: str) -> bool:
        """Evaluate SQL queries against the database."""
        try:
            self.logger.info(f"Evaluating SQL for {phase}...")
            
            sql_results_file = self.phase_files[phase]['sql_results']
            status_file = self.phase_files[phase]['status']
            
            # Use the evaluation system (assuming it exists)
            evaluation_dir = Path(__file__).parent.parent.parent / "evaluation"
            
            if not evaluation_dir.exists():
                self.logger.warning("Evaluation system not found, skipping SQL evaluation")
                return True
            
            cmd = [
                "docker", "compose", "-f", str(evaluation_dir / "docker-compose.yml"),
                "run", "--rm", "so_eval",
                "python", "src/evaluate.py",
                "--input", f"/app/results/{sql_results_file.name}",
                "--output", f"/app/results/{status_file.name}"
            ]
            
            # Copy files to evaluation directory for Docker access
            eval_results_dir = evaluation_dir / "results"
            eval_results_dir.mkdir(exist_ok=True)
            
            import shutil
            shutil.copy2(sql_results_file, eval_results_dir / sql_results_file.name)
            
            result = subprocess.run(cmd, cwd=evaluation_dir, capture_output=True, text=True)
            
            if result.returncode == 0:
                # Copy results back
                if (eval_results_dir / status_file.name).exists():
                    shutil.copy2(eval_results_dir / status_file.name, status_file)
                    self.logger.info(f"Successfully evaluated SQL for {phase}")
                    return True
            
            self.logger.error(f"Error in SQL evaluation: {result.stderr}")
            return False
            
        except Exception as e:
            self.logger.error(f"Error in evaluate_sql: {e}")
            return False
    
    def run_experiment(self, phases: List[str] = None) -> bool:
        """Run the complete consistency-based experiment."""
        if phases is None:
            phases = ['amb', 'debug', 'follow']
        
        self.logger.info(f"Starting consistency experiment: {self.experiment_name}")
        self.logger.info(f"Phases to run: {phases}")
        
        try:
            # Step 1: Load initial data
            if not self.load_initial_data():
                return False
            
            # Step 2: Run each phase
            for phase in phases:
                self.logger.info(f"Starting {phase} phase...")
                
                # Generate prompts
                if not self.generate_prompts(phase):
                    self.logger.error(f"Failed to generate {phase} prompts")
                    continue
                
                # Call API with multiple samples
                if not self.call_llm_api_multiple(phase):
                    self.logger.error(f"Failed to call API for {phase}")
                    continue
                
                # Extract SQL results
                if not self.extract_sql_results(phase):
                    self.logger.error(f"Failed to extract SQL results for {phase}")
                    continue
                
                # Evaluate SQL
                if not self.evaluate_sql(phase):
                    self.logger.warning(f"SQL evaluation failed for {phase}, continuing anyway")
                
                self.logger.info(f"Completed {phase} phase")
            
            self.logger.info(f"Experiment {self.experiment_name} completed successfully")
            
            # Generate summary
            self.generate_experiment_summary()
            
            return True
            
        except Exception as e:
            self.logger.error(f"Error in run_experiment: {e}")
            return False
    
    def generate_experiment_summary(self):
        """Generate a summary of the experiment results."""
        try:
            summary = {
                'experiment_name': self.experiment_name,
                'model_name': self.model_name,
                'api_provider': self.api_provider,
                'samples': self.samples,
                'confidence_threshold': self.confidence_threshold,
                'patience': self.patience,
                'timestamp': time.time(),
                'files': {}
            }
            
            # List output files
            for phase, files in self.phase_files.items():
                summary['files'][phase] = {}
                for file_type, file_path in files.items():
                    summary['files'][phase][file_type] = {
                        'path': str(file_path),
                        'exists': file_path.exists(),
                        'size': file_path.stat().st_size if file_path.exists() else 0
                    }
            
            # Save summary
            summary_file = self.experiment_dir / "experiment_summary.json"
            with open(summary_file, 'w', encoding='utf-8') as f:
                json.dump(summary, f, indent=2, ensure_ascii=False)
            
            self.logger.info(f"Experiment summary saved to {summary_file}")
            
        except Exception as e:
            self.logger.error(f"Error generating experiment summary: {e}")

def main():
    """Main entry point for consistency-based experiments."""
    parser = argparse.ArgumentParser(description='Run consistency-based BIRD-Interact experiments')
    
    # Model configuration
    parser.add_argument('--model', required=True, help='Model name (e.g., gpt-4, claude-3-sonnet)')
    parser.add_argument('--api_provider', default='openai', 
                       choices=['openai', 'anthropic', 'google'],
                       help='API provider to use')
    
    # Consistency parameters
    parser.add_argument('--samples', type=int, default=10,
                       help='Number of SQL samples to generate for consistency check')
    parser.add_argument('--confidence_threshold', type=float, default=0.6,
                       help='Confidence threshold for accepting SQL without clarification')
    
    # Experiment configuration
    parser.add_argument('--patience', type=int, default=3,
                       help='Maximum number of clarification turns')
    parser.add_argument('--max_workers', type=int, default=10,
                       help='Maximum number of parallel API workers')
    parser.add_argument('--output_dir', default='./results/consistency',
                       help='Output directory for experiment results')
    parser.add_argument('--experiment_name', 
                       help='Custom experiment name (auto-generated if not provided)')
    
    # Phase selection
    parser.add_argument('--phases', nargs='+', default=['amb', 'debug', 'follow'],
                       choices=['amb', 'debug', 'follow'],
                       help='Phases to run')
    
    args = parser.parse_args()
    
    # Create and run experiment
    experiment = ConsistencyBIRDInteractExperiment(
        model_name=args.model,
        api_provider=args.api_provider,
        samples=args.samples,
        confidence_threshold=args.confidence_threshold,
        patience=args.patience,
        max_workers=args.max_workers,
        output_dir=args.output_dir,
        experiment_name=args.experiment_name
    )
    
    # Run the experiment
    success = experiment.run_experiment(args.phases)
    
    if success:
        print(f"Experiment completed successfully: {experiment.experiment_name}")
        print(f"Results saved to: {experiment.experiment_dir}")
    else:
        print(f"Experiment failed: {experiment.experiment_name}")
        sys.exit(1)

if __name__ == "__main__":
    main()
