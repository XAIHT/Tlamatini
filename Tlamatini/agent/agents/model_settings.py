"""Shared model registry for the Models dialog and standalone workflow agents.

Created by Angela López Mendoza · @angelahack1 — Tlamatini.
Only model/engine/voice settings live here; credentials remain in their existing
configuration. ``@config`` in an agent YAML follows the saved global choice.
"""
import copy
import json
import logging
import os
from pathlib import Path


INHERIT = '@config'
FIELDS = []


def _field(key, label, group, default, *, agent='', path='', kind='ollama',
           optional=False, choices=(), fallback='', help_text=''):
    FIELDS.append(dict(key=key, label=label, group=group, default=default,
                       agent=agent, path=path, kind=kind, optional=optional,
                       choices=list(choices), fallback=fallback, help=help_text))


for key, label, default in (
    ('embeding-model', 'Embedding / memory', 'Nomic-Embed-Text:latest'),
    ('chained-model', 'Chained reasoning', 'glm-5.3:cloud'),
    ('access_aimed_prompt_model', 'Access aimed prompts', 'glm-5.3:cloud'),
    ('unified_agent_model', 'Unified / Multi-Turn', 'glm-5.3:cloud'),
    ('mcp_files_search_model', 'MCP file search', 'glm-5.3:cloud'),
    ('internet_classifier_model', 'Internet classifier', 'glm-5.3:cloud'),
    ('web_summarizer_model', 'Web search summaries', 'glm-5.3:cloud'),
):
    _field(key, label, 'Core', default)

for agent, prefix, first, second in (
    ('image_interpreter', 'image', 'jcyhsiao/qwen3.5cloud:latest', 'gemma4:cloud'),
    ('video_analyzer', 'video', 'gemma4:cloud', 'jcyhsiao/qwen3.5cloud:latest'),
):
    for suffix, label, path, default in (
        ('interpreter_model', 'interpreter 1', 'interpreter_model_1', first),
        ('interpreter_model_2', 'interpreter 2', 'interpreter_model_2', second),
        ('merging_model', 'merger', 'merging_model', 'glm-5.3:cloud'),
    ):
        _field(f'{prefix}_{suffix}', f'{prefix.title()} {label}', 'Vision', default,
               agent=agent, path=path, help_text='Vision-capable model required.' if 'interpreter' in suffix
               else 'Text model that combines both interpretations.')
_field('claude_image_model', 'Claude image analysis', 'Vision', 'claude-opus-4-5-20251101',
       kind='provider', help_text='Anthropic model ID; requires your existing Claude API credentials.')

_field('talker_model', 'Talker · speech generation', 'Speech', 'legraphista/Orpheus:3b-ft-q8',
       agent='talker', path='model', help_text='Orpheus-compatible audio-token model; ordinary chat models cannot speak.')
_field('talker_voice', 'Talker · voice', 'Speech', 'tara', agent='talker', path='voice',
       kind='choice', choices=('tara', 'leah', 'jess', 'mia', 'zoe'), help_text='Use a supported female Orpheus voice.')
_field('whisperer_engine', 'Whisperer · recognition engine', 'Speech', 'faster-whisper',
       agent='whisperer', path='engine', kind='choice', choices=('faster-whisper', 'cloud-groq', 'cloud-openai'))
_field('whisperer_model', 'Whisperer · local speech model', 'Speech', 'base',
       agent='whisperer', path='model', kind='local', help_text='Whisper size, Hugging Face model ID or local model directory.')
_field('whisperer_cloud_model', 'Whisperer · cloud speech model', 'Speech', '', optional=True,
       agent='whisperer', path='cloud_model', kind='provider', help_text='Optional. Empty uses the selected speech provider’s default; credentials stay in the agent.')
_field('whisperer_cleanup_model', 'Whisperer · transcript cleanup', 'Speech', 'glm-5.3:cloud',
       agent='whisperer', path='cleanup_model', fallback='unified_agent_model',
       help_text='Ollama post-processing only; this does not enable cleanup or send microphone audio to Ollama.')
_field('video_transcription_model', 'Video-Analyzer · audio tracks', 'Speech', 'base',
       agent='video_analyzer', path='transcription.model', kind='local', help_text='Local faster-whisper model for video audio tracks.')

for agent, label, group, path in (
    ('crawler', 'Crawler', 'Workflows', 'llm.model'),
    ('flowcreator', 'FlowCreator', 'Workflows', 'llm.model'),
    ('flowhypervisor', 'FlowHypervisor', 'Workflows', 'llm.model'),
    ('prompter', 'Prompter', 'Workflows', 'llm.model'),
    ('pser', 'PSer', 'Workflows', 'llm.model'),
    ('reviewer', 'Reviewer', 'Workflows', 'llm.model'),
    ('file_interpreter', 'File-Interpreter', 'Documents', 'llm.model'),
    ('summarizer', 'Summarizer', 'Documents', 'llm.model'),
    ('pdfer', 'PDFer · design and polish', 'Documents', 'ollama_model'),
    ('pptxer', 'PPTXer · design and polish', 'Documents', 'ollama_model'),
    ('latexer', 'LaTeXer · repair', 'Documents', 'repair_model'),
    ('monitor_log', 'Monitor-Log', 'Monitoring & messaging', 'llm.model'),
    ('monitor_netstat', 'Monitor-Netstat', 'Monitoring & messaging', 'llm.model'),
    ('notifier', 'Notifier', 'Monitoring & messaging', 'llm.model'),
    ('recmailer', 'RecMailer', 'Monitoring & messaging', 'llm.model'),
    ('instant_messaging_doctor', 'Instant-Messaging-Doctor', 'Monitoring & messaging', 'ollama.model'),
    ('teletlamatini', 'TeleTlamatini · completeness check', 'Monitoring & messaging', 'completeness_check.model'),
):
    _field(f'{agent}_model', label, group, 'glm-5.3:cloud', agent=agent, path=path,
           fallback='unified_agent_model', optional=agent == 'latexer',
           help_text='Optional. Empty disables model repair.' if agent == 'latexer' else '')

BY_KEY = {field['key']: field for field in FIELDS}
AGENTS = frozenset(field['agent'] for field in FIELDS if field['agent'])


def values_for_dialog(config):
    values = {}
    for field in FIELDS:
        value = config.get(field['key'])
        if value is None or (not str(value).strip() and not field['optional']):
            value = config.get(field['fallback']) if field['fallback'] else None
            if value is None or not str(value).strip():
                value = field['default']
        values[field['key']] = str(value).strip()
    return values


def validate_values(payload):
    errors, updates = {}, {}
    for field in FIELDS:
        key = field['key']
        value = payload.get(key)
        if not isinstance(value, str):
            errors[key] = 'must be a string' if key in payload else 'missing'
            continue
        value = value.strip()
        if not value and not field['optional']:
            errors[key] = 'must not be empty'
        elif value == INHERIT:
            errors[key] = 'select a model here; @config is only for per-agent overrides'
        elif field['choices'] and value not in field['choices']:
            errors[key] = 'choose one of: ' + ', '.join(field['choices'])
        elif len(value) > 512 or any(ord(char) < 32 for char in value):
            errors[key] = 'must be a single value of at most 512 characters'
        else:
            updates[key] = value
    return updates, errors


def read_app_config(agent_file=None):
    explicit = os.environ.get('CONFIG_PATH', '').strip()
    root = next((p for p in Path(agent_file or __file__).resolve().parents if p.name == 'agents'), None)
    path = Path(explicit) if explicit else (root.parent / 'config.json' if root else None)
    if not path or not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding='utf-8-sig'))
        if not isinstance(data, dict):
            raise ValueError('expected a JSON object')
        return data
    except (OSError, ValueError) as exc:
        logging.warning('MODELS: could not read %s (%s); using initial defaults', path, type(exc).__name__)
        return {}


def resolve_agent_models(agent, config, app_config=None, *, agent_file=None, force=False):
    """Resolve only registered fields; explicit overrides and empty disable values win."""
    if not isinstance(config, dict):
        return config
    result = copy.deepcopy(config)
    values = values_for_dialog(read_app_config(agent_file) if app_config is None else app_config)
    for field in FIELDS:
        if field['agent'] != agent:
            continue
        parts = field['path'].split('.')
        target = result
        for part in parts[:-1]:
            if part not in target:
                target[part] = {}
            if not isinstance(target[part], dict):
                break
            target = target[part]
        else:
            key = parts[-1]
            if force or key not in target or target[key] == INHERIT:
                target[key] = values[field['key']]
    return result
