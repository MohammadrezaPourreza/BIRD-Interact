#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
BIRD-Interact Unified Pipeline
Unified BIRD-Interact conversational SQL generation pipeline with parameterized configuration and multiple run modes
"""
import os
import sys
import json
import argparse
import logging
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Any, Optional, Callable

# Add path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from anges.utils.inference_api import vertex_claude_inference, gemini_inference
from sql_evaluator import SQLEvaluator

class BirdInteractPipeline:
    """BIRD-Interact unified pipeline class"""
    
    def __init__(self, 
                 data_path: str,
                 db_schema_path: str, 
                 external_kg_path: str,
                 model: str = "gemini",
                 max_turns: int = 7,
                 log_level: str = "INFO",
                 run_real_eval: bool = False):
        """
        Initialize pipeline
        
        Args:
            data_path: Data file path
            db_schema_path: Database schema path template
            external_kg_path: External knowledge base path template
            model: The inference model to use ('gemini' or 'claude')
            max_turns: Maximum conversation turns
            log_level: Logging level
            run_real_eval: Whether to run real SQL evaluation
        """
        self.data_path = data_path
        self.db_schema_path = db_schema_path
        self.external_kg_path = external_kg_path
        self.max_turns = max_turns
        self.run_real_eval = run_real_eval
        
        # Setup logging first
        self._setup_logging(log_level)

        # Set inference API based on model name
        self.inference_api: Callable[[str], str]
        if model.lower() == 'gemini':
            self.inference_api = gemini_inference
        elif model.lower() == 'claude':
            self.inference_api = vertex_claude_inference
        else:
            raise ValueError(f"Unsupported model: {model}. Please choose 'gemini' or 'claude'.")
        self.logger.info(f"Using inference model: {model}")
        
        # Initialize SQL evaluator
        self.sql_evaluator = SQLEvaluator(log_level=log_level) if run_real_eval else None
        
    def _setup_logging(self, log_level: str):
        """Setup logging configuration"""
        # Clear existing handlers
        for handler in logging.root.handlers[:]:
            logging.root.removeHandler(handler)
            
        logging.basicConfig(
            level=getattr(logging, log_level.upper()),
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.StreamHandler(),
                logging.FileHandler('/tmp/bird_interact_pipeline.log', mode='a')
            ],
            force=True
        )
        self.logger = logging.getLogger(__name__)
        self.logger.info(f"Logging system initialized, level: {log_level}")
    
    def load_sample_data(self, sample_id: Optional[int] = None, limit: int = 1) -> List[Dict[str, Any]]:
        """Load sample data"""
        data = []
        with open(self.data_path, 'r', encoding='utf-8') as f:
            for i, line in enumerate(f):
                if sample_id is not None and i == sample_id:
                    return [json.loads(line)]
                if sample_id is None and i >= limit:
                    break
                data.append(json.loads(line))
        return data
    
    def load_db_schema(self, db_name: str) -> str:
        """Load database schema"""
        schema_path = self.db_schema_path.replace("[[DB_name]]", db_name)
        with open(schema_path, 'r', encoding='utf-8') as f:
            return f.read()
    
    def load_external_knowledge(self, db_name: str) -> List[Dict[str, Any]]:
        """Load external knowledge base"""
        kg_path = self.external_kg_path.replace("[[DB_name]]", db_name)
        knowledge = []
        with open(kg_path, 'r', encoding='utf-8') as f:
            for line in f:
                knowledge.append(json.loads(line))
        return knowledge
    
    def create_system_prompt(self, data: Dict[str, Any], turn_num: int = 1, conversation_history: List[Dict] = None) -> str:
        """Create system prompt"""
        db_name = data.get('selected_database', '')
        db_schema = self.load_db_schema(db_name)
        external_kg = self.load_external_knowledge(db_name)
        
        # Build conversation history
        history_text = ""
        if conversation_history:
            history_text = "\n# Previous Conversation:\n"
            for conv in conversation_history:
                history_text += f"System: {conv['system']}\n"
                history_text += f"User: {conv['user']}\n\n"
        
        prompt = f"""You are a good data scientist with great SQL writing ability. You have a DB called "{db_name}". You are given the DB schema information below:

# DB Schema Info:
{db_schema}

And you are given some useful external knowledge about this DB below:
# External Knowledge:
{json.dumps(external_kg, indent=2)}

# Instructions:
You are a good data scientist who is tasked with generating PostgreSQL to solve the user task below. However, the user's query may not be clear enough. Then you need to ask for clarification about these ambiguity in user task below. You only have {self.max_turns} turns to ask for clarification, each turn you can only ask one question with few sentences. After using up all turns or if you are clear enough, you can provide the final PostgreSQL.

You have the following choice at each turn:
1. **Ask for Clarification**: You can only ask **ONE** question each time! Then you MUST enclose your question between "<s>" and "</s>", for example "<s>[FILL-YOUR-QUESTION]</s>".
2. **Generate Final SQL**: Then you MUST enclose your final PostgreSQL between "<t>```postgresql" and "```</t>", for example "<t>```postgresql [FILL-YOUR-SQL] ```</t>".

NOTE: If you think you have asked enough questions or used up all turns, you MUST provide the final PostgreSQL about the Text-to-SQL task!

# User Task:
{data.get('query', '')}

{history_text}
### Turn {turn_num} ({self.max_turns} turns left):
# Format: "<s>[YOUR-ONLY-ONE-QUESTION]</s>" if you choose to ask for clarification; or "<t>```postgresql [FILL-YOUR-SQL] ```</t>" if you choose to generate final SQL.
- You: """
        
        return prompt
    
    def create_user_encoder_prompt(self, data: Dict[str, Any], system_question: str, turn_num: int = 1) -> str:
        """Create user encoder prompt"""
        db_name = data.get('selected_database', '')
        db_schema = self.load_db_schema(db_name)
        
        prompt = f"""### Task: Ambiguity Resolution

You are a good Text-to-SQL engineer and provide Text-to-SQL task to your client. Your client is asking for clarification about the ambiguity of your Text-to-SQL task and you are required to answer this question based on your ground-truth SQL.

# All Labeled Ambiguity Points:
```json
user_query_ambiguity: 
{json.dumps(data.get('user_query_ambiguity', {}), indent=4)}

knowledge_ambiguity: 
{json.dumps(data.get('knowledge_ambiguity', []), indent=4)}
```

# Ground Truth SQL:
{data.get('sol_sql', [''])[0]}

# System Question:
{system_question}

# Instructions:
You need to analyze the system's question and decide how to respond based on the ambiguity information and ground truth SQL. You should output one of the following actions:

1. `labeled("term")` - if the question is about a specific term that you can clarify
2. `unlabeled("segment")` - if the question is about a segment that you can clarify
3. `unanswerable()` - if you cannot answer the question

# Format: [ACTION]
- You: """
        
        return prompt
    
    def create_user_decoder_prompt(self, data: Dict[str, Any], system_question: str, user_action: str, turn_num: int = 1) -> str:
        """Create user decoder prompt"""
        db_name = data.get('selected_database', '')
        db_schema = self.load_db_schema(db_name)
        
        prompt = f"""### Task: Question Answering

You are a good Text-to-SQL engineer and provide Text-to-SQL task to your client. Your client is asking for clarification about the ambiguity of your Text-to-SQL task and you are required to answer this question based on your ground-truth SQL.

Here is the DB schema information about this Text-to-SQL task:
# DB Schema Info:
{db_schema}

# All Labeled Ambiguity Points:
```json
user_query_ambiguity: 
{json.dumps(data.get('user_query_ambiguity', {}), indent=4)}

knowledge_ambiguity: 
{json.dumps(data.get('knowledge_ambiguity', []), indent=4)}
```

# Ground Truth SQL:
{data.get('sol_sql', [''])[0]}

# System Question:
{system_question}

# Your Action:
{user_action}

# Instructions:
You need to answer the system's question based on the action you decided and the ambiguity information. You should provide a clear and helpful answer that helps the system understand what you want.

# Format: "<s>[YOUR-ANSWER]</s>"
- You: """
        
        return prompt
    
    def extract_response(self, response: str) -> str:
        """Extract response content"""
        if not response:
            return ""
        
        # Extract content between <s>...</s>
        if "<s>" in response and "</s>" in response:
            start = response.find("<s>") + 3
            end = response.find("</s>")
            return response[start:end].strip()
        
        # Extract content between <t>...</t>
        if "<t>" in response and "</t>" in response:
            start = response.find("<t>") + 3
            end = response.find("</t>")
            return response[start:end].strip()
        
        return response.strip()
    
    def is_sql_response(self, response: str) -> bool:
        """Check if response is SQL"""
        return "<t>" in response and "```postgresql" in response
    
    def _call_llm_with_retry(self, prompt: str, max_retries: int = 3, timeout: int = 60) -> str:
        """LLM call with retry and timeout"""
        for attempt in range(max_retries):
            try:
                self.logger.debug(f"LLM call attempt {attempt + 1}/{max_retries}")
                start_time = time.time()
                response = self.inference_api(prompt)
                elapsed = time.time() - start_time
                self.logger.debug(f"LLM call completed in: {elapsed:.2f} seconds")
                return response
            except Exception as e:
                self.logger.warning(f"LLM call failed (attempt {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)  # Exponential backoff
                else:
                    self.logger.error(f"LLM call ultimately failed: {e}")
                    return ""
        return ""
    
    def run_conversation(self, data: Dict[str, Any], sample_id: Optional[int] = None) -> Dict[str, Any]:
        """Run conversation for single sample"""
        sample_id = sample_id or 0
        question = data.get('query', '')
        db_name = data.get('selected_database', 'unknown')
        
        self.logger.info(f"[Sample {sample_id}] Starting...")
        self.logger.info(f"[Sample {sample_id}] Question: {question}")
        self.logger.info(f"[Sample {sample_id}] Database: {db_name}")
        
        conversation_history = []
        
        # Start conversation
        for turn in range(1, self.max_turns + 1):
            self.logger.info(f"[Sample {sample_id}] Turn {turn}: System generating answer...")
            
            try:
                # 1. System reasoning
                system_prompt = self.create_system_prompt(data, turn, conversation_history)
                system_response = self._call_llm_with_retry(system_prompt)
                system_content = self.extract_response(system_response)
                
                self.logger.debug(f"[Sample {sample_id}] Turn {turn} - System response: {system_content[:100]}...")
                
                # Check if SQL was generated
                if self.is_sql_response(system_response):
                    self.logger.info(f"[Sample {sample_id}] Turn {turn}: Generated SQL successfully")
                    self.logger.info(f"Sample {sample_id} at turn {turn} generated SQL")
                    return self._create_result(data, system_content, turn, conversation_history, True)
                
                # 2. User simulator encoder
                self.logger.info(f"[Sample {sample_id}] Turn {turn}: User simulator analyzing...")
                user_encoder_prompt = self.create_user_encoder_prompt(data, system_content, turn)
                user_encoder_response = self._call_llm_with_retry(user_encoder_prompt)
                user_action = self.extract_response(user_encoder_response)
                
                # 3. User simulator decoder
                self.logger.info(f"[Sample {sample_id}] Turn {turn}: User simulator answering...")
                user_decoder_prompt = self.create_user_decoder_prompt(data, system_content, user_action, turn)
                user_decoder_response = self._call_llm_with_retry(user_decoder_prompt)
                user_content = self.extract_response(user_decoder_response)
                
                self.logger.info(f"[Sample {sample_id}] Turn {turn}: User response: {user_content[:100]}...")
                
                # Record conversation history
                conversation_history.append({
                    'turn': turn,
                    'system': system_content,
                    'user': user_content,
                    'user_action': user_action
                })
                
            except Exception as e:
                self.logger.error(f"[Sample {sample_id}] Turn {turn}: Processing failed - {e}")
                self.logger.error(f"Sample {sample_id} at turn {turn} processing failed: {e}")
                return self._create_result(data, None, turn, conversation_history, False)
        
        self.logger.warning(f"[Sample {sample_id}] Reached maximum turns ({self.max_turns})")
        self.logger.warning(f"Sample {sample_id} reached maximum turns {self.max_turns}")
        return self._create_result(data, None, self.max_turns, conversation_history, False)
    
    def _create_result(self, data: Dict[str, Any], final_sql: Optional[str], turns: int, 
                      conversation_history: List[Dict], success: bool) -> Dict[str, Any]:
        """Create result dictionary"""
        # Clean SQL, remove ```postgresql markers
        if final_sql:
            if final_sql.startswith('```postgresql'):
                final_sql = final_sql[13:]
            if final_sql.endswith('```'):
                final_sql = final_sql[:-3]
            final_sql = final_sql.strip()
        
        result = {
            'instance_id': data.get('instance_id', ''),
            'selected_database': data.get('selected_database', ''),
            'query': data.get('query', ''),
            'sol_sql': data.get('sol_sql', []),
            'pred_sqls': [final_sql] if final_sql else [],
            'conditions': data.get('conditions', {"decimal": 2, "distinct": False, "order": True}),
            'user_query_ambiguity': data.get('user_query_ambiguity', {}),
            'knowledge_ambiguity': data.get('knowledge_ambiguity', []),
            'follow_up': data.get('follow_up', {}),
            'test_cases': data.get('test_cases', []),
            'conversation_turns': turns,
            'conversation_history': conversation_history,
            'success': success,
            'terminate_flg': success
        }
        
        return result
    
    def run_single_sample(self, sample_id: int = 0) -> Dict[str, Any]:
        """Run single sample"""
        self.logger.info(f"🚀 Running single sample mode - SampleID: {sample_id}")
        
        data_list = self.load_sample_data(sample_id=sample_id)
        if not data_list:
            raise ValueError(f"Could not load Sample {sample_id}")
        
        data = data_list[0]
        result = self.run_conversation(data, sample_id)
        
        # Save results
        self.logger.info(f"[Sample {sample_id}] Saving results...")
        self._save_results([result], f"/tmp/single_sample_{sample_id}_result.json")
        eval_file = f"/tmp/single_sample_{sample_id}_eval.jsonl"
        self._save_eval_format([result], eval_file)
        
        # Run real evaluation (if enabled)
        eval_results = {}
        if self.run_real_eval:
            eval_results = self._run_real_evaluation(eval_file)
        
        # Display result summary
        status = "Success" if result['success'] else "Failed"
        turns = result['conversation_turns']
        if eval_results and eval_results.get('details'):
            detail = eval_results['details'].get(result['instance_id'], {})
            sql_correct = detail.get('is_correct', False)
            sql_status = "Correct" if sql_correct else "Incorrect"
            exec_time = detail.get('execution_time', 0)
            if exec_time > 0:
                self.logger.info(f"📊 Result: {data.get('selected_database', 'unknown')} - {status} - {turns}turns - SQL: {sql_status} - Execution time: {exec_time:.2f}s")
            else:
                self.logger.info(f"📊 Result: {data.get('selected_database', 'unknown')} - {status} - {turns}turns - SQL: {sql_status}")
        else:
            self.logger.info(f"📊 Result: {data.get('selected_database', 'unknown')} - {status} - {turns}turns")
        
        return result
    
    def run_multiple_samples(self, num_samples: int, num_workers: int = 1) -> List[Dict[str, Any]]:
        """Run multiple samples"""
        self.logger.info(f"🚀 Running multiple samples mode - Sample count: {num_samples}, Worker threads: {num_workers}")
        
        data_list = self.load_sample_data(limit=num_samples)
        
        if num_workers == 1:
            # Single-threaded mode
            results = []
            for i, data in enumerate(data_list):
                self.logger.info(f"📝 Processing Sample {i+1}/{len(data_list)}")
                result = self.run_conversation(data, i)
                results.append(result)
        else:
            # Multi-threaded mode
            self.logger.info(f"🔄 Processing {len(data_list)} samples using multi-threaded mode")
            results = []
            with ThreadPoolExecutor(max_workers=num_workers) as executor:
                future_to_data = {
                    executor.submit(self.run_conversation, data, i): (i, data) 
                    for i, data in enumerate(data_list)
                }
                
                completed = 0
                for future in as_completed(future_to_data):
                    i, data = future_to_data[future]
                    completed += 1
                    self.logger.info(f"📝 Completed Sample {i} ({completed}/{len(data_list)})")
                    try:
                        result = future.result()
                        results.append(result)
                    except Exception as exc:
                        self.logger.error(f"Sample {i} Processing failed: {exc}")
                        # Create failed result
                        results.append(self._create_result(data, None, 0, [], False))
        
        # Sort by sample ID
        results.sort(key=lambda x: int(x.get('instance_id', '0').split('_')[-1]) if '_' in x.get('instance_id', '0') else 0)
        
        # Save results
        self.logger.info("💾 Saving result file...")
        self._save_results(results, "/tmp/multiple_samples_results.json")
        eval_file = "/tmp/multiple_samples_eval.jsonl"
        self._save_eval_format(results, eval_file)
        
        # Run real evaluation (if enabled)
        eval_results = {}
        if self.run_real_eval:
            eval_results = self._run_real_evaluation(eval_file)
        
        # Print statistics
        self._print_statistics(results, eval_results)
        
        return results
    
    def _save_results(self, results: List[Dict[str, Any]], filepath: str):
        """Save results to JSON file"""
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        self.logger.info(f"Results saved to {filepath}")
    
    def _save_eval_format(self, results: List[Dict[str, Any]], filepath: str):
        """Save evaluation format file"""
        with open(filepath, 'w', encoding='utf-8') as f:
            for item in results:
                f.write(json.dumps(item, ensure_ascii=False) + '\n')
        self.logger.info(f"Evaluation format file saved to {filepath}")
    
    def _run_real_evaluation(self, eval_file_path: str) -> Dict[str, Any]:
        """Run real BIRD-Interact evaluation"""
        if not self.sql_evaluator:
            self.logger.warning("SQL evaluator not initialized")
            return {}
            
        try:
            self.logger.info(f"🔍 Running real SQL evaluation...")
            results = self.sql_evaluator.run_evaluation(eval_file_path)
            
            if results.get('errors'):
                self.logger.warning(f"Evaluation completed with errors: {results['errors']}")
            else:
                self.logger.info("✅ SQL evaluation completed")
                
            return results
            
        except Exception as e:
            self.logger.error(f"Evaluation error: {e}")
            return {}
    
    def _print_statistics(self, results: List[Dict[str, Any]], eval_results: Dict[str, Any] = None):
        """Print statistics"""
        total = len(results)
        successful = sum(1 for r in results if r['success'])
        avg_turns = sum(r['conversation_turns'] for r in results) / total if total > 0 else 0
        
        # If there are real evaluation results, use them
        if eval_results and eval_results.get('summary'):
            summary = eval_results['summary']
            correct_sql = summary.get('correct_sql', 0)
            accuracy = summary.get('sql_correctness_rate', 0)
            avg_exec_time = summary.get('avg_execution_time', 0)
        else:
            correct_sql = successful
            accuracy = successful / total * 100 if total > 0 else 0
            avg_exec_time = 0
        
        print(f"\n{'='*60}")
        print(f"BIRD-Interact Pipeline Statistics")
        print(f"{'='*60}")
        print(f"Total Samples: {total}")
        print(f"Successful SQL generation: {successful}")
        print(f"SQL generation success rate: {successful/total*100:.1f}%")
        if eval_results and eval_results.get('summary'):
            print(f"SQL correctness: {correct_sql}/{total} ({accuracy:.1f}%)")
            if avg_exec_time > 0:
                print(f"Average execution time: {avg_exec_time:.2f}s")
        print(f"Average conversation turns: {avg_turns:.1f}")
        print(f"{'='*60}")
        
        # Detailed results
        for i, result in enumerate(results):
            if eval_results and eval_results.get('details'):
                detail = eval_results['details'].get(result['instance_id'], {})
                sql_status = "✅" if detail.get('is_correct', False) else "❌"
                gen_status = "✅" if result['success'] else "❌"
                print(f"{gen_status}{sql_status} Sample {i}: {result['instance_id']} - {result['selected_database']} - {result['conversation_turns']}turns")
            else:
                status = "✅" if result['success'] else "❌"
                print(f"{status} Sample {i}: {result['instance_id']} - {result['selected_database']} - {result['conversation_turns']}turns")

def main():
    """Main function"""
    parser = argparse.ArgumentParser(description='BIRD-Interact Unified Pipeline')
    
    # Data path parameters
    parser.add_argument('--data_path', type=str, 
                       default="/home/hailongli/BIRDInteract/BIRD-Interact/bird_interact_conv/data/bird-interact-lite/bird_interact_data.jsonl",
                       help='Data file path')
    parser.add_argument('--db_schema_path', type=str,
                       default="/home/hailongli/BIRDInteract/BIRD-Interact/bird_interact_conv/data/bird-interact-lite/[[DB_name]]/[[DB_name]]_schema.txt",
                       help='Database schema path template')
    parser.add_argument('--external_kg_path', type=str,
                       default="/home/hailongli/BIRDInteract/BIRD-Interact/bird_interact_conv/data/bird-interact-lite/[[DB_name]]/[[DB_name]]_kb.jsonl",
                       help='External knowledge base path template')
    
    # Run mode parameters
    parser.add_argument('--mode', type=str, choices=['single', 'multiple'], default='single',
                       help='Run mode: single=run a single sample, multiple=run multiple samples')
    parser.add_argument('--sample_id', type=int, default=0,
                       help='The SampleID to use in single sample mode')
    parser.add_argument('--num_samples', type=int, default=3,
                       help='The number of samples to run in multiple sample mode')
    
    # Configuration parameters
    parser.add_argument('--model', type=str, choices=['gemini', 'claude'], default='gemini',
                       help='The inference model to use (gemini or claude)')
    parser.add_argument('--max_turns', type=int, default=7,
                       help='Maximum number of conversation turns')
    parser.add_argument('--num_workers', type=int, default=1,
                       help='Number of parallel processing workers')
    parser.add_argument('--log_level', type=str, choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'], default='INFO',
                       help='Logging level')
    parser.add_argument('--run_real_eval', action='store_true',
                       help='Run real SQL evaluation (requires database environment)')
    
    # Output parameters
    parser.add_argument('--output_dir', type=str, default='/tmp',
                       help='Output directory')
    
    args = parser.parse_args()
    
    # Create pipeline
    pipeline = BirdInteractPipeline(
        data_path=args.data_path,
        db_schema_path=args.db_schema_path,
        external_kg_path=args.external_kg_path,
        model=args.model,
        max_turns=args.max_turns,
        log_level=args.log_level,
        run_real_eval=args.run_real_eval
    )
    
    # Run pipeline
    if args.mode == 'single':
        print(f"🚀 Running single sample mode - SampleID: {args.sample_id}")
        result = pipeline.run_single_sample(args.sample_id)
        print(f"\n📊 Result: {result['instance_id']} - {'Success' if result['success'] else 'Failed'} - {result['conversation_turns']}turns")
    else:
        print(f"🚀 Running multiple samples mode - Sample count: {args.num_samples}, Workers: {args.num_workers}")
        results = pipeline.run_multiple_samples(args.num_samples, args.num_workers)

if __name__ == "__main__":
    main()