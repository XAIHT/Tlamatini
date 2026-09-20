"""Append Video-Analyzer audio-track and summary examples to Media & Voice.

Created by Angela López Mendoza · @angelahack1 — Tlamatini.
"""
from django.db import migrations


PROMPTS = (
    (125, 35, 'transcription',
     'Transcribe every audio track of the selected video. Preserve timestamps and track indexes; '
     'return the transcript, detected languages, audio_status and artifact paths. Do not capture a microphone.'),
    (126, 37, 'summary',
     'Summarize the selected video using speech and timestamped visual evidence. Include an overview, '
     'chronology, readable on-screen text, key facts, demonstrated steps, decisions, action items and '
     'coverage limitations. Report missing audio or partial results honestly; link the saved report.'),
)


def add_prompts(apps, schema_editor):
    prompt = apps.get_model('agent', 'Prompt')
    for pid, rank, mode, task in PROMPTS:
        content = (
            f'Video-Analyzer — {mode}\n\n'
            '[[ VIDEO FILE — REQUIRED: path to an existing video ]]\n\n'
            'If VIDEO FILE is unfilled, ask for its path before running. Never invent a file.\n\n'
            f'{task}\nUse chat_agent_video_analyzer with analysis_type="{mode}", '
            'video_pathfilenames set to VIDEO FILE and audio_tracks="all". '
            'Use chat_agent_run_status/log to wait for completion and inspect the result. '
            'Do not use robotics verdict tokens for this task. '
            '\nPRE-FLIGHT: tick only Multi-Turn and Exec report. End with END-RESPONSE.'
        )
        prompt.objects.update_or_create(idPrompt=pid, defaults={
            'promptName': f'prompt-{pid}', 'promptContent': content,
            'category': 'media_voice', 'sort_rank': rank,
        })


def remove_prompts(apps, schema_editor):
    apps.get_model('agent', 'Prompt').objects.filter(idPrompt__in=[125, 126]).delete()


class Migration(migrations.Migration):
    dependencies = [('agent', '0206_qwen35_cloud_model_tag_rename')]
    operations = [migrations.RunPython(add_prompts, remove_prompts)]
