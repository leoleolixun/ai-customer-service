import argparse
import asyncio
import hashlib
import json
import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import select

from app.core.database import async_session_factory, engine
from app.core.security import generate_api_credential, hash_api_secret, hash_password
from app.core.storage import get_object_storage
from app.domains.applications.models import ApiCredential, Application
from app.domains.identities.models import StaffUser, TenantMembership, TenantRole
from app.domains.knowledge.models import (
    DocumentStatus,
    IngestionJob,
    IngestionStatus,
    KnowledgeBase,
    KnowledgeBaseBinding,
    KnowledgeChunk,
    KnowledgeDocument,
)
from app.domains.knowledge.parsing import lexicalize
from app.domains.model_gateway.models import (
    AIModelConfig,
    AIProviderAccount,
    ApplicationModelBinding,
    ModelPurpose,
    ModelStatus,
    ProviderKind,
    ProviderScope,
    ProviderStatus,
)
from app.domains.tenants.models import Tenant
from app.providers.llm.fake import FakeEmbeddingProvider
from scripts.password_input import read_password


@dataclass(frozen=True, slots=True)
class DemoDefinition:
    slug: str
    name: str
    admin_email: str
    applications: tuple[str, ...]


DEMOS = (
    DemoDefinition(
        slug="demo-retail",
        name="Demo Retail",
        admin_email="admin@demo-retail.example",
        applications=("storefront-web", "storefront-widget"),
    ),
    DemoDefinition(
        slug="demo-saas",
        name="Demo SaaS",
        admin_email="admin@demo-saas.example",
        applications=("help-center-web", "in-product-widget"),
    ),
)


def load_sources(tenant_slug: str) -> list[dict[str, Any]]:
    path = Path(__file__).resolve().parents[1] / "eval" / "knowledge_sources_v1.jsonl"
    return [
        record
        for line in path.read_text(encoding="utf-8").splitlines()
        if (record := json.loads(line))["tenant_id"] == tenant_slug
    ]


async def seed_demo(definition: DemoDefinition, password: str) -> dict[str, str]:
    storage = get_object_storage()
    async with async_session_factory() as session:
        existing = await session.scalar(select(Tenant).where(Tenant.slug == definition.slug))
        if existing is not None:
            return {"tenant": definition.slug, "status": "already_exists"}

        tenant = Tenant(name=definition.name, slug=definition.slug)
        admin = StaffUser(
            email=definition.admin_email,
            display_name=f"{definition.name} Admin",
            password_hash=hash_password(password),
        )
        session.add_all([tenant, admin])
        await session.flush()
        session.add(
            TenantMembership(
                tenant_id=tenant.id,
                staff_user_id=admin.id,
                role=TenantRole.TENANT_ADMIN,
            )
        )

        applications = [
            Application(
                tenant_id=tenant.id,
                name=name,
                public_key=f"app_{secrets.token_hex(16)}",
                allowed_origins=["http://localhost:5174", "http://localhost:8081"],
                rate_limit_per_minute=60,
            )
            for name in definition.applications
        ]
        provider = AIProviderAccount(
            tenant_id=tenant.id,
            scope=ProviderScope.TENANT,
            name="Deterministic demo provider",
            kind=ProviderKind.FAKE,
            status=ProviderStatus.READY,
        )
        session.add_all([*applications, provider])
        await session.flush()

        chat_model = AIModelConfig(
            tenant_id=tenant.id,
            provider_account_id=provider.id,
            name="Demo chat",
            model_name="fake-chat",
            purpose=ModelPurpose.CHAT,
            status=ModelStatus.ACTIVE,
        )
        embedding_model = AIModelConfig(
            tenant_id=tenant.id,
            provider_account_id=provider.id,
            name="Demo embedding",
            model_name="fake-embedding",
            purpose=ModelPurpose.EMBEDDING,
            embedding_dimension=32,
            status=ModelStatus.ACTIVE,
        )
        session.add_all([chat_model, embedding_model])
        await session.flush()
        session.add_all(
            [
                ApplicationModelBinding(
                    tenant_id=tenant.id,
                    application_id=application.id,
                    model_config_id=chat_model.id,
                    purpose=ModelPurpose.CHAT,
                )
                for application in applications
            ]
        )

        knowledge_base = KnowledgeBase(
            tenant_id=tenant.id,
            name="V1 evaluation corpus",
            description=f"Fixed neutral V1 corpus for {definition.name}",
            embedding_model_config_id=embedding_model.id,
            embedding_model_name=embedding_model.model_name,
            embedding_dimension=32,
            embedding_version="v1",
        )
        session.add(knowledge_base)
        await session.flush()
        session.add_all(
            [
                KnowledgeBaseBinding(
                    tenant_id=tenant.id,
                    application_id=application.id,
                    knowledge_base_id=knowledge_base.id,
                )
                for application in applications
            ]
        )

        for source in load_sources(definition.slug):
            source_id = str(source["source_id"])
            source_title = str(source["title"])
            source_content = str(source["content"])
            content = source_content.encode()
            object_key = (
                f"tenants/{tenant.id}/knowledge/{knowledge_base.id}/documents/"
                f"seed/{source_id.replace('/', '-')}.md"
            )
            document = KnowledgeDocument(
                tenant_id=tenant.id,
                knowledge_base_id=knowledge_base.id,
                title=source_title,
                source_filename=f"{source_id.replace('/', '-')}.md",
                source_url=f"https://{definition.slug}.example.com/{source_id}",
                mime_type="text/markdown",
                byte_size=len(content),
                object_key=object_key,
                content_hash=hashlib.sha256(content).hexdigest(),
                status=DocumentStatus.READY,
            )
            session.add(document)
            await session.flush()
            indexed_content = f"{source_title}\n{source_content}"
            lexical_text = lexicalize(indexed_content)
            embedding = await FakeEmbeddingProvider().embed(
                texts=[indexed_content], model="fake-embedding", dimensions=32
            )
            session.add_all(
                [
                    IngestionJob(
                        tenant_id=tenant.id,
                        knowledge_base_id=knowledge_base.id,
                        document_id=document.id,
                        status=IngestionStatus.COMPLETED,
                        stage="published",
                        attempts=1,
                    ),
                    KnowledgeChunk(
                        tenant_id=tenant.id,
                        knowledge_base_id=knowledge_base.id,
                        document_id=document.id,
                        document_version=1,
                        chunk_index=0,
                        content=source_content,
                        heading_path=[source_title],
                        source_locator=document.source_url or document.source_filename,
                        lexical_text=lexical_text,
                        lexical_vector=lexical_text,
                        content_hash=hashlib.sha256(content).hexdigest(),
                        embedding=embedding[0],
                        embedding_model="fake-embedding",
                        embedding_version="v1",
                        embedding_dimension=32,
                        chunking_version="v1",
                    ),
                ]
            )
            await storage.put(object_key, content, document.mime_type)

        result = {
            "tenant": definition.slug,
            "status": "created",
            "admin_email": definition.admin_email,
        }
        for application in applications:
            key_prefix, secret, api_key = generate_api_credential()
            session.add(
                ApiCredential(
                    tenant_id=tenant.id,
                    application_id=application.id,
                    key_prefix=key_prefix,
                    secret_hash=hash_api_secret(secret),
                    scopes=["customer_token:create"],
                )
            )
            result[f"application_{application.name}"] = str(application.id)
            result[f"api_key_{application.name}"] = api_key
        await session.commit()
        return result


async def run(password: str) -> None:
    for definition in DEMOS:
        result = await seed_demo(definition, password)
        print(result)
    await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Create two isolated neutral V1 demo tenants.")
    parser.add_argument(
        "--password-stdin",
        action="store_true",
        help="Read one demo administrator password line from standard input instead of prompting.",
    )
    args = parser.parse_args()
    password = read_password(from_stdin=args.password_stdin, prompt="Demo administrator password: ")
    if len(password) < 12:
        parser.error("password must contain at least 12 characters")
    asyncio.run(run(password))


if __name__ == "__main__":
    main()
