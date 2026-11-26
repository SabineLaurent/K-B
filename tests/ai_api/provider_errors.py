"""The answer of Azure to gpt-6.1-sol asked with the effort none (#710), its message given a mark:
a message may quote the input, so it is never kept."""

import json

MESSAGE_MARK = "message-mark-of-the-test"
UNSUPPORTED_EFFORT = json.dumps(
    {
        "error": {
            "message": "Unsupported value: 'reasoning_effort' does not support 'none'"
            f" with this model. {MESSAGE_MARK}",
            "type": "invalid_request_error",
            "param": "reasoning_effort",
            "code": "unsupported_value",
        }
    }
)
