
# DEALWEAVER AI
## AI-Based Multi-Agent Buyer-Seller Negotiation System

### Project Overview
DEALWEAVER AI simulates buyer-seller negotiations using four agents:
1. Buyer Agent
2. Seller Agent
3. Mediator Agent
4. Negotiation Analyst Agent

### Member 1: Dataset, ML and Deep Learning

Dataset: Stanford NLP Craigslist Bargains

- Training messages: 26,316
- Validation messages: 2,996
- Intent classes: 9

### Models Developed

1. Logistic Regression with TF-IDF
2. Baseline BiLSTM using PyTorch
3. Improved BiLSTM using PyTorch

### Model Comparison

| Model | Accuracy | Macro F1 | Weighted F1 |
|---|---:|---:|---:|
| Logistic Regression | 71.16% | 65.75% | 71.50% |
| Baseline BiLSTM | 67.32% | 66.68% | 67.17% |
| Improved BiLSTM | 73.06% | 70.18% | 73.22% |

Selected model: Improved BiLSTM.

### Project Structure

- dataset/: Dataset documentation and processed data
- models/: Trained ML and DL models
- evaluation/: Metrics, reports and visualizations
- agents/: Negotiation agent implementations (integration stage)
- app/: Streamlit application (integration stage)

### Model Deliverables

- intent_model.joblib
- vectorizer.joblib
- bilstm_model.pth
- vocab.json
- label_mapping.json
- label_encoder.pkl

### Evaluation Deliverables

- evaluation_metrics.json
- classification_report.json
- confusion_matrix.csv
- model_comparison.csv
- training_history.json
- plots/

### Technology Stack

Python, Pandas, NumPy, Scikit-learn, PyTorch,
Matplotlib, Seaborn and Google Colab.

### Evaluation Note

The original test split contained no usable labelled
intent messages. Therefore, all reported performance
metrics are validation results, not independent test results.

The intent classifier predicts dialogue intent.
Price-limit validation and negotiation decisions are
handled separately by rule-based agent logic.

<<<<<<< HEAD
### Future Integration

The trained classifier will be integrated into the
Negotiation Analyst Agent and connected to the
Buyer, Seller and Mediator Agents.
=======
### Integration Status

The trained classifier is integrated into the Negotiation Analyst Agent. The Mediator, Analyst, Risk Analyzer and Gen AI response generator are connected through the negotiation support coordinator.

### Member 3: Mediator, Analyst, Risk Analyzer and Gen AI

#### Implemented Modules

1. **Mediator Agent** (`agents/mediator_agent.py`)
   - Checks whether buyer and seller price limits overlap.
   - Calculates a midpoint compromise suggestion.
   - Does not guarantee acceptance of the suggested price.

2. **Negotiation Analyst** (`agents/analyst_agent.py`)
   - Uses the trained Improved BiLSTM intent predictor.
   - Predicts negotiation intent and confidence score.
   - Provides interpretations and warnings.

3. **Risk Analyzer** (`core/risk_analyzer.py`)
   - Detects offers outside acceptable price limits.
   - Detects repeated rejections and stalled price movement.
   - Identifies situations with no feasible price overlap.

4. **Gen AI Response Generator** (`genai/response_generator.py`)
   - Uses Ollama with the `llama3.2:3b` model.
   - Generates polite negotiation responses.
   - Validates generated responses against price and acceptance restrictions.
   - Uses predefined fallback responses if Ollama is unavailable or output is rejected.

5. **Integration Coordinator** (`core/negotiation_support.py`)
   - Connects the Mediator, Analyst, Risk Analyzer and Gen AI modules.
   - Provides a structured result for application integration.
   - Does not include the exact buyer maximum or seller minimum in its returned result.

#### Running the Modules

Run commands from the project root:

```powershell
python -m agents.mediator_agent
python -m agents.analyst_agent
python -m core.risk_analyzer
python -m genai.response_generator
python -m core.negotiation_support
```

Ollama must be installed and running with the `llama3.2:3b` model for local LLM response generation. The response generator provides a fallback when Ollama is unavailable.

#### Running Tests

Run the complete test suite:

```powershell
python -m pytest tests/ -v
```

Latest local test result: **65 passed, 1 warning**.

The warning is a pytest compatibility deprecation warning from the installed AnyIO plugin.

The integration coordinator connects Member 3's support modules. The automated Buyer-Seller negotiation workflow remains implemented separately.

### Updated Integration Status

The trained intent classifier is integrated into the Negotiation Analyst Agent. The Mediator, Analyst, Risk Analyzer and Gen AI response generator are connected through the negotiation support coordinator.
>>>>>>> 9d24adc6876cbad571ff45181f96e6262ab7fa09
