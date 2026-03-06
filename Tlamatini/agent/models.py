from django.db import models
from django.contrib.auth.models import User

class AgentMessage(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    message = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'{self.user.username}: {self.message}'

class LLMProgram(models.Model):
    idProgram = models.IntegerField(primary_key=True)
    programName = models.CharField(max_length=200)
    programLanguage = models.CharField(max_length=200)
    timestamp = models.DateTimeField(auto_now_add=True)
    programContent = models.TextField()

    def __str__(self):
        return f'{self.programName}'

class LLMSnippet(models.Model):
    idSnippet = models.IntegerField(primary_key=True)
    snippetName = models.CharField(max_length=200)
    snippetLanguage = models.CharField(max_length=200)
    timestamp = models.DateTimeField(auto_now_add=True)
    snippetContent = models.TextField()

    def __str__(self):
        return f'{self.snippetName}'

class Prompt(models.Model):
    idPrompt = models.IntegerField(primary_key=True)
    promptName = models.CharField(max_length=200)
    promptContent = models.TextField()

    def __str__(self):
        return f'{self.promptName}'

class Omission(models.Model):
    idOmission = models.IntegerField(primary_key=True)
    omissionName = models.CharField(max_length=200)
    omissionContent = models.TextField()

    def __str__(self):
        return f'{self.omissionName}'

class ContextCache(models.Model):
    query_hash = models.CharField(max_length=64, unique=True)  # SHA1 hash
    context_blob = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'ContextCache for query_hash: {self.query_hash[:16]}...'

class Mcp(models.Model):
    idMcp = models.IntegerField(primary_key=True)
    mcpName = models.CharField(max_length=200)
    mcpDescription = models.CharField(max_length=500)
    mcpContent = models.TextField()

    def __str__(self):
        return f'{self.mcpName}'

class Tool(models.Model):
    idTool = models.IntegerField(primary_key=True)
    toolName = models.CharField(max_length=200)
    toolDescription = models.CharField(max_length=500)
    toolContent = models.TextField()

    def __str__(self):
        return f'{self.toolName}'

class Agent(models.Model):
    idAgent = models.IntegerField(primary_key=True)
    agentName = models.CharField(max_length=200)
    agentDescription = models.CharField(max_length=500)
    agentContent = models.TextField()

    def __str__(self):
        return f'{self.agentName}'

class AgentProcess(models.Model):
    idAgentProcess = models.IntegerField(primary_key=True)
    agentProcessDescription = models.CharField(max_length=500)
    agentProcessPid = models.IntegerField()

    def __str__(self):
        return f'{self.agentProcessDescription} {self.agentProcessPid}'

class Asset(models.Model):
    idAsset = models.IntegerField(primary_key=True)
    assetName = models.CharField(max_length=200)
    assetDescription = models.CharField(max_length=500)
    assetContent = models.TextField()

    def __str__(self):
        return f'{self.assetName} {self.assetDescription}'


class SessionState(models.Model):
    """
    Persists user session state across browser reconnections.
    Single-user app: One context shared across all tabs for the same user.
    Expires after 24 hours of inactivity.
    """
    user = models.OneToOneField(User, on_delete=models.CASCADE, primary_key=True)
    context_path = models.CharField(max_length=1000, blank=True, null=True)
    context_type = models.CharField(max_length=20, blank=True, null=True)  # 'directory' | 'file' | None
    context_filename = models.CharField(max_length=500, blank=True, null=True)
    last_active = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'{self.user.username}: {self.context_type} - {self.context_path}'
    
    def is_expired(self):
        """Check if session state is older than 24 hours."""
        from django.utils import timezone
        from datetime import timedelta
        return timezone.now() - self.last_active > timedelta(hours=24)
