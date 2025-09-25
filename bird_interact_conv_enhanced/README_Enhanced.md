# BIRD-Interact Enhanced Conversational Module with SQL Execution Tool

This enhanced module extends the original BIRD-Interact conversational system with a powerful SQL execution tool that allows LLMs to interactively explore databases during the clarification phase. This leads to more informed questions, better understanding of user requirements, and ultimately higher-quality SQL solutions.

## 🚀 Key Enhancements

### SQL Execution Tool Integration
- **Interactive SQL Exploration**: LLMs can execute SQL queries during conversations to explore data structure and contents
- **Real-time Feedback**: Immediate results and error messages help LLMs understand the database better
- **Separate Budget System**: Independent budgets for clarification questions and SQL executions
- **Enhanced Error Handling**: Detailed error categorization with helpful suggestions

### Advanced Conversation Flow
- **Multi-Action Turns**: LLMs can ask questions, execute SQL, or provide final answers in each turn
- **Reflection Framework**: Built-in prompts encourage critical thinking and self-assessment
- **Budget Management**: Smart budget tracking ensures efficient use of both question and SQL budgets
- **Progressive Understanding**: SQL exploration results inform better clarification questions

## 🏗️ Architecture Overview

```
Enhanced BIRD-Interact Flow:
┌─────────────────────────────────────────────────────────────┐
│                    Enhanced Phase 1: Ambiguity Resolution   │
├─────────────────────────────────────────────────────────────┤
│ Turn 1-N: LLM can choose from:                            │
│ ┌─────────────────┐ ┌─────────────────┐ ┌──────────────────┐ │
│ │ Ask Clarification│ │ Execute SQL     │ │ Provide Final SQL │ │
│ │ <s>question</s>  │ │ <sql_execute>   │ │ <t>```sql```</t>  │ │
│ │                 │ │ query           │ │                  │ │
│ │ Budget: 3 turns │ │ </sql_execute>  │ │ (Terminates)     │ │
│ │                 │ │ Budget: 5 execs │ │                  │ │
│ └─────────────────┘ └─────────────────┘ └──────────────────┘ │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    Enhanced Debugging Phase                │
├─────────────────────────────────────────────────────────────┤
│ • SQL exploration for error analysis                       │
│ • Diagnostic queries to understand issues                  │
│ • Enhanced error messages with suggestions                 │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    Enhanced Follow-up Phase                │
├─────────────────────────────────────────────────────────────┤
│ • Fresh SQL execution budget for follow-up exploration     │
│ • Context-aware prompting with previous solution          │
│ • Same enhanced debugging capabilities                     │
└─────────────────────────────────────────────────────────────┘
```

## 📋 Directory Structure

```
bird_interact_conv_enhanced/
├── code/
│   ├── sql_execution_tool.py              # Core SQL execution tool
│   ├── infer_api_system_enhanced.py       # Enhanced system inference
│   ├── collect_response_enhanced.py       # Enhanced response processing
│   ├── infer_api_user_1.py               # User simulator (step 1)
│   ├── infer_api_user_2.py               # User simulator (step 2)
│   ├── collect_response.py               # Original response collection
│   ├── call_api.py                       # API calling interface
│   ├── sql_parser.py                     # SQL parsing utilities
│   ├── wrap_up_sql.py                    # SQL formatting
│   └── config.py                         # API configuration
├── prompts/
│   ├── prompts_enhanced.py               # Enhanced prompts with SQL tool
│   ├── prompts.py                        # Original prompts (fallback)
│   └── prompts_for_bird_interact_full.py # Full dataset prompts
├── pipeline/
│   ├── run_enhanced_pipeline.sh          # Main enhanced pipeline
│   └── run_gpt.sh                        # Original pipeline (reference)
├── data/
│   └── bird-interact-lite/               # Dataset (to be downloaded)
├── results/                              # Enhanced results with SQL metrics
├── calculate_enhanced_score.py           # Comprehensive scoring
├── calculate_final_score.py              # Original scoring (reference)
└── README.md                             # This file
```

## 🛠️ Setup and Installation

### 1. Prerequisites
- All original BIRD-Interact prerequisites
- Enhanced Docker setup with SQL execution capabilities
- API keys configured in `code/config.py`

### 2. Database Setup
Use the same database setup as the original BIRD-Interact:
```bash
cd ../evaluation
./setup-databases.sh
```

### 3. API Configuration
Update `code/config.py` with your model configurations:
```python
model_config = {
    "gpt-4o": {"base_url": "YOUR_API_URL", "api_key": "YOUR_API_KEY"},
    "gpt-4o-mini": {"base_url": "YOUR_API_URL", "api_key": "YOUR_API_KEY"},
}
```

## 🏃‍♂️ Running the Enhanced Pipeline

### Basic Usage
```bash
cd pipeline
bash run_enhanced_pipeline.sh
```

### Configuration Parameters
Edit the top of `run_enhanced_pipeline.sh` to customize:

```bash
# Basic parameters
patience=3                    # Clarification question budget
max_sql_executions=5         # SQL execution budget (NEW!)
system_model_name="gpt-4o"   # System model
US_model_name="gpt-4o-mini"  # User simulator model
project_root="/app"          # Project root path
```

### Advanced Configuration
- **Patience Budget**: Number of clarification questions allowed (original feature)
- **SQL Execution Budget**: Number of SQL queries allowed during clarification and debugging phases
- **Independent Budgets**: Question and SQL budgets are tracked separately
- **Phase-specific Resets**: SQL budget resets for follow-up phase

## 🔧 SQL Execution Tool Features

### Tool Usage Format
LLMs use the tool by wrapping SQL in special tags:
```
<sql_execute>SELECT COUNT(*) FROM users WHERE active = true;</sql_execute>
```

### Comprehensive Error Handling
The tool provides detailed error categorization:
- **Syntax Errors**: With specific suggestions for common issues
- **Table/Column Not Found**: Clear guidance on schema verification
- **Permission Errors**: Appropriate handling of access restrictions
- **Timeout Errors**: Suggestions for query optimization
- **Type Errors**: Data type mismatch guidance

### Result Formatting
Results are formatted for optimal LLM understanding:
```
✅ **SQL Execution Successful**
**Query Type:** SELECT
**Total Rows:** 150
**Displayed Rows:** 100
⚠️ *Results truncated to 100 rows*

**Results:**
```
Row 1: john@example.com | John Doe | 2023-01-01
Row 2: jane@example.com | Jane Smith | 2023-01-02
...
```
```

### Safety Features
- **Result Truncation**: Prevents overwhelming LLMs with large result sets
- **Query Timeout**: Prevents long-running queries from blocking conversations
- **Error Recovery**: Graceful handling of database connection issues
- **Budget Enforcement**: Prevents excessive SQL usage

## 📊 Enhanced Evaluation Metrics

### Traditional BIRD-Interact Scoring
The enhanced system maintains full compatibility with original scoring:
- Phase 1 First Try: 0.7 points
- Phase 1 After Debugging: 0.5 points  
- Phase 2 First Try: 0.3 points
- Phase 2 After Debugging: 0.2 points

### New Enhanced Metrics
```bash
python calculate_enhanced_score.py \
    --result_dir path/to/results \
    --patience 3 \
    --sql_executions 5
```

Additional metrics tracked:
- **SQL Adoption Rate**: Percentage of instances using SQL tool
- **SQL Success Rate**: Successful SQL executions / total attempts
- **SQL Efficiency Score**: Weighted metric of successful usage vs budget
- **Enhanced Score**: Traditional score with SQL effectiveness bonus (up to 10%)

### Comprehensive Reporting
The enhanced scorer generates detailed reports including:
- Traditional vs Enhanced performance comparison
- SQL tool usage patterns and effectiveness
- Phase-by-phase breakdown with SQL impact
- Budget utilization analysis
- Error categorization and patterns

## 🧪 Testing and Validation

### Unit Testing SQL Tool
```bash
cd code
python sql_execution_tool.py  # Runs built-in tests
```

### Integration Testing
```bash
# Test with a small subset
head -n 5 data/bird-interact-lite/bird_interact_data.jsonl > test_data.jsonl
# Modify pipeline to use test_data.jsonl
bash run_enhanced_pipeline.sh
```

### Validation Checklist
- [ ] SQL tool executes queries correctly
- [ ] Error handling provides useful feedback
- [ ] Budget tracking works independently
- [ ] Results format is LLM-friendly
- [ ] Original scoring compatibility maintained
- [ ] Enhanced metrics are meaningful

## 🔍 Key Implementation Details

### ConversationState Management
The enhanced system introduces `ConversationState` class to track:
- Turn progression and limits
- SQL execution usage and budget
- Conversation history with SQL results
- Termination conditions and flow control

### Enhanced Response Processing
The `collect_response_enhanced.py` module:
- Parses SQL execution tags from LLM responses
- Executes SQL queries using the tool
- Formats results back into conversation flow
- Maintains conversation state consistency

### Prompt Engineering
Enhanced prompts in `prompts_enhanced.py`:
- Clear action options (question/SQL/final answer)
- Budget awareness messaging
- Reflection framework integration
- Error-specific guidance for debugging

### Pipeline Orchestration
The `run_enhanced_pipeline.sh` script:
- Manages separate budget tracking
- Handles SQL execution at each turn
- Maintains backward compatibility
- Provides comprehensive logging

## 🚨 Important Notes and Limitations

### Budget Management
- Question budget (patience) and SQL budget are independent
- SQL budget resets between main phase and follow-up phase
- Budget enforcement prevents runaway conversations
- Budget exhaustion forces final answer generation

### Database Safety
- SQL execution is read-only by default
- Query timeout prevents blocking
- Result truncation prevents memory issues
- Connection pooling handles concurrent access

### LLM Compatibility
- Tool works with any API-compatible model
- Requires models that can follow structured output format
- Performance varies significantly between models
- Larger models tend to use SQL tool more effectively

### Performance Considerations
- SQL execution adds latency to conversations
- Database connection overhead per query
- Result processing and formatting costs
- Increased token usage from SQL results

## 🔬 Research and Development

### Experimental Features
The enhanced implementation serves as a platform for research into:
- Tool-augmented conversation systems
- Interactive database exploration strategies
- Multi-budget optimization in conversational AI
- Reflection and self-assessment in LLMs

### Metrics for Analysis
Track these metrics for research insights:
- Correlation between SQL usage and final accuracy
- Patterns in successful SQL exploration strategies
- Impact of budget constraints on behavior
- Error recovery effectiveness

### Future Enhancements
Potential areas for further development:
- **Advanced SQL Analysis**: Query plan analysis and optimization suggestions
- **Schema Exploration**: Automated schema discovery and documentation
- **Multi-turn SQL**: Complex queries built across multiple turns
- **Collaborative Filtering**: Learning from successful SQL patterns
- **Dynamic Budgets**: Adaptive budget allocation based on complexity

## 📚 Comparison with Original System

| Feature | Original BIRD-Interact | Enhanced BIRD-Interact |
|---------|----------------------|------------------------|
| Clarification Questions | ✅ Limited by patience budget | ✅ Same budget system |
| SQL Exploration | ❌ None | ✅ Separate SQL budget |
| Error Debugging | ✅ Basic retry mechanism | ✅ Enhanced with SQL diagnostics |
| Conversation Flow | ✅ Linear: question → SQL | ✅ Flexible: question/SQL/answer |
| Budget System | ✅ Single patience budget | ✅ Dual budget system |
| Reflection Prompts | ❌ Minimal | ✅ Built-in reflection framework |
| Result Processing | ✅ Final SQL only | ✅ All SQL executions processed |
| Scoring System | ✅ Traditional 4-phase scoring | ✅ Traditional + enhanced metrics |

## 🤝 Contributing

To contribute to the enhanced BIRD-Interact system:

1. **Test thoroughly**: Ensure both original and enhanced functionality work
2. **Maintain compatibility**: Keep traditional scoring system intact  
3. **Document changes**: Update this README with any new features
4. **Follow patterns**: Use existing code patterns for consistency
5. **Add tests**: Include tests for new functionality

### Code Style
- Follow existing Python conventions
- Add comprehensive docstrings
- Use type hints where helpful
- Include error handling and logging
- Write modular, reusable code

## 📄 License and Attribution

This enhanced version maintains the same license as the original BIRD-Interact project. 

**Original BIRD-Interact Team**: Database, evaluation framework, original conversation system
**Enhanced Version**: SQL execution tool, enhanced prompts, dual budget system, comprehensive metrics

---

🎉 **Ready to explore interactive database conversations with enhanced SQL capabilities!**

For questions, issues, or contributions, please refer to the original BIRD-Interact documentation and this enhanced README.