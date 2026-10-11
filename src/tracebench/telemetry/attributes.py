"""Names of span attributes, following the OpenTelemetry GenAI semantic conventions.

The GenAI conventions are still marked "Development", so names may change.
Keeping them all here means a rename is a one-file change.
"""

OPERATION_NAME = "gen_ai.operation.name"
PROVIDER_NAME = "gen_ai.provider.name"
AGENT_NAME = "gen_ai.agent.name"

REQUEST_MODEL = "gen_ai.request.model"
REQUEST_TEMPERATURE = "gen_ai.request.temperature"
RESPONSE_MODEL = "gen_ai.response.model"
RESPONSE_FINISH_REASONS = "gen_ai.response.finish_reasons"

USAGE_INPUT_TOKENS = "gen_ai.usage.input_tokens"
USAGE_OUTPUT_TOKENS = "gen_ai.usage.output_tokens"

INPUT_MESSAGES = "gen_ai.input.messages"
OUTPUT_MESSAGES = "gen_ai.output.messages"

TOOL_NAME = "gen_ai.tool.name"
TOOL_CALL_ID = "gen_ai.tool.call.id"
TOOL_CALL_ARGUMENTS = "gen_ai.tool.call.arguments"
TOOL_CALL_RESULT = "gen_ai.tool.call.result"

ERROR_TYPE = "error.type"

# Our own attribute, not part of the spec, so it uses the project's name as a prefix.
COST_USD = "tracebench.cost_usd"

# Attributes that hold conversation content (see decision 0011).
CONTENT_ATTRIBUTES = {INPUT_MESSAGES, OUTPUT_MESSAGES, TOOL_CALL_ARGUMENTS, TOOL_CALL_RESULT}