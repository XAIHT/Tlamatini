import os
import sys
import json
from typing import Tuple, Dict, Any

def load_config_and_prompt(application_path: str) -> Tuple[Dict[str, Any], str, str]:
    config_file_path = os.path.join(application_path, 'config.json')
    prompt_file_path = os.path.join(application_path, 'prompt.pmt')

    for path, name in [(config_file_path, 'config.json'), (prompt_file_path, 'prompt.pmt')]:
        if not os.path.exists(path):
            print(f"--- Critical Error: Required configuration file '{name}' not found in application directory.")
            print(f"--- Expected location: {path}")
            print("--- Please ensure all required configuration files are present before running the application.")
            sys.exit(1)

    with open(config_file_path, 'r', encoding='utf-8') as f:
        config = json.load(f)
    with open(prompt_file_path, 'r', encoding='utf-8') as f:
        prompt_template = f.read()

    return config, prompt_template, config_file_path
