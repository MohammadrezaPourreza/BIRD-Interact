# BIRD-Interact New Pipeline

A new BIRD-Interact conversational SQL generation pipeline, completely rewritten in Python to avoid file I/O, with full user simulator and termination logic support.

## 🚀 Quick Start

### 1. Environment Setup

#### Option A: Docker PostgreSQL (Recommended)
```bash
# Start PostgreSQL with Docker
cd /home/hailongli/BIRDInteract/BIRD-Interact/evaluation
docker-compose up -d postgresql

# Verify PostgreSQL is running
PGPASSWORD=123123 psql -h localhost -p 5432 -U root -d postgres -c "\l"
```

#### Option B: Local PostgreSQL
```bash
# Install PostgreSQL locally (if not using Docker)
sudo apt-get install postgresql postgresql-contrib
sudo systemctl start postgresql
```

### 2. Activate Environment
```bash
# Activate virtual environment
source /home/hailongli/BIRDInteract/BIRD-Interact/venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Run Pipeline

#### Basic Usage
```bash
# Run single sample
python bird_interact_pipeline.py --mode single --sample_id 0

# Run multiple samples
python bird_interact_pipeline.py --mode multiple --num_samples 3

# Run with real SQL evaluation (requires database environment)
python bird_interact_pipeline.py --mode single --sample_id 0 --run_real_eval
```

#### Advanced Usage
```bash
# Run with custom parameters
python bird_interact_pipeline.py \
    --mode multiple \
    --num_samples 10 \
    --max_turns 5 \
    --num_workers 4 \
    --run_real_eval \
    --log_level DEBUG

# Run standalone SQL evaluation
python sql_evaluator.py --input /path/to/results.jsonl
```

## 📁 File Structure

- `bird_interact_pipeline.py` - Unified pipeline implementation with parameterized configuration
- `sql_evaluator.py` - Standalone SQL evaluation tool with Docker PostgreSQL support
- `final_eval_validation.py` - Format validation utility
- `COMPLETE_PIPELINE_SUMMARY.md` - Detailed technical documentation

## ⚙️ Configuration Parameters

### Command Line Arguments
```bash
# Basic parameters
--data_path          # Data file path
--db_schema_path     # Database schema path template
--external_kg_path   # External knowledge base path template

# Run modes
--mode              # single=single sample, multiple=multiple samples
--sample_id         # Sample ID for single sample mode
--num_samples       # Number of samples for multiple samples mode

# Configuration parameters
--max_turns         # Maximum conversation turns (default: 7)
--num_workers       # Number of parallel processing workers (default: 1)
--log_level         # Logging level (DEBUG, INFO, WARNING, ERROR)
--run_real_eval     # Run real SQL evaluation (requires database environment)

# Output parameters
--output_dir        # Output directory (default: /tmp)
```

## 🔧 SQL Evaluation Features

### Two Evaluation Modes

#### 1. Basic Mode (Default)
- Only checks SQL generation success
- No database connection required
- Fast execution

```bash
python bird_interact_pipeline.py --mode single --sample_id 0
```

**Output:**
```
Total Samples: 1
Successful SQL Generation: 1
SQL Generation Success Rate: 100.0%
Average Conversation Turns: 2.0
```

#### 2. Real Evaluation Mode
- Uses BIRD-Interact evaluation system
- Checks SQL correctness against ground truth
- Requires Docker PostgreSQL environment

```bash
python bird_interact_pipeline.py --mode single --sample_id 0 --run_real_eval
```

**Output:**
```
Total Samples: 1
Successful SQL Generation: 1
SQL Generation Success Rate: 100.0%
SQL Correctness: 1/1 (100.0%)
Average Conversation Turns: 2.0
Average Execution Time: 0.15s
```

### Standalone SQL Evaluator

The `sql_evaluator.py` script provides independent SQL evaluation capabilities:

```bash
# Basic evaluation
python sql_evaluator.py --input /path/to/results.jsonl

# Save detailed results
python sql_evaluator.py --input /path/to/results.jsonl --output /path/to/detailed_results.json

# Custom evaluation script path
python sql_evaluator.py --input /path/to/results.jsonl --eval_script /custom/path/eval_bird_interact_batch.py
```

## 🐳 Docker PostgreSQL Setup

### Prerequisites
- Docker and Docker Compose installed
- BIRD-Interact database dumps available

### Setup Steps
1. **Start PostgreSQL Container:**
   ```bash
   cd /home/hailongli/BIRDInteract/BIRD-Interact/evaluation
   docker-compose up -d postgresql
   ```

2. **Verify Database Initialization:**
   ```bash
   PGPASSWORD=123123 psql -h localhost -p 5432 -U root -d postgres -c "\l"
   ```

3. **Check Database Templates:**
   ```bash
   PGPASSWORD=123123 psql -h localhost -p 5432 -U root -d crypto_template -c "\dt"
   ```

### Database Configuration
- **Host:** localhost
- **Port:** 5432
- **User:** root
- **Password:** 123123
- **Templates:** All BIRD-Interact databases with schema and data

## 📊 Output Format

### Pipeline Results
Results are saved in JSON format with the following structure:

```json
{
  "instance_id": "crypto_1",
  "selected_database": "crypto",
  "query": "What is the total volume?",
  "conversation_turns": 2,
  "success": true,
  "pred_sqls": ["SELECT SUM(volume) FROM trades"],
  "conversation_history": [...],
  "terminate_flg": true
}
```

### Evaluation Results
When using real evaluation mode, additional fields are included:

```json
{
  "instance_id": "crypto_1",
  "status": "success",
  "is_correct": true,
  "generated_sql": "SELECT SUM(volume) FROM trades",
  "sol_sql": "SELECT SUM(volume) FROM trades",
  "execution_time": 0.15,
  "error_msg": ""
}
```

## 🔍 Troubleshooting

### Common Issues

1. **PostgreSQL Connection Failed:**
   ```bash
   # Check if Docker container is running
   docker ps | grep postgresql
   
   # Restart if needed
   docker-compose restart postgresql
   ```

2. **Database Templates Empty:**
   ```bash
   # Recreate container with fresh data
   docker-compose down postgresql
   docker volume rm evaluation_postgresql_data
   docker-compose up -d postgresql
   ```

3. **Evaluation Script Not Found:**
   ```bash
   # Check evaluation script path
   ls -la /home/hailongli/BIRDInteract/BIRD-Interact/evaluation/src/eval_bird_interact_batch.py
   ```

4. **Permission Denied:**
   ```bash
   # Check file permissions
   chmod +x bird_interact_pipeline.py sql_evaluator.py
   ```

### Log Files
- Pipeline logs: `/tmp/bird_interact_pipeline.log`
- Evaluation logs: Console output with timestamps

## 🚀 Performance Tips

1. **Use Multi-threading for Multiple Samples:**
   ```bash
   python bird_interact_pipeline.py --mode multiple --num_samples 10 --num_workers 4
   ```

2. **Enable Real Evaluation Only When Needed:**
   - Basic mode is much faster
   - Use real evaluation for final testing

3. **Optimize Database Connection:**
   - Use Docker PostgreSQL for consistency
   - Ensure database templates are properly initialized

## 📈 Example Results

### Single Sample Run
```
🚀 Running single sample mode - Sample ID: 0
📊 Result: crypto_1 - Success - 2 turns - SQL: Correct - Execution time: 0.15s
```

### Multiple Samples Run
```
🚀 Running multiple samples mode - Number of samples: 10, Worker threads: 4
📝 Processing sample 1/10
📝 Processing sample 2/10
...
📊 Results: 8/10 successful, 6/10 correct SQL
```

### Evaluation Results
```
BIRD-Interact SQL Evaluation Detailed Results
================================================================================
Total Samples: 10
Successful SQL Generation: 10
SQL Generation Success Rate: 100.0%
SQL Correctness: 8/10 (80.0%)
Average Conversation Turns: 2.3
Average Execution Time: 0.18s
================================================================================
✅✅ crypto_1 - crypto - 2 turns
✅❌ crypto_2 - crypto - 3 turns
...
================================================================================
Legend: First symbol=SQL Generation, Second symbol=SQL Correctness
        ✅=Success, ❌=Failed
```

## 🔄 Migration from Old Pipeline

The new pipeline is fully compatible with the old shell script approach but provides:

1. **Better Error Handling:** Comprehensive error messages and logging
2. **Real SQL Evaluation:** Actual correctness checking with database execution
3. **Docker Support:** Easy database setup without local PostgreSQL installation
4. **Parallel Processing:** Multi-threaded execution for multiple samples
5. **Detailed Output:** Rich result format with conversation history and metadata

## 📝 License

This project follows the same license as the original BIRD-Interact project.

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test with both basic and real evaluation modes
5. Submit a pull request

## 📞 Support

For issues and questions:
1. Check the troubleshooting section above
2. Review log files for detailed error messages
3. Ensure Docker PostgreSQL is properly configured
4. Verify all dependencies are installed correctly