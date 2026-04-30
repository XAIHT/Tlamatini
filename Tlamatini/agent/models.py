from django.db import models
from django.contrib.auth.models import User

class AgentMessage(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    conversation_user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='agent_messages', null=True)
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


class ChatAgentRun(models.Model):
    runId = models.CharField(primary_key=True, max_length=64)
    toolDescription = models.CharField(max_length=200)
    templateAgentDir = models.CharField(max_length=200)
    runtimeDir = models.CharField(max_length=1000)
    logPath = models.CharField(max_length=1000)
    requestText = models.TextField(blank=True)
    pid = models.IntegerField(null=True, blank=True)
    status = models.CharField(max_length=32, default='created')
    exitCode = models.IntegerField(null=True, blank=True)
    startedAt = models.DateTimeField(auto_now_add=True)
    finishedAt = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f'{self.toolDescription} [{self.runId}] {self.status}'

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


# ── ACPX models ────────────────────────────────────────────────────────
class AcpAgent(models.Model):
    """
    Mirror of the ACPX agent registry. One row per registered agent_id
    (claude / cursor / codex / qwen / etc.). The `command` is the executable
    string used at spawn time. `healthy` is the most recent probe result.
    """
    agent_id      = models.CharField(max_length=64, unique=True)
    command       = models.CharField(max_length=512)
    description   = models.CharField(max_length=500, blank=True, default="")
    enabled       = models.BooleanField(default=True)
    healthy       = models.BooleanField(default=False)
    last_probe_at = models.DateTimeField(null=True, blank=True)
    notes         = models.TextField(blank=True, default="")

    class Meta:
        verbose_name = "ACP Agent"
        verbose_name_plural = "ACP Agents"

    def __str__(self):
        return f"{self.agent_id} ({'healthy' if self.healthy else 'unhealthy'})"


class Skill(models.Model):
    """
    Mirror of a SKILL.md package on disk. Disk is source of truth; this
    table is the toggle/UI/listing surface (same pattern as Mcp/Tool/Agent).
    """
    name             = models.CharField(max_length=128, unique=True)
    description      = models.TextField(blank=True, default="")
    runtime          = models.CharField(max_length=32, default="in-process")
    acpx_agent       = models.CharField(max_length=64, blank=True, default="")
    enabled          = models.BooleanField(default=True)
    frontmatter_json = models.TextField(blank=True, default="")
    body_sha256      = models.CharField(max_length=64, blank=True, default="")
    last_loaded_at   = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Skill"
        verbose_name_plural = "Skills"

    def __str__(self):
        return f"{self.name} [{self.runtime}]"


class AcpSession(models.Model):
    """One ACP child-process session, persisted across reconnects."""
    session_uuid    = models.CharField(max_length=64, unique=True)
    agent_id        = models.CharField(max_length=64)
    user            = models.ForeignKey(User, on_delete=models.CASCADE,
                                        null=True, blank=True,
                                        related_name="acp_sessions")
    cwd             = models.CharField(max_length=1024, blank=True, default="")
    state_path      = models.CharField(max_length=1024, blank=True, default="")
    transcript_path = models.CharField(max_length=1024, blank=True, default="")
    started_at      = models.DateTimeField(auto_now_add=True)
    ended_at        = models.DateTimeField(null=True, blank=True)
    ok              = models.BooleanField(null=True, blank=True)
    pid             = models.IntegerField(null=True, blank=True)
    label           = models.CharField(max_length=200, blank=True, default="")

    def __str__(self):
        return f"{self.agent_id}/{self.session_uuid[:8]}"


class SkillInvocation(models.Model):
    """One harness invocation of a skill. Audit trail."""
    skill_name     = models.CharField(max_length=128)
    user           = models.ForeignKey(User, on_delete=models.CASCADE,
                                       null=True, blank=True,
                                       related_name="skill_invocations")
    started_at     = models.DateTimeField(auto_now_add=True)
    finished_at    = models.DateTimeField(null=True, blank=True)
    ok             = models.BooleanField(null=True, blank=True)
    iterations     = models.IntegerField(null=True, blank=True)
    tokens         = models.IntegerField(null=True, blank=True)
    args_json      = models.TextField(blank=True, default="")
    output_json    = models.TextField(blank=True, default="")
    audit_path     = models.CharField(max_length=1024, blank=True, default="")
    failure_reason = models.CharField(max_length=64, blank=True, default="")
    acp_session    = models.ForeignKey(AcpSession, null=True, blank=True,
                                        on_delete=models.SET_NULL,
                                        related_name="skill_invocations")

    def __str__(self):
        return f"{self.skill_name} @ {self.started_at}"
