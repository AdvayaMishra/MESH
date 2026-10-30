from alembic import context
from app import models  # noqa: F401
from app.core.config import settings
from app.core.db import Base
from sqlalchemy import create_engine

target_metadata = Base.metadata

if context.is_offline_mode():
    context.configure(
        url=settings().database_url, target_metadata=target_metadata, literal_binds=True
    )
    with context.begin_transaction():
        context.run_migrations()
else:
    with create_engine(settings().database_url).connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
