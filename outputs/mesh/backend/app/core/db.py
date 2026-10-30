from collections.abc import Generator

from fastapi import HTTPException
from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings


class Base(DeclarativeBase):
    pass


engine = create_engine(settings().database_url, pool_pre_ping=True)
SessionFactory = sessionmaker(engine, expire_on_commit=False)


def session() -> Generator[Session, None, None]:
    with SessionFactory() as db:
        try:
            assert_runtime_role(db)
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise


def assert_runtime_role(db: Session) -> None:
    if db.get_bind().dialect.name == "postgresql":
        unsafe = db.scalar(
            text("""SELECT rolsuper OR rolbypassrls OR EXISTS(
            SELECT 1 FROM pg_tables WHERE schemaname='public'
            AND tablename='organizations' AND pg_has_role(current_user, tableowner, 'MEMBER'))
            OR has_schema_privilege(current_user, 'public', 'CREATE')
            FROM pg_roles WHERE rolname=current_user""")
        )
        if unsafe:
            raise HTTPException(503, "Runtime database role is overprivileged")


def tenant_context(db: Session, organization_id: str, user_id: str) -> None:
    if db.bind is not None and db.bind.dialect.name == "postgresql":
        db.execute(
            text("SELECT set_config('mesh.organization_id', :org, true)"), {"org": organization_id}
        )
        db.execute(text("SELECT set_config('mesh.user_id', :uid, true)"), {"uid": user_id})
