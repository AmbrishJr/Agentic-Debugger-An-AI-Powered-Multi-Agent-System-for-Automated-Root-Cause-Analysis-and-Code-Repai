from app.core.config import settings
from app.models.records import AppPreference
from app.schemas.contracts import Preferences


def preferences(db):
    row = db.get(AppPreference, 'default')
    values = dict(row.values) if row else {}
    # Existing pre-provider preferences inherit the operator's selected provider.
    if 'provider' not in values:
        values['provider'] = settings.llm_provider
        if values['provider'] == 'gemini':
            values['model'] = settings.gemini_model
    values.setdefault('model', settings.gemini_model if values['provider'] == 'gemini' else settings.openai_model)
    return Preferences(**values).model_dump()
