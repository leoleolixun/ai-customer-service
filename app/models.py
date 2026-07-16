"""Import all SQLAlchemy models so migrations can discover metadata."""

from app.domains.applications.models import ApiCredential, Application
from app.domains.audit.models import AuditLog
from app.domains.conversations.models import Conversation, ConversationFeedback, EndUser, Message
from app.domains.handoffs.models import HandoffRequest
from app.domains.identities.models import StaffUser, TenantMembership
from app.domains.knowledge.models import (
    Citation,
    IngestionJob,
    KnowledgeBase,
    KnowledgeBaseBinding,
    KnowledgeChunk,
    KnowledgeDocument,
)
from app.domains.model_gateway.models import (
    AIModelConfig,
    AIProviderAccount,
    ApplicationModelBinding,
)
from app.domains.tenants.models import Tenant
from app.domains.usage.models import AIUsageRecord

__all__ = [
    "AIModelConfig",
    "AIProviderAccount",
    "AIUsageRecord",
    "ApiCredential",
    "Application",
    "ApplicationModelBinding",
    "AuditLog",
    "Citation",
    "Conversation",
    "ConversationFeedback",
    "EndUser",
    "HandoffRequest",
    "IngestionJob",
    "KnowledgeBase",
    "KnowledgeBaseBinding",
    "KnowledgeChunk",
    "KnowledgeDocument",
    "Message",
    "StaffUser",
    "Tenant",
    "TenantMembership",
]
