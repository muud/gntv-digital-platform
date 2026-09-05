from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool
from alembic import context
from app.core.config import settings
from app.core.database import Base

from app.models import audit, auth_extra, user  # noqa: F401
from app.modules.chat import models as chat_models  # noqa: F401
from app.modules.cms import models as cms_models  # noqa: F401
from app.modules.catalog import models as catalog_models  # noqa: F401
from app.modules.editorial import models as editorial_models  # noqa: F401
from app.modules.distribution import models as distribution_models  # noqa: F401
from app.modules.monetization import models as monetization_models  # noqa: F401
from app.modules.streaming import models as streaming_models  # noqa: F401
from app.modules.sheeko_xariiro import models as sheeko_xariiro_models  # noqa: F401
from app.modules.cdn import models as cdn_models  # noqa: F401
from app.modules.partners import models as partner_models  # noqa: F401

target_metadata = Base.metadata

config = context.config
config.set_main_option("sqlalchemy.url", str(settings.DATABASE_URL))

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def run_migrations_offline() -> None:
    """Run migrations in offline mode."""
    url = settings.DATABASE_URL
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in online mode."""
    section = config.get_section(config.config_ini_section)
    if section is None:
        section = {}
    connectable = engine_from_config(
        dict(section),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
