from app.core.config import settings
from app.models.records import AppPreference
from app.schemas.contracts import Preferences


def preferences(db):
    row = db.get(AppPreference, 'default')
    return Preferences(**(row.values if row else {'model': settings.openai_model})).model_dump()
