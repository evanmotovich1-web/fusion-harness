"""Gemini via the official signed-in Antigravity CLI, not ACP or Cloud Code."""
from providers import register_provider
from providers.base import ProviderProfile


class GeminiLoginProfile(ProviderProfile):
    def create_client(self, **client_kwargs):
        from .client import GeminiLoginClient
        return GeminiLoginClient(**client_kwargs)

    def build_api_kwargs_extras(self, *, reasoning_config=None, **context):
        effort = (reasoning_config or {}).get('effort')
        if effort is None:
            return {}, {}
        # Host 'max' means the highest effort this model supports, not an
        # unsupported literal CLI value. Preserve the user's global preference.
        supported = {
            'none':'low', 'minimal':'low', 'low':'low', 'medium':'medium',
            'high':'high', 'xhigh':'high', 'max':'high', 'ultra':'high',
        }
        if effort not in supported:
            raise ValueError('Unsupported Hermes reasoning effort for Gemini login')
        return {}, {'reasoning_effort': supported[effort]}


gemini_login = GeminiLoginProfile(
    name='gemini-login',
    aliases=('google-gemini-cli', 'gemini-oauth'),
    display_name='Gemini Login (Antigravity CLI)',
    description='Official signed-in CLI inference; Hermes owns tool execution. Text only.',
    auth_type='external_process',
    api_mode='chat_completions',
    env_vars=(),
    base_url='gemini-login://antigravity',
    process_command='/Applications/Gemini.app/Contents/Helpers/agy',
    process_args=(),
    process_command_env_vars=('GEMINI_LOGIN_CLI',),
    supports_health_check=False,
    supports_model_listing=False,
    supports_vision=False,
    supports_vision_tool_messages=False,
    fallback_models=('gemini-4-argon', 'gemini-3.8-flash'),
    model_aliases={'argon':'gemini-4-argon','flash':'gemini-3.8-flash'},
    model_capabilities={
        model: {'tool_call':True, 'reasoning':True, 'attachment':False, 'modalities':{'input':['text'],'output':['text']}}
        for model in ('gemini-4-argon', 'gemini-3.8-flash')
    },
)
register_provider(gemini_login)
