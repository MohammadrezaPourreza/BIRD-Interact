#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
BIRD-Interact Experiment Runner

A unified experiment management system for running conversational text-to-SQL experiments.
This script orchestrates the entire pipeline including:
- Multi-turn ambiguity resolution
- User simulation (two-stage)
- SQL generation and debugging
- Follow-up question handling
- Comprehensive evaluation

Author: BIRD-Interact Team
"""

import os
import sys
import json
import argparse
import logging
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple


def setup_logging(log_dir: str, log_level: str = "INFO") -> logging.Logger:
    """Setup comprehensive logging with both file and console output."""
    
    # Create log directory
    Path(log_dir).mkdir(parents=True, exist_ok=True)
    
    # Create logger
    logger = logging.getLogger("bird_interact_experiment")
    logger.setLevel(getattr(logging, log_level.upper()))
    
    # Remove existing handlers to avoid duplication
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    
    # File handler
    log_file = os.path.join(log_dir, f"experiment_{int(time.time())}.log")
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(getattr(logging, log_level.upper()))
    
    # Formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)
    
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    logger.info(f"Logging initialized. Log file: {log_file}")
    return logger


def run_command(cmd: List[str], description: str, logger: logging.Logger, show_progress: bool = False) -> bool:
    """Execute a command with proper logging and error handling."""
    
    logger.info(f"Starting: {description}")
    logger.debug(f"Command: {' '.join(cmd)}")
    
    try:
        if show_progress:
            # For API calls, show real-time output with robust encoding handling
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                universal_newlines=True,
                encoding='utf-8',
                errors='replace'  # Replace invalid characters instead of failing
            )
            
            # Read output in real-time with error handling
            while True:
                try:
                    output = process.stdout.readline()
                    if output == '' and process.poll() is not None:
                        break
                    if output:
                        # Log API responses and progress
                        output_line = output.strip()
                        if output_line:
                            # Check if it looks like an LLM response
                            if any(keyword in output_line.lower() for keyword in ['response:', 'llm response', 'api response', 'generated:', 'completion:']):
                                # For LLM responses, don't truncate - show full response
                                logger.info(f"{output_line}")
                            elif 'processing' in output_line.lower() or 'turn' in output_line.lower():
                                logger.info(f"📊 Progress: {output_line}")
                            else:
                                logger.debug(f"Output: {output_line}")
                except UnicodeDecodeError as ude:
                    logger.warning(f"⚠️ Unicode decode error in output stream: {str(ude)}")
                    continue
                except Exception as e:
                    logger.warning(f"⚠️ Error reading output stream: {str(e)}")
                    continue
            
            # Get any remaining stderr with encoding handling
            try:
                stderr = process.stderr.read()
                if stderr:
                    logger.debug(f"STDERR: {stderr}")
            except UnicodeDecodeError:
                logger.warning("⚠️ Could not decode stderr due to encoding issues")
            
            return_code = process.poll()
            if return_code != 0:
                raise subprocess.CalledProcessError(return_code, cmd, stderr=stderr if 'stderr' in locals() else "encoding error")
                
        else:
            # For non-API calls, use the original method with encoding handling
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True,
                encoding='utf-8',
                errors='replace'  # Replace invalid characters instead of failing
            )
            
            if result.stdout:
                logger.debug(f"STDOUT: {result.stdout}")
        
        logger.info(f"✅ Completed: {description}")
        return True
        
    except subprocess.CalledProcessError as e:
        logger.error(f"❌ Failed: {description}")
        logger.error(f"Return code: {e.returncode}")
        if hasattr(e, 'stderr') and e.stderr:
            logger.error(f"STDERR: {e.stderr}")
        if hasattr(e, 'stdout') and e.stdout:
            logger.error(f"STDOUT: {e.stdout}")
        return False
    except UnicodeDecodeError as ude:
        logger.error(f"❌ UTF-8 decoding error in {description}: {str(ude)}")
        logger.error("💡 This may be due to non-UTF-8 characters in API response. Retrying with error handling...")
        return False
    except Exception as e:
        logger.error(f"❌ Unexpected error in {description}: {str(e)}")
        return False


def check_file_exists_and_not_empty(file_path: str) -> bool:
    """Check if file exists and is not empty."""
    return os.path.exists(file_path) and os.path.getsize(file_path) > 0


def get_max_turn_from_jsonl(jsonl_file: str, logger: logging.Logger) -> int:
    """Extract the maximum turn number from a JSONL file."""
    
    max_turn = 0
    try:
        with open(jsonl_file, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    data = json.loads(line)
                    if 'max_turn' in data:
                        max_turn = max(max_turn, data['max_turn'])
        
        logger.info(f"Maximum turn found: {max_turn}")
        return max_turn
        
    except Exception as e:
        logger.error(f"Error reading max_turn from {jsonl_file}: {str(e)}")
        return 3  # Default fallback


class BIRDInteractExperiment:
    """Main experiment orchestration class."""
    
    def __init__(self, config: Dict, logger: logging.Logger):
        self.config = config
        self.logger = logger
        self.project_root = config['project_root']
        self.patience = config['patience']
        self.system_model = config['system_model_name']
        self.user_model = config['US_model_name']
        
        # Generate timestamp for unique experiment identification
        if config.get('experiment_name'):
            experiment_suffix = config['experiment_name']
        else:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            experiment_suffix = timestamp
        
        # Setup paths with datetime stamp
        self.result_dir = os.path.join(
            self.project_root,
            "bird_interact_conv/results",
            f"patience_{self.patience}",
            f"{self.system_model}_{experiment_suffix}"
        )
        
        self.data_dir = os.path.join(self.project_root, "bird_interact_conv/data/bird-interact-lite")
        self.code_dir = os.path.join(self.project_root, "bird_interact_conv/code")
        self.eval_dir = os.path.join(self.project_root, "evaluation/src")
        
        # Create result directory
        Path(self.result_dir).mkdir(parents=True, exist_ok=True)
        
        self.logger.info(f"Experiment initialized:")
        self.logger.info(f"  - Result directory: {self.result_dir}")
        self.logger.info(f"  - System model: {self.system_model}")
        self.logger.info(f"  - User model: {self.user_model}")
        self.logger.info(f"  - Patience: {self.patience}")
        self.logger.info(f"  - Experiment suffix: {experiment_suffix}")
    
    def get_file_path(self, file_type: str, suffix: str = "") -> str:
        """Generate standardized file paths."""
        base_name = f"{file_type}_interaction{suffix}.jsonl"
        return os.path.join(self.result_dir, base_name)
    
    def run_system_interaction(self, turn_num: int, phase: str = "amb") -> bool:
        """Run system interaction (AI asking questions)."""
        
        # Determine data path
        if turn_num == 1 or phase != "amb":
            if check_file_exists_and_not_empty(self.get_file_path("system")):
                data_path = self.get_file_path("system")
            else:
                data_path = os.path.join(self.data_dir, "bird_interact_data.jsonl")
        else:
            data_path = self.get_file_path("system")
        
        # Determine user response path
        if phase == "amb" and turn_num > 1:
            user_resp_path = self.get_file_path("user_2")
        elif phase == "debug":
            user_resp_path = self.get_file_path("sql_results", "_output_with_status")
        elif phase == "follow":
            user_resp_path = self.get_file_path("sql_results", "_debug_output_with_status")
        else:
            user_resp_path = os.path.join(self.data_dir, "bird_interact_data.jsonl")
        
        result_path_prompt = self.get_file_path("system", "_prompt")
        result_path_response = self.get_file_path("system", "_response")
        result_path_final = self.get_file_path("system")
        
        # Step 1: Generate prompts
        cmd = [
            "python", os.path.join(self.code_dir, "infer_api_system.py"),
            "--prompt_path", data_path,
            "--result_path", result_path_prompt,
            "--user_resp_path", user_resp_path,
            "--DB_schema_path", os.path.join(self.data_dir, "[[DB_name]]/[[DB_name]]_schema.txt"),
            "--external_kg_path", os.path.join(self.data_dir, "[[DB_name]]/[[DB_name]]_kb.jsonl"),
            "--patience", str(self.patience),
            "--turn_num", str(turn_num),
            "--phase", phase
        ]
        
        if not run_command(cmd, f"System prompt generation (turn {turn_num}, phase {phase})", self.logger):
            return False
        
        # Check if prompts were generated
        if not check_file_exists_and_not_empty(result_path_prompt):
            self.logger.warning(f"No prompts generated for system turn {turn_num} phase {phase}")
            return True  # Not an error, just no work to do
        
        # Step 2: Call API with retry mechanism for encoding issues
        max_retries = 3
        for retry in range(max_retries):
            try:
                cmd = [
                    "python", os.path.join(self.code_dir, "call_api.py"),
                    "--model_name", self.system_model,
                    "--prompt_path", result_path_prompt,
                    "--output_path", result_path_response
                ]
                
                if run_command(cmd, f"System API call (turn {turn_num}, phase {phase}) - Attempt {retry + 1}", self.logger, show_progress=True):
                    break  # Success, exit retry loop
                elif retry < max_retries - 1:
                    self.logger.warning(f"⚠️ System API call failed, retrying... ({retry + 1}/{max_retries})")
                    import time
                    time.sleep(2)  # Wait before retry
                else:
                    self.logger.error(f"❌ System API call failed after {max_retries} attempts")
                    return False
                    
            except Exception as e:
                if "utf-8" in str(e).lower() or "encoding" in str(e).lower():
                    self.logger.warning(f"⚠️ System encoding error detected, attempt {retry + 1}/{max_retries}: {str(e)}")
                    if retry < max_retries - 1:
                        import time
                        time.sleep(2)
                        continue
                    else:
                        self.logger.error(f"❌ Persistent system encoding error after {max_retries} attempts")
                        return False
                else:
                    raise  # Re-raise non-encoding errors
        
        # Step 3: Collect responses
        source_path = result_path_final if turn_num > 1 and phase == "amb" else user_resp_path
        cmd = [
            "python", os.path.join(self.code_dir, "collect_response.py"),
            "--source_path", source_path,
            "--response_path", result_path_response,
            "--result_path", result_path_final
        ]
        
        return run_command(cmd, f"System response collection (turn {turn_num}, phase {phase})", self.logger)
    
    def run_user_interaction(self, turn_num: int, stage: int) -> bool:
        """Run user simulation (stage 1 or 2)."""
        
        stage_name = f"user_{stage}"
        
        # Determine data path
        if check_file_exists_and_not_empty(self.get_file_path(stage_name)):
            data_path = self.get_file_path(stage_name)
        else:
            data_path = os.path.join(self.data_dir, "bird_interact_data.jsonl")
        
        result_path_prompt = self.get_file_path(stage_name, "_prompt")
        result_path_response = self.get_file_path(stage_name, "_response")
        result_path_final = self.get_file_path(stage_name)
        
        # Step 1: Generate prompts
        if stage == 1:
            cmd = [
                "python", os.path.join(self.code_dir, "infer_api_user_1.py"),
                "--prompt_path", data_path,
                "--result_path", result_path_prompt,
                "--sys_resp_path", self.get_file_path("system"),
                "--DB_schema_path", os.path.join(self.data_dir, "[[DB_name]]/[[DB_name]]_schema.txt"),
                "--turn_num", str(turn_num)
            ]
        else:  # stage == 2
            cmd = [
                "python", os.path.join(self.code_dir, "infer_api_user_2.py"),
                "--prompt_path", data_path,
                "--result_path", result_path_prompt,
                "--sys_resp_path", self.get_file_path("system"),
                "--user_1_resp_path", self.get_file_path("user_1"),
                "--DB_schema_path", os.path.join(self.data_dir, "[[DB_name]]/[[DB_name]]_schema.txt"),
                "--turn_num", str(turn_num)
            ]
        
        if not run_command(cmd, f"User {stage} prompt generation (turn {turn_num})", self.logger):
            return False
        
        # Check if prompts were generated
        if not check_file_exists_and_not_empty(result_path_prompt):
            self.logger.warning(f"No prompts generated for user {stage} turn {turn_num}")
            return True  # Not an error, just no work to do
        
        # Step 2: Call API with retry mechanism for encoding issues
        max_retries = 3
        for retry in range(max_retries):
            try:
                cmd = [
                    "python", os.path.join(self.code_dir, "call_api.py"),
                    "--model_name", self.user_model,
                    "--prompt_path", result_path_prompt,
                    "--output_path", result_path_response
                ]
                
                if run_command(cmd, f"User {stage} API call (turn {turn_num}) - Attempt {retry + 1}", self.logger, show_progress=True):
                    break  # Success, exit retry loop
                elif retry < max_retries - 1:
                    self.logger.warning(f"⚠️ API call failed, retrying... ({retry + 1}/{max_retries})")
                    import time
                    time.sleep(2)  # Wait before retry
                else:
                    self.logger.error(f"❌ API call failed after {max_retries} attempts")
                    return False
                    
            except Exception as e:
                if "utf-8" in str(e).lower() or "encoding" in str(e).lower():
                    self.logger.warning(f"⚠️ Encoding error detected, attempt {retry + 1}/{max_retries}: {str(e)}")
                    if retry < max_retries - 1:
                        import time
                        time.sleep(2)
                        continue
                    else:
                        self.logger.error(f"❌ Persistent encoding error after {max_retries} attempts")
                        return False
                else:
                    raise  # Re-raise non-encoding errors
        
        # Step 3: Collect responses
        source_path = result_path_final if turn_num > 1 else os.path.join(self.data_dir, "bird_interact_data.jsonl")
        cmd = [
            "python", os.path.join(self.code_dir, "collect_response.py"),
            "--source_path", source_path,
            "--response_path", result_path_response,
            "--result_path", result_path_final
        ]
        
        return run_command(cmd, f"User {stage} response collection (turn {turn_num})", self.logger)
    
    def run_single_turn(self, turn_num: int, is_final: bool = False, phase: str = "amb") -> bool:
        """Run a complete turn (system + user1 + user2)."""
        
        self.logger.info(f"🔄 === Starting Turn {turn_num} (Phase: {phase}) ===")
        
        # System interaction
        self.logger.info(f"🤖 Running system interaction (turn {turn_num})")
        if not self.run_system_interaction(turn_num, phase):
            self.logger.error(f"❌ Failed system interaction for turn {turn_num}")
            return False
        
        # Skip user interaction for debug and follow phases
        if phase != "amb":
            self.logger.info(f"⏭️  Skipping user interaction for phase {phase}")
            return True
        
        # User interaction stage 1
        self.logger.info(f"👤 Running user interaction stage 1 (turn {turn_num})")
        if not self.run_user_interaction(turn_num, 1):
            self.logger.error(f"❌ Failed user 1 interaction for turn {turn_num}")
            return False
        
        # User interaction stage 2
        self.logger.info(f"👤 Running user interaction stage 2 (turn {turn_num})")
        if not self.run_user_interaction(turn_num, 2):
            self.logger.error(f"❌ Failed user 2 interaction for turn {turn_num}")
            return False
        
        self.logger.info(f"✅ === Completed Turn {turn_num} (Phase: {phase}) ===")
        return True
    
    def extract_sql_and_evaluate(self, suffix: str = "", follow_up_path: Optional[str] = None) -> bool:
        """Extract SQL from results and run evaluation."""
        
        data_path = self.get_file_path("system")
        result_path = self.get_file_path("sql_results", suffix)
        
        # Extract SQL
        cmd = [
            "python", os.path.join(self.code_dir, "wrap_up_sql.py"),
            "--data_path", data_path,
            "--result_path", result_path
        ]
        
        if follow_up_path:
            cmd.extend(["--follow_up_path", follow_up_path])
        
        if not run_command(cmd, f"SQL extraction{suffix}", self.logger):
            return False
        
        # Run evaluation
        cmd = [
            "python", os.path.join(self.eval_dir, "eval_bird_interact_batch.py"),
            "--jsonl", result_path
        ]
        
        return run_command(cmd, f"Evaluation{suffix}", self.logger)
    
    def run_phase_1_ambiguity_resolution(self) -> bool:
        """Run Phase 1: Multi-turn ambiguity resolution."""
        
        self.logger.info("🎯 ========================================")
        self.logger.info("🎯 Phase 1: Ambiguity Resolution")
        self.logger.info("🎯 ========================================")
        
        # Turn 1
        self.logger.info("🔄 Starting initial turn...")
        if not self.run_single_turn(1):
            return False
        
        # Get max turns from the system interaction file
        system_file = self.get_file_path("system")
        if not check_file_exists_and_not_empty(system_file):
            self.logger.error("❌ No system interaction file found after turn 1")
            return False
        
        max_turn = get_max_turn_from_jsonl(system_file, self.logger)
        self.logger.info(f"📊 Maximum turns determined: {max_turn}")
        
        # Intermediate turns (2 to max_turn-1)
        for turn_num in range(2, max_turn):
            self.logger.info(f"🔄 Starting intermediate turn {turn_num}/{max_turn-1}...")
            if not self.run_single_turn(turn_num):
                return False
        
        # Final turn (SQL generation)
        self.logger.info(f"🎯 Starting final turn {max_turn} (SQL generation)...")
        if not self.run_single_turn(max_turn, is_final=True):
            return False
        
        # Extract SQL and evaluate
        self.logger.info("🔍 Extracting SQL and running evaluation...")
        return self.extract_sql_and_evaluate()
    
    def run_phase_1_debug(self) -> bool:
        """Run Phase 1 Debugging: One more chance for debugging."""
        
        self.logger.info("🐛 ========================================")
        self.logger.info("🐛 Phase 1: Debugging")
        self.logger.info("🐛 ========================================")
        
        # Get the final turn number
        system_file = self.get_file_path("system")
        max_turn = get_max_turn_from_jsonl(system_file, self.logger)
        
        # Run debug turn
        self.logger.info(f"🔧 Running debug turn {max_turn}...")
        if not self.run_single_turn(max_turn, phase="debug"):
            return False
        
        # Extract SQL and evaluate
        self.logger.info("🔍 Extracting debugged SQL and running evaluation...")
        return self.extract_sql_and_evaluate("_debug")
    
    def run_phase_2_follow_up(self) -> bool:
        """Run Phase 2: Follow-up questions."""
        
        self.logger.info("❓ ========================================")
        self.logger.info("❓ Phase 2: Follow-up Questions")
        self.logger.info("❓ ========================================")
        
        # Get the final turn number
        system_file = self.get_file_path("system")
        max_turn = get_max_turn_from_jsonl(system_file, self.logger)
        
        # Run follow-up turn
        self.logger.info(f"❓ Running follow-up turn {max_turn}...")
        if not self.run_single_turn(max_turn, phase="follow"):
            return False
        
        # Extract SQL and evaluate
        self.logger.info("🔍 Extracting follow-up SQL and running evaluation...")
        follow_up_prompt_path = self.get_file_path("system", "_prompt")
        return self.extract_sql_and_evaluate("_fu", follow_up_prompt_path)
    
    def run_phase_2_debug(self) -> bool:
        """Run Phase 2 Debugging: Follow-up question debugging."""
        
        self.logger.info("🐛❓ ========================================")
        self.logger.info("🐛❓ Phase 2: Follow-up Debugging")
        self.logger.info("🐛❓ ========================================")
        
        # Get the final turn number
        system_file = self.get_file_path("system")
        max_turn = get_max_turn_from_jsonl(system_file, self.logger)
        
        # Run debug turn
        self.logger.info(f"🔧 Running follow-up debug turn {max_turn}...")
        if not self.run_single_turn(max_turn, phase="debug"):
            return False
        
        # Extract SQL and evaluate
        self.logger.info("🔍 Extracting debugged follow-up SQL and running evaluation...")
        follow_up_prompt_path = self.get_file_path("system", "_prompt")
        return self.extract_sql_and_evaluate("_fu_debug", follow_up_prompt_path)
    
    def run_full_experiment(self) -> bool:
        """Run the complete experiment pipeline."""
        
        self.logger.info("🚀 Starting BIRD-Interact Experiment")
        self.logger.info("🚀 " + "=" * 50)
        
        start_time = time.time()
        
        try:
            # Phase 1: Ambiguity Resolution
            self.logger.info("📝 Starting Phase 1: Ambiguity Resolution...")
            if not self.run_phase_1_ambiguity_resolution():
                self.logger.error("❌ Phase 1 Ambiguity Resolution failed")
                return False
            
            # Phase 1 Debugging
            self.logger.info("🔧 Starting Phase 1: Debugging...")
            if not self.run_phase_1_debug():
                self.logger.error("❌ Phase 1 Debugging failed")
                return False
            
            # Phase 2: Follow-up Questions
            self.logger.info("❓ Starting Phase 2: Follow-up Questions...")
            if not self.run_phase_2_follow_up():
                self.logger.error("❌ Phase 2 Follow-up failed")
                return False
            
            # Phase 2 Debugging
            self.logger.info("🔧❓ Starting Phase 2: Follow-up Debugging...")
            if not self.run_phase_2_debug():
                self.logger.error("❌ Phase 2 Debugging failed")
                return False
            
            duration = time.time() - start_time
            self.logger.info("🎉 " + "=" * 50)
            self.logger.info(f"🎉 Experiment completed successfully in {duration:.2f} seconds")
            self.logger.info(f"📁 Results saved in: {self.result_dir}")
            
            return True
            
        except Exception as e:
            self.logger.error(f"💥 Unexpected error during experiment: {str(e)}")
            return False


def main():
    """Main entry point for the experiment runner."""
    
    parser = argparse.ArgumentParser(
        description='Run BIRD-Interact conversational text-to-SQL experiments'
    )
    
    parser.add_argument(
        '--patience',
        type=int,
        default=3,
        help='Maximum conversation turns allowed (default: 3)'
    )
    
    parser.add_argument(
        '--system_model_name',
        type=str,
        default='gemini-2.0-flash',
        help='Model name for the AI system (default: gemini-2.0-flash)'
    )
    
    parser.add_argument(
        '--US_model_name',
        type=str,
        default='gemini-2.0-flash',
        help='Model name for user simulation (default: gemini-2.0-flash)'
    )
    
    parser.add_argument(
        '--project_root',
        type=str,
        default='/app/',
        help='Root directory of the project (default: /app/)'
    )
    
    parser.add_argument(
        '--log_level',
        type=str,
        default='INFO',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
        help='Logging level (default: INFO)'
    )
    
    parser.add_argument(
        '--log_dir',
        type=str,
        default=None,
        help='Directory for log files (default: project_root/logs)'
    )
    
    parser.add_argument(
        '--experiment_name',
        type=str,
        default=None,
        help='Custom experiment name suffix (default: auto-generated timestamp)'
    )
    
    args = parser.parse_args()
    
    # Setup configuration
    config = {
        'patience': args.patience,
        'system_model_name': args.system_model_name,
        'US_model_name': args.US_model_name,
        'project_root': args.project_root,
        'experiment_name': args.experiment_name
    }
    
    # Setup logging
    if args.log_dir is None:
        log_dir = os.path.join(args.project_root, 'logs')
    else:
        log_dir = args.log_dir
    
    logger = setup_logging(log_dir, args.log_level)
    
    # Log configuration
    logger.info("Starting BIRD-Interact Experiment Runner")
    logger.info("Configuration:")
    for key, value in config.items():
        logger.info(f"  {key}: {value}")
    
    # Initialize and run experiment
    experiment = BIRDInteractExperiment(config, logger)
    
    success = experiment.run_full_experiment()
    
    if success:
        logger.info("Experiment completed successfully!")
        sys.exit(0)
    else:
        logger.error("Experiment failed!")
        sys.exit(1)


if __name__ == "__main__":
    main()
