import logging
from typing import Any, Optional, Union

# Pydantic data model for the LLM class
import litellm
from litellm.types.utils import Choices, ModelResponse, Usage

from dsp.modules.schemas import (
    ChatMessage,
    DSPyModelResponse,
    LLMModelParams,
)


# TODO: should be moved to a centralised logging module
logger = logging.getLogger(__name__)
logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(name)s -   %(message)s",
    datefmt="%m/%d/%Y %H:%M:%S",
    level=logging.INFO,  # TODO: figure out how to make this customizable
)

# Only for testing
litellm.set_verbose = True


class LLM:
    llm_params: LLMModelParams
    history: list[dict[str, Any]] = []

    def __init__(
        self,
        llm_params: LLMModelParams,
    ):
        super().__init__()
        self.llm_params = llm_params

    def basic_request(self, prompt: str, **kwargs) -> ModelResponse:
        self.update_messages_with_prompt(prompt)

        response: ModelResponse = litellm.completion(
            **self.llm_params.to_json(), **kwargs
        )

        self.history.append(
            {
                "prompt": prompt,
                "response": response.to_dict(),
                "raw_kwargs": kwargs,
                "kwargs": self.llm_params.to_json(ignore_sensitive=True),
            }
        )

        return response

    # TODO: enable caching
    def request(self, prompt: str, **kwargs) -> ModelResponse:
        return self.basic_request(prompt, **kwargs)

    def log_usage(self, response: ModelResponse):
        """Log the total tokens from the OpenAI API response."""
        usage_data: Usage = response.get("usage")
        if usage_data:
            total_tokens = usage_data.get("total_tokens")
            logger.debug(f"OpenAI Response Token Usage: {total_tokens}")

    def filter_only_completed(self, choices: list[Choices]) -> list[Choices]:
        """Filters out incomplete completions by checking if the finish_reason is not 'length'.
        Returns the filtered list of choices only if there are any, otherwise returns the original list.
        """
        filtered_choices = [c for c in choices if c.finish_reason != "length"]
        if len(filtered_choices):
            return filtered_choices
        return choices

    def get_text_from_choice(self, choice: Choices) -> str:
        """Returns the text from the choice."""
        return choice.message.content

    def transform_choices_to_dspy_model_response(
        self, choices: list[Choices], add_logprobs: bool = False
    ) -> list[DSPyModelResponse]:
        """Transforms the choices to DSPyModelResponse."""
        dspy_choices: list[DSPyModelResponse] = []
        for choice in choices:
            # TODO: ideally we should return the choice object itself, which contains more information.
            dspy_choices.append(
                {
                    "text": self.get_text_from_choice(choice),
                }
            )
            if add_logprobs:
                # TODO: check if we can strong type this.
                dspy_choices[-1]["logprobs"] = (
                    choice.logprobs if choice.logprobs else None
                )

        return dspy_choices

    def update_messages_with_prompt(self, prompt: str):
        """Updates the messages with the prompt."""
        self.llm_params.prompt = prompt
        if not self.llm_params.messages:
            self.llm_params.messages = []
        self.llm_params.messages.append(
            ChatMessage(role="user", content=prompt)
        )

    def __call__(
        self,
        prompt: str,
        only_completed: bool = True,
        **kwargs,
    ) -> list[DSPyModelResponse]:
        """Retrieves completions from LLM."""

        self.llm_params.only_completed = only_completed

        assert self.llm_params.only_completed, "for now"
        assert self.llm_params.return_sorted is False, "for now"

        # TODO: I don't really like that the prompt is string instead of messages. We should refactor this.
        response = self.request(prompt, **kwargs)

        self.log_usage(response)

        choices = (
            self.filter_only_completed(response.choices)
            if self.llm_params.only_completed
            else response.choices
        )

        choices = self.transform_choices_to_dspy_model_response(
            choices, self.llm_params.logprobs
        )

        return choices