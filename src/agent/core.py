"""
Agent Core
==========

The main agent class that orchestrates all operations.

The agent is the "brain" of the bot. It:
1. Receives user messages
2. Assembles context from memory and RAG
3. Sends requests to the LLM
4. Handles tool calls in a loop
5. Returns the final response

Agent Loop:
    User Message
         │
         ▼
    Assemble Context (memory + RAG)
         │
         ▼
    LLM Request with Tools
         │
         ▼
    ┌─── Has Tool Calls? ───┐
    │                       │
    Yes                     No
    │                       │
    ▼                       ▼
    Execute Tools      Return Response
    │
    ▼
    Add Results to Context
    │
    └──────────────────────┐
                           │
                    Loop until done

This pattern allows the agent to:
- Gather information from multiple sources
- Take multiple actions
- Think through complex tasks
"""

from typing import TYPE_CHECKING

from openai import AsyncOpenAI

from src.agent.context import ContextAssembler
from src.agent.tools_executor import ToolExecutor
from src.memory import MemoryManager
from src.utils.config import get_config
from src.utils.logger import Logger

if TYPE_CHECKING:
    from src.rag import RAGManager

logger = Logger("Agent")


class Agent:
    """
    The main agent that processes user requests.

    The agent coordinates:
    - Context assembly (memory, RAG, conversation)
    - LLM interactions
    - Tool execution
    - Response generation

    Example:
        agent = Agent(memory, rag, config)

        # Process a user message
        response = await agent.process(
            user_id="U123",
            message="Summarize #engineering from today",
            channel_id="D456",
            channel_type="dm"
        )

        print(response)  # The agent's response text
    """

    # Maximum tool execution iterations to prevent infinite loops
    MAX_TOOL_ITERATIONS = 10

    def __init__(
        self,
        memory: MemoryManager,
        rag: "RAGManager | None" = None
    ):
        """
        Initialize the agent.

        Args:
            memory: Memory manager for context
            rag: Optional RAG manager for semantic search
        """
        config = get_config()

        self.memory = memory
        self.rag = rag

        # Initialize OpenAI client
        self.openai = AsyncOpenAI(api_key=config.openai.api_key)
        self.model = config.openai.model

        # Initialize components
        self.context_assembler = ContextAssembler(memory, rag)
        self.tool_executor = ToolExecutor()

        logger.info(f"Agent initialized with model: {self.model}")

    async def process(
        self,
        user_id: str,
        message: str,
        channel_id: str,
        channel_type: str = "dm"
    ) -> str:
        """
        Process a user message and return a response.

        This is the main entry point for the agent. It:
        1. Assembles context
        2. Calls the LLM
        3. Executes any tool calls
        4. Returns the final response

        Args:
            user_id: The Slack user ID
            message: The user's message
            channel_id: The Slack channel/DM ID
            channel_type: "dm" for direct messages, "channel" for public

        Returns:
            The agent's response text
        """
        logger.info(f"Processing message from {user_id}: {message[:50]}...")

        try:
            # 1. Assemble context
            context = await self.context_assembler.assemble(
                user_id=user_id,
                user_message=message,
                channel_type=channel_type,
                include_rag=True
            )

            # 2. Initial LLM call
            messages = context.to_openai_messages()

            response = await self.openai.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=context.tools if context.tools else None,
                tool_choice="auto"
            )

            # 3. Tool execution loop
            iterations = 0
            while response.choices[0].message.tool_calls and iterations < self.MAX_TOOL_ITERATIONS:
                iterations += 1
                logger.debug(f"Tool iteration {iterations}")

                # Parse and execute tool calls
                tool_calls = self.tool_executor.parse_tool_calls(response)
                results = await self.tool_executor.execute_all(tool_calls)

                # Add assistant message with tool calls
                messages.append(response.choices[0].message.model_dump())

                # Add tool results
                for result in results:
                    messages.append(result.to_openai_message())

                # Continue the conversation
                response = await self.openai.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    tools=context.tools if context.tools else None,
                    tool_choice="auto"
                )

            if iterations >= self.MAX_TOOL_ITERATIONS:
                logger.warning("Reached max tool iterations")

            # 4. Extract the final response
            final_message = response.choices[0].message.content or ""

            # 5. Store the response in memory
            self.context_assembler.add_assistant_message(user_id, final_message)

            logger.info(f"Generated response ({len(final_message)} chars)")
            return final_message

        except Exception as e:
            logger.error("Error processing message", e)
            return f"I encountered an error: {str(e)}"

    async def process_with_streaming(
        self,
        user_id: str,
        message: str,
        channel_id: str,
        channel_type: str = "dm"
    ):
        """
        Process a message with streaming response.

        Yields response chunks as they're generated. Note that tool calls
        are not streamed - only the final text response.

        Args:
            user_id: The Slack user ID
            message: The user's message
            channel_id: The channel/DM ID
            channel_type: "dm" or "channel"

        Yields:
            Response text chunks
        """
        logger.info(f"Processing message (streaming) from {user_id}")

        try:
            # Assemble context
            context = await self.context_assembler.assemble(
                user_id=user_id,
                user_message=message,
                channel_type=channel_type,
                include_rag=True
            )

            messages = context.to_openai_messages()

            # Initial call (non-streaming to handle tools)
            response = await self.openai.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=context.tools if context.tools else None,
                tool_choice="auto"
            )

            # Handle tool calls (non-streaming)
            iterations = 0
            while response.choices[0].message.tool_calls and iterations < self.MAX_TOOL_ITERATIONS:
                iterations += 1

                tool_calls = self.tool_executor.parse_tool_calls(response)
                results = await self.tool_executor.execute_all(tool_calls)

                messages.append(response.choices[0].message.model_dump())
                for result in results:
                    messages.append(result.to_openai_message())

                response = await self.openai.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    tools=context.tools if context.tools else None,
                    tool_choice="auto"
                )

            # Final response with streaming
            stream = await self.openai.chat.completions.create(
                model=self.model,
                messages=messages,
                stream=True
            )

            full_response = ""
            async for chunk in stream:
                if chunk.choices[0].delta.content:
                    content = chunk.choices[0].delta.content
                    full_response += content
                    yield content

            # Store in memory
            self.context_assembler.add_assistant_message(user_id, full_response)

        except Exception as e:
            logger.error("Error in streaming response", e)
            yield f"I encountered an error: {str(e)}"

    async def get_summary(
        self,
        channel_id: str,
        channel_name: str,
        hours: int = 24
    ) -> str:
        """
        Generate a summary of a channel's recent activity.

        This is a convenience method that uses the slack_fetch_messages tool
        and asks the LLM to summarize.

        Args:
            channel_id: The Slack channel ID
            channel_name: Human-readable channel name
            hours: Hours of history to summarize

        Returns:
            Summary text
        """
        # Use a synthetic user ID for summaries
        user_id = f"summary_{channel_id}"

        prompt = f"""Please summarize the recent activity in #{channel_name}.

Use the slack_fetch_messages tool to get the last {hours} hours of messages,
then provide:
1. Key topics discussed
2. Important decisions or conclusions
3. Any action items or follow-ups
4. A brief draft reply if appropriate

Keep the summary concise but informative."""

        return await self.process(
            user_id=user_id,
            message=prompt,
            channel_id=channel_id,
            channel_type="channel"
        )

    def clear_conversation(self, user_id: str) -> None:
        """
        Clear the conversation history for a user.

        Useful for starting fresh or on explicit request.

        Args:
            user_id: The Slack user ID
        """
        self.memory.clear_conversation(user_id)
        logger.info(f"Cleared conversation for {user_id}")
