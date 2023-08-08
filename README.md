# Self-Service Analytics With Council

A demo that uses a Council Agent to generate and execute Python code for data analytics. Runnable as a notebook or as a Flask/JavaScript app with a UI.

There are two Controllers currently:
- src/data_analytics_agent/stock_price_analyst/controller.py
- src/data_analytics_agent/stock_price_analyst/council_controller.py

where `council_controller.py` is an attempt at generalizing the Controller originally developed for the demo so that it might become `LLMInstructController` in Council proper.

## Features

- Generate data analytics code for Pandas DataFrames
- Uses a controller to decide whether to write new code or edit existing code
- Controller interprets the context (chat history + controller state variables) and generates instructions for selected chains
- Python execution skill has an error-correction loop

## To Do

- Improve controller and code generation prompts (e.g. using few-shot prompts)

## Running the demo

- Create a new Python/conda environment
- Install dependencies using `pip install -r requirements.txt` (outdated - this should be much smaller)
- Set up a the Python sandbox
  - cd to `src/data_analytics_agent/stock_price_analyst`
  - `python -m venv code_sandbox`
  - `source code_sandbox/bin/activate`
  - `pip install pandas plotly`
- Run the notebook `src/data_analytics_agent/stock_price_analyst/analyst.ipynb` or `src/data_analytics_agent/stock_price_analyst/analyst_instruct_controller.ipynb`
  - Note: `analyst_instruct_controller.ipynb` is the notebook that uses the "generalized" controller.
- Run the Flask app `cd src/data_analytics_agent/flask-app && python app.py` and open the webpage `src/data_analytics_agent/flask-app/index.html`

